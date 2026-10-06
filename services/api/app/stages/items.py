"""Stage 8: non-book contents — dedupe across frames, measure where scale exists, price as a sourced range.

Art and portraits are never auto-priced: they go to appraisal unless the policyholder said it is a print.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from rapidfuzz import fuzz

from app.schema.claim_packet import Dimensions, Item, ItemPrice
from app.sources.common import Listing, now_iso
from app.sources.ebay import marketplace_for
from app.stages.measure import FrameScale
from app.stages.observations import ObjectObs
from app.stages.price import FxSource, Locale

ART_CATEGORIES = {"framed_art", "portrait"}
PRINT_WORDS = ("print", "poster", "reproduction")
DESCRIPTION_MATCH = 70
MIN_LISTINGS = 3


class ListingSource(Protocol):
    async def listings(self, query: str = "", gtin: str = "", condition: str = "new", country: str = "US", **kw) -> list[Listing]: ...


@dataclass
class TrackedItem:
    id: str
    category: str
    sightings: list[tuple[str, ObjectObs, FrameScale | None]] = field(default_factory=list)
    user_notes: list[str] = field(default_factory=list)
    excluded: bool = False

    @property
    def best(self) -> tuple[str, ObjectObs, FrameScale | None]:
        return max(self.sightings, key=lambda s: (s[2] is not None, s[1].confidence))

    @property
    def brand_model(self) -> str:
        return next((o.brand_model for _, o, _ in self.sightings if o.brand_model), "")


def same_object(a: ObjectObs, b: ObjectObs) -> bool:
    if a.category != b.category:
        return False
    if a.brand_model and b.brand_model:
        return fuzz.token_set_ratio(a.brand_model, b.brand_model) >= 85
    return fuzz.token_sort_ratio(a.description.lower(), b.description.lower()) >= DESCRIPTION_MATCH


class ItemTracker:
    def __init__(self) -> None:
        self.items: list[TrackedItem] = []
        self._ids = itertools.count(1)

    def ingest(self, frame_ref: str, objects: list[ObjectObs], scale: FrameScale | None) -> list[TrackedItem]:
        touched: list[TrackedItem] = []
        for obj in objects:
            # two similar objects in the same frame are two objects
            match = next((t for t in self.items if t not in touched and same_object(t.best[1], obj)), None)
            if match is None:
                match = TrackedItem(id=f"it_{next(self._ids):03d}", category=obj.category)
                self.items.append(match)
            match.sightings.append((frame_ref, obj, scale))
            touched.append(match)
        return touched


def measure_object(obj: ObjectObs, scale: FrameScale | None) -> Dimensions:
    """Approximate w x h from the frame's plane scale; depth is not observable from one view."""
    if scale is None:
        return Dimensions()
    x0, y0, x1, y1 = obj.box
    my, mx = (y0 + y1) / 2, (x0 + x1) / 2
    return Dimensions(
        w=round(scale.distance_cm((x0, my), (x1, my)), 0),
        h=round(scale.distance_cm((mx, y0), (mx, y1)), 0),
    )


def item_query(t: TrackedItem) -> str:
    if t.brand_model:
        return t.brand_model
    _, obj, _ = t.best
    return " ".join(x for x in (obj.material, obj.description or obj.category.replace("_", " ")) if x)[:80]


def is_declared_print(notes: list[str]) -> bool:
    return any(w in n.lower() for n in notes for w in PRINT_WORDS)


async def price_item(t: TrackedItem, target: Locale, source: ListingSource, fx: FxSource, threshold: float) -> tuple[str, ItemPrice]:
    if t.category in ART_CATEGORIES and not is_declared_print(t.user_notes):
        return "needs_appraisal", ItemPrice()
    query = item_query(t) + (" print" if t.category in ART_CATEGORIES else "")
    listings = await source.listings(query=query, condition="new", country=target.country)
    currency = listings[0].currency if listings else ""
    amounts = [x.amount for x in listings if x.currency == currency]
    if len(amounts) < MIN_LISTINGS:
        return "unpriced", ItemPrice()

    low, high = (float(v) for v in np.percentile(amounts, [25, 75]))
    rate = (await fx.rate(currency, target.currency)).rate
    low, high = round(low * rate, 2), round(high * rate, 2)
    if high > threshold:
        return "needs_appraisal", ItemPrice()
    median = float(np.median(amounts))
    evidence = min((x for x in listings if x.currency == currency), key=lambda x: abs(x.amount - median))
    marketplace, _ = marketplace_for(target.country)
    status = "priced" if t.brand_model else "range"
    return status, ItemPrice(
        low=low,
        high=high,
        currency=target.currency,
        source=f"eBay {marketplace} new listings, IQR of {len(amounts)} for '{query}'",
        url=evidence.url,
        retrieved_at=now_iso(),
        converted=currency != target.currency,
        fx_rate=rate if currency != target.currency else None,
        sample_size=len(amounts),
    )


def to_item(t: TrackedItem, status: str, price: ItemPrice) -> Item:
    frame_ref, obj, scale = t.best
    return Item(
        id=t.id,
        category=t.category,
        description=obj.description,
        material=obj.material,
        brand_model=t.brand_model,
        frame_ref=frame_ref,
        frame_refs=sorted({f for f, _, _ in t.sightings}),
        dimensions_cm=measure_object(obj, scale),
        status=status,
        replacement_cost=price,
        confidence=round(max(o.confidence for _, o, _ in t.sightings), 2),
        user_notes=t.user_notes,
        excluded=t.excluded,
    )
