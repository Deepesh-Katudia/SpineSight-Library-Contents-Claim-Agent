"""After the sweep: finish identification, apply the policyholder's spoken corrections, price,
measure the room and assemble the packet. Every stage is timed for the metrics block."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager
from datetime import UTC, datetime

from rapidfuzz import fuzz

from app.schema.claim_packet import (
    Book,
    ClaimPacket,
    Item,
    ItemPrice,
    LocaleComparison,
    PriceQuote,
    StageMetric,
    Sweep,
)
from app.session import SweepSession, UserFact
from app.stages.identify import Identification
from app.stages.items import TrackedItem, price_item, to_item
from app.stages.packet import build_packet
from app.stages.price import BookSignals, Locale, apply_pricing, price_book
from app.stages.room import assemble_room
from app.stages.track import TrackedSpine

log = logging.getLogger(__name__)
PRICE_CONCURRENCY = 6
NOTE_MATCH = 70
SECOND_LOCALE_SAMPLE = 10


class Timer:
    def __init__(self) -> None:
        self.latency: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.latency[name] = self.latency.get(name, 0) + time.perf_counter() - started


def _match_book(hint: str, books: list[Book]) -> Book | None:
    if not hint:
        return None
    scored = [(fuzz.token_set_ratio(hint.lower(), f"{b.title} {b.author} {b.spine_text_raw}".lower()), b) for b in books]
    best = max(scored, default=(0, None), key=lambda x: x[0])
    return best[1] if best[0] >= NOTE_MATCH else None


def _match_item(hint: str, items: list[TrackedItem]) -> TrackedItem | None:
    if not hint:
        return None
    scored = [(fuzz.token_set_ratio(hint.lower(), f"{t.category} {t.best[1].description} {t.brand_model}".lower()), t)
              for t in items]
    best = max(scored, default=(0, None), key=lambda x: x[0])
    return best[1] if best[0] >= NOTE_MATCH else None


def to_book(spine: TrackedSpine, shelf: str, position: int, ident: Identification) -> Book:
    r = spine.best_read
    identified = ident.status == "identified"
    return Book(
        id=spine.id, shelf=shelf, position=position, frame_ref=spine.frame_ref,
        frame_refs=sorted({s.frame_ref for s in spine.sightings}),
        status="identified" if identified else "unidentified",
        title=ident.title if identified else "",
        author=ident.author if identified else "",
        publisher=ident.publisher if identified else "",
        edition=ident.edition, isbn=ident.isbn,
        spine_text_raw=r.text, orientation=r.orientation if r.orientation in ("vertical", "flat") else "unknown",
        spine_height_cm=spine.height_cm, spine_thickness_cm=spine.thickness_cm,
        id_confidence=ident.confidence if identified else 0.0,
        catalog_source=ident.catalog_source, catalog_url=ident.catalog_url,
        unidentified_reason="" if identified else ident.reason,
    )


def apply_facts(books: list[Book], items: list[TrackedItem], facts: list[UserFact]) -> tuple[list[Book], list[str]]:
    """Attach spoken corrections to lines. Anything that cannot be attached is reported, not dropped."""
    unattached: list[str] = []
    by_id = {b.id: b for b in books}
    for f in facts:
        if f.kind == "exclude_shelf":
            unit = (f.ref_hint or f.target.removeprefix("shelf:")).strip().upper()
            hits = [b for b in by_id.values() if b.shelf.upper().startswith(f"{unit}-")]
            for b in hits:
                by_id[b.id] = b.model_copy(update={"excluded": True, "user_notes": b.user_notes + [f.text]})
            if not hits:
                unattached.append(f"exclude shelf '{unit}': no books tracked on that shelf ({f.text})")
        elif f.kind == "book_note":
            b = _match_book(f.ref_hint, list(by_id.values()))
            if b:
                by_id[b.id] = b.model_copy(update={"user_notes": b.user_notes + [f.text]})
            else:
                unattached.append(f"book note not matched to a line: {f.text}")
        elif f.kind in ("item_note", "exclude_item"):
            t = _match_item(f.ref_hint, items)
            if t:
                t.user_notes.append(f.text)
                t.excluded = t.excluded or f.kind == "exclude_item"
            else:
                unattached.append(f"item note not matched to a line: {f.text}")
        else:
            unattached.append(f"{f.kind}: {f.text}")
    return [by_id[b.id] for b in books], unattached


async def _price_books(session: SweepSession, books: list[Book], idents: dict[str, Identification],
                       locale: Locale) -> dict[str, tuple]:
    deps, sem = session.deps, asyncio.Semaphore(PRICE_CONCURRENCY)
    threshold = deps.settings.appraisal_threshold
    if locale.currency != deps.settings.primary_currency:
        threshold *= (await deps.fx.rate(deps.settings.primary_currency, locale.currency)).rate

    async def one(b: Book):
        async with sem:
            ident = idents[b.id]
            spine_flags = session_flags.get(b.id, ())
            retail = await deps.retail_offer(b.title, b.author, b.isbn, locale.country)
            result = await price_book(b, locale, deps.ebay, deps.fx, retail,
                                      BookSignals(ident.year, spine_flags, tuple(b.user_notes)), threshold)
            return b.id, result

    session_flags = {s.id: s.best_read.visual_flags for _, _, s in session.spines.all_spines()}
    targets = [b for b in books if b.status == "identified" and not b.excluded]
    results = await asyncio.gather(*(one(b) for b in targets), return_exceptions=True)
    for b, r in zip(targets, results):
        if isinstance(r, BaseException):
            log.warning("pricing %s (%s) failed: %r", b.id, locale.country, r)
    return {r[0]: r[1] for r in results if not isinstance(r, BaseException)}


async def finalize(session: SweepSession) -> ClaimPacket:
    timer = Timer()
    deps, locale = session.deps, session.locale
    with timer.stage("drain_frames"):
        await session.drain()

    with timer.stage("identify"):
        tracked = session.spines.all_spines()
        found = await asyncio.gather(*(session.identification_for(s) for _, _, s in tracked))
        idents = {s.id: ident for (_, _, s), ident in zip(tracked, found)}
        books = [to_book(s, shelf, pos, idents[s.id]) for shelf, pos, s in tracked]
        books, unattached = apply_facts(books, session.items.items, session.facts)

    with timer.stage("price_books"):
        priced = await _price_books(session, books, idents, locale)
        books = [apply_pricing(b, priced[b.id]) if b.id in priced else b for b in books]

    with timer.stage("price_items"):
        threshold = deps.settings.appraisal_threshold
        item_prices = await asyncio.gather(
            *(price_item(t, locale, deps.ebay, deps.fx, threshold) for t in session.items.items),
            return_exceptions=True)
        for t, p in zip(session.items.items, item_prices):
            if isinstance(p, BaseException):
                log.warning("pricing item %s failed: %r", t.id, p)
        items: list[Item] = [
            to_item(t, *(p if not isinstance(p, BaseException) else ("unpriced", ItemPrice())))
            for t, p in zip(session.items.items, item_prices)
        ]

    with timer.stage("room"):
        room = assemble_room(session.walls)

    with timer.stage("second_locale"):
        try:
            second = await second_locale(session, books, idents)
        except Exception as exc:  # the locale-proof block must never cost the whole packet
            log.warning("second locale pricing failed: %r", exc)
            second = []
            unattached.append(f"second-locale pricing failed: {exc}")

    session.ended_at = session.ended_at or datetime.now(UTC)
    s = deps.settings
    sweep = Sweep(id=session.id, captured_at=session.started_at.isoformat(), device=session.device,
                  duration_s=session.duration_s, country=locale.country, currency=locale.currency,
                  second_locale={"country": s.second_country, "currency": s.second_currency})
    with timer.stage("packet"):
        packet = build_packet(sweep, room, books, items, metrics=_metrics(session, timer))
        packet = packet.model_copy(update={"second_locale": second, "unattached_notes": unattached})
        _verify_frame_refs(session, packet)
    return packet


async def second_locale(session: SweepSession, books: list[Book], idents: dict[str, Identification]) -> list[LocaleComparison]:
    s = session.deps.settings
    target = Locale(s.second_country, s.second_currency)
    sample = [b for b in books if b.status == "identified" and not b.excluded][:SECOND_LOCALE_SAMPLE]
    priced = await _price_books(session, sample, idents, target)
    out = []
    for b in sample:
        r = priced.get(b.id)
        out.append(LocaleComparison(
            book_id=b.id, title=b.title, country=target.country, currency=target.currency,
            replacement_cost=r.replacement if r else PriceQuote(),
            used_value=r.used if r else PriceQuote(),
            appraisal_reason=r.appraisal_reason if r else "pricing failed",
        ))
    return out


def _metrics(session: SweepSession, timer: Timer) -> list[StageMetric]:
    st = session.stats
    live = [StageMetric(stage=f"live_{k}", latency_s=round(v, 2), calls=st.calls.get(k, 0),
                        cost_usd=round(st.cost_usd.get(k, 0), 4)) for k, v in st.latency_s.items()]
    post = [StageMetric(stage=k, latency_s=round(v, 2)) for k, v in timer.latency.items()]
    total = sum(timer.latency.values())
    return live + post + [StageMetric(stage="time_to_packet", latency_s=round(total, 2),
                                      cost_usd=round(sum(st.cost_usd.values()), 4))]


def _verify_frame_refs(session: SweepSession, packet: ClaimPacket) -> None:
    refs = [b.frame_ref for b in packet.books] + [i.frame_ref for i in packet.items] + packet.room.frame_refs
    missing = [r for r in refs if r and not session.deps.store.exists(r)]
    if missing:
        raise RuntimeError(f"packet references {len(missing)} frames that were not saved, e.g. {missing[0]}")
