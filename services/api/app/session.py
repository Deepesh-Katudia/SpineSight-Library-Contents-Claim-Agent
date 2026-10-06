"""A live sweep: receives keyframes, runs detect -> read -> track -> measure per frame, keeps the
live inventory, emits events (SSE) and capture hints the voice agent speaks to the user.
Identification starts in the background as soon as a spine becomes legible, so most of the
post-sweep work is already done when the user stops."""

from __future__ import annotations

import asyncio
import logging
import time
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.deps import Deps
from app.llm import CallStats, LLMError
from app.stages import detect, read
from app.stages.identify import Identification, identify
from app.stages.items import ItemTracker
from app.stages.measure import plausible_a4, refine_quad, scale_from_reference
from app.stages.observations import FrameObservation
from app.stages.price import Locale
from app.stages.room import WallMeasurement, measure_wall
from app.stages.track import SpineTracker, TrackedSpine

log = logging.getLogger(__name__)

BLUR_LIMIT = 0.5
GLARE_LIMIT = 0.5
UNREADABLE_FRACTION = 0.5
HINT_COOLDOWN_S = 8.0
FRAME_WORKERS = 3
IDENTIFY_CONCURRENCY = 6
IDENTIFY_RETRIES = 2


@dataclass(frozen=True)
class UserFact:
    kind: str  # exclude_shelf | exclude_item | book_note | item_note | room_note
    text: str
    target: str
    ref_hint: str
    at: str


@dataclass
class SweepSession:
    deps: Deps
    locale: Locale
    device: str = ""
    id: str = field(default_factory=lambda: secrets.token_hex(6))
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    target: str = ""
    stats: CallStats = field(default_factory=CallStats)
    spines: SpineTracker = field(default_factory=SpineTracker)
    items: ItemTracker = field(default_factory=ItemTracker)
    walls: list[WallMeasurement] = field(default_factory=list)
    facts: list[UserFact] = field(default_factory=list)
    frames_received: int = 0
    frames_processed: int = 0
    frame_errors: int = 0
    _subscribers: list[asyncio.Queue] = field(default_factory=list)
    _identifications: dict[tuple, asyncio.Task] = field(default_factory=dict)
    _hint_at: dict[str, float] = field(default_factory=dict)
    _identify_sem: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(IDENTIFY_CONCURRENCY))
    finishing: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=60))
    _workers: list[asyncio.Task] = field(default_factory=list)

    # ---------- lifecycle ----------
    def start(self) -> None:
        self._workers = [asyncio.create_task(self._worker()) for _ in range(FRAME_WORKERS)]

    async def drain(self) -> None:
        await self._queue.join()
        for w in self._workers:
            w.cancel()
        if self._identifications:
            await asyncio.gather(*self._identifications.values(), return_exceptions=True)

    # ---------- events ----------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def emit(self, event: dict) -> None:
        for q in list(self._subscribers):
            if not q.full():
                q.put_nowait(event)

    def hint(self, key: str, text: str) -> None:
        now = time.monotonic()
        if now - self._hint_at.get(key, 0) < HINT_COOLDOWN_S:
            return
        self._hint_at[key] = now
        self.emit({"type": "hint", "key": key, "text": text, "target": self.target})

    # ---------- inputs ----------
    async def enqueue_frame(self, jpeg: bytes, t_ms: int, width: int, height: int, target: str) -> str | None:
        self.frames_received += 1
        ref = self.deps.store.frame_ref(self.id, t_ms)
        await self.deps.store.save(ref, jpeg)
        try:
            self._queue.put_nowait((ref, jpeg, t_ms, width, height, target or self.target))
        except asyncio.QueueFull:
            self.hint("backlog", "Processing is behind; please hold steady for a second.")
            return None
        return ref

    def add_fact(self, kind: str, text: str, ref_hint: str = "") -> UserFact:
        fact = UserFact(kind, text, self.target, ref_hint, datetime.now(UTC).isoformat())
        self.facts.append(fact)
        self.emit({"type": "fact", "kind": kind, "text": text, "ref_hint": ref_hint, "target": self.target})
        return fact

    # ---------- per-frame pipeline ----------
    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._process(*job)
            except (LLMError, ValueError) as exc:
                self.frame_errors += 1
                log.warning("frame %s failed: %s", job[0], exc)
                self.emit({"type": "frame_error", "frame_ref": job[0], "error": str(exc)[:200]})
            except Exception:
                self.frame_errors += 1
                log.exception("frame %s crashed", job[0])
            finally:
                self._queue.task_done()

    async def _process(self, ref: str, jpeg: bytes, t_ms: int, width: int, height: int, target: str) -> None:
        llm = self.deps.llm(self.stats)
        obs = await detect.detect_frame(llm, jpeg, ref, t_ms, width, height, target)
        if obs.reference:
            img = await asyncio.to_thread(read.decode_jpeg, jpeg)
            refined = await asyncio.to_thread(refine_quad, img, obs.reference)
            obs.reference = refined if plausible_a4(refined) else None
        obs = await read.read_spines(llm, jpeg, obs)
        await self.deps.events.log(self.id, "frame_observation", _obs_summary(obs))

        base = scale_from_reference(obs.reference) if obs.reference else None
        async with self._lock:
            touched = self.spines.ingest(obs, lambda _o: base)
            touched_items = self.items.ingest(ref, obs.objects, base)
            wall = measure_wall(obs, self.locale.country)
            if wall:
                self.walls.append(wall)
            self.frames_processed += 1

        self._capture_hints(obs, touched)
        for spine in touched:
            self._maybe_identify(spine)
            self.emit(_book_event(spine))
        for it in touched_items:
            self.emit({"type": "item", "id": it.id, "category": it.category,
                       "description": it.best[1].description, "brand_model": it.brand_model, "frame_ref": it.best[0]})
        if wall:
            self.emit({"type": "wall", "label": wall.label, "width_m": wall.width_m, "height_m": wall.height_m,
                       "method": wall.method, "frame_ref": wall.frame_ref})
        self.emit({"type": "frame", "frame_ref": ref, "t_ms": t_ms, "spines": len(obs.spines),
                   "objects": len(obs.objects), "scale": "a4" if base else ""})

    def _capture_hints(self, obs: FrameObservation, touched: list[TrackedSpine]) -> None:
        q = obs.quality
        if q.blur > BLUR_LIMIT:
            self.hint("blur", "The picture is blurry. Ask the user to slow down and hold the phone steady.")
        if q.glare > GLARE_LIMIT:
            self.hint("glare", "Glare is hiding spines. Ask the user to tilt the phone or step out of the light.")
        if obs.spines:
            unreadable = sum(1 for s in obs.spines if s.legibility < 0.4)
            if unreadable / len(obs.spines) > UNREADABLE_FRACTION:
                self.hint(f"unreadable:{obs.target}",
                          f"{unreadable} of {len(obs.spines)} spines on {obs.target or 'this shelf'} are unreadable. "
                          "Ask the user to step closer to this shelf and pan slowly.")
            if not any(s.scale_method for s in touched):
                self.hint(f"noscale:{obs.target}",
                          "No metric reference in view for these books. Ask the user to include the A4 sheet "
                          "on this shelf in the frame for a moment.")
        if obs.target.startswith("wall:") and obs.wall is None:
            self.hint(f"wall:{obs.target}", "Ask the user to step back and show this whole wall, floor to ceiling "
                                            "and corner to corner, with the A4 sheet or the door visible.")

    def _maybe_identify(self, spine: TrackedSpine) -> None:
        """Start a catalogue lookup once a spine has a legible title. Illegible reads and failed
        lookups are never cached, so a later sharp sighting of the same spine is still looked up."""
        r = spine.best_read
        s = self.deps.settings
        key = (r.title.lower(), r.author.lower(), r.publisher.lower())
        if not r.title or r.legibility < s.min_legibility:
            return
        existing = self._identifications.get(key)
        if existing is not None and not (existing.done() and existing.exception() is not None):
            return

        async def run() -> Identification:
            async with self._identify_sem:
                for attempt in range(IDENTIFY_RETRIES + 1):
                    try:
                        ident = await identify(r, self.deps.catalog_search, s.min_legibility, s.min_catalog_match)
                        break
                    except Exception:
                        if attempt == IDENTIFY_RETRIES:
                            raise
                        await asyncio.sleep(1.5 * (attempt + 1))
            self.emit({"type": "identified", "key": list(key), "status": ident.status, "title": ident.title,
                       "author": ident.author, "confidence": ident.confidence})
            return ident

        self._identifications[key] = asyncio.create_task(run())

    async def identification_for(self, spine: TrackedSpine) -> Identification:
        r = spine.best_read
        key = (r.title.lower(), r.author.lower(), r.publisher.lower())
        if key not in self._identifications:
            self._maybe_identify(spine)
        task = self._identifications.get(key)
        if task is None:
            return Identification("unidentified", reason=f"spine legibility {r.legibility:.2f}; no readable title — not guessed")
        try:
            return await task
        except Exception as exc:  # a source outage must not crash the packet
            log.warning("identification failed for %s: %s", key, exc)
            return Identification("unidentified", reason=f"catalogue lookup failed: {exc}")

    @property
    def duration_s(self) -> float:
        end = self.ended_at or datetime.now(UTC)
        return round((end - self.started_at).total_seconds(), 1)


def _book_event(spine: TrackedSpine) -> dict:
    r = spine.best_read
    return {"type": "book", "id": spine.id, "shelf": spine.row_key, "text": r.text, "title": r.title,
            "author": r.author, "legibility": r.legibility, "height_cm": spine.height_cm,
            "thickness_cm": spine.thickness_cm, "frame_ref": spine.frame_ref}


def _obs_summary(obs: FrameObservation) -> dict:
    return {
        "frame_ref": obs.frame_ref, "target": obs.target, "t_ms": obs.t_ms,
        "spines": [{"box": s.box, "row": s.row, "orientation": s.orientation, "text": s.text,
                    "title": s.title, "author": s.author, "legibility": s.legibility} for s in obs.spines],
        "objects": [{"box": o.box, "category": o.category, "description": o.description,
                     "brand_model": o.brand_model} for o in obs.objects],
        "reference": obs.reference, "has_wall": obs.wall is not None,
        "quality": {"blur": obs.quality.blur, "glare": obs.quality.glare, "issues": list(obs.quality.issues)},
    }
