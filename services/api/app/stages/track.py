"""Stage 4: track spines across overlapping frames so each physical book is counted once.

A pan produces overlapping frames. For each shelf row in a new frame we slide its left-to-right
spine sequence along every known row of the same shelf unit and pick the offset with the best
agreement (fuzzy spine text when both are legible, pixel aspect ratio otherwise). Unmatched
spines extend the row; an unmatched sequence starts a new row.
"""

from __future__ import annotations

import itertools
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.stages.measure import FrameScale, measure_spine, pick_scale, scale_from_known_spines
from app.stages.observations import FrameObservation, SpineObs

TEXT_MATCH = 80
TEXT_MISMATCH = 45
ASPECT_TOLERANCE = 0.2
MIN_ALIGN_SCORE = 1.0
MIN_MEAN_SCORE = 0.4
METRIC_METHODS = ("a4_reference", "chained_spines")


@dataclass
class Sighting:
    frame_ref: str
    spine: SpineObs
    height_cm: float | None
    thickness_cm: float | None
    scale_method: str
    scale_confidence: float


@dataclass
class TrackedSpine:
    id: str
    unit: str
    row_key: str
    sightings: list[Sighting] = field(default_factory=list)

    @property
    def best_read(self) -> SpineObs:
        return max(self.sightings, key=lambda s: (s.spine.legibility, len(s.spine.text))).spine

    @property
    def frame_ref(self) -> str:
        return max(self.sightings, key=lambda s: s.spine.legibility).frame_ref

    def _best_scale_sightings(self) -> list[Sighting]:
        measured = [s for s in self.sightings if s.height_cm is not None or s.thickness_cm is not None]
        if not measured:
            return []
        top = max(s.scale_confidence for s in measured)
        return [s for s in measured if s.scale_confidence == top]

    def _median(self, attr: str) -> float | None:
        values = [getattr(s, attr) for s in self._best_scale_sightings() if getattr(s, attr) is not None]
        return round(statistics.median(values), 1) if values else None

    @property
    def height_cm(self) -> float | None:
        return self._median("height_cm")

    @property
    def thickness_cm(self) -> float | None:
        return self._median("thickness_cm")

    @property
    def scale_method(self) -> str:
        best = self._best_scale_sightings()
        return best[0].scale_method if best else ""

    @property
    def scale_confidence(self) -> float:
        best = self._best_scale_sightings()
        return best[0].scale_confidence if best else 0.0


def _aspect(s: SpineObs) -> float:
    return s.thickness_px / s.height_px if s.height_px else 0.0


def match_score(known: SpineObs, new: SpineObs) -> float:
    if known.orientation != new.orientation:
        return -1.0
    if known.text and new.text and known.legibility >= 0.4 and new.legibility >= 0.4:
        ratio = fuzz.token_set_ratio(known.text, new.text)
        if ratio >= TEXT_MATCH:
            return 2.0
        if ratio <= TEXT_MISMATCH:
            return -2.0
        return 0.0
    a, b = _aspect(known), _aspect(new)
    if a and b and abs(a - b) / max(a, b) <= ASPECT_TOLERANCE:
        return 0.5
    return -0.5


def best_offset(row: list[TrackedSpine], seq: list[SpineObs]) -> tuple[int, float]:
    """Offset k aligns seq[i] with row[k+i]. Returns (k, score); score -inf when no overlap.

    Offsets with weak mean per-pair agreement are rejected. Ties (typical for a run of unreadable,
    similar spines) resolve to the largest k: the pan continuing past what is already known.
    """
    best = (0, float("-inf"))
    for k in range(-len(seq) + 1, len(row)):
        pairs = [(row[k + i], s) for i, s in enumerate(seq) if 0 <= k + i < len(row)]
        if not pairs:
            continue
        score = sum(match_score(t.best_read, s) for t, s in pairs)
        if score / len(pairs) < MIN_MEAN_SCORE:
            continue
        if score >= best[1]:
            best = (k, score)
    return best


class SpineTracker:
    def __init__(self) -> None:
        self.rows: dict[str, list[TrackedSpine]] = {}
        self._ids = itertools.count(1)
        self._row_ids = itertools.count(1)

    def _new_spine(self, unit: str, row_key: str) -> TrackedSpine:
        return TrackedSpine(id=f"bk_{next(self._ids):04d}", unit=unit, row_key=row_key)

    def _align(self, unit: str, seq: list[SpineObs]) -> tuple[str, int] | None:
        best: tuple[str, int, float] | None = None
        for key, row in self.rows.items():
            if not key.startswith(f"{unit}-"):
                continue
            k, score = best_offset(row, seq)
            if score >= MIN_ALIGN_SCORE and (best is None or score > best[2]):
                best = (key, k, score)
        return (best[0], best[1]) if best else None

    def ingest(
        self, obs: FrameObservation, base_scale: Callable[[FrameObservation], FrameScale | None]
    ) -> list[TrackedSpine]:
        """Align, pick this frame's scale (chaining from known spines), measure, and merge."""
        unit = obs.target.split(":", 1)[1] if obs.target.startswith("shelf:") else "U"
        by_row: dict[int, list[SpineObs]] = {}
        for s in obs.spines:
            by_row.setdefault(s.row, []).append(s)

        plans = []
        for seq in by_row.values():
            seq = sorted(seq, key=lambda s: s.box[0])
            plans.append((seq, self._align(unit, seq)))

        known = [
            (s.height_px, self.rows[a[0]][a[1] + i])
            for seq, a in plans if a
            for i, s in enumerate(seq)
            if 0 <= a[1] + i < len(self.rows[a[0]]) and s.orientation != "flat"
        ]
        known = [(px, t) for px, t in known if t.height_cm and t.scale_method in METRIC_METHODS]
        source_conf = min((t.scale_confidence for _, t in known), default=0.0)
        chained = scale_from_known_spines([(px, t.height_cm) for px, t in known], source_conf)
        scale = pick_scale(base_scale(obs), chained)

        touched: list[TrackedSpine] = []
        for seq, alignment in plans:
            touched.extend(self._merge(unit, seq, alignment, obs.frame_ref, scale))
        return touched

    def _merge(self, unit, seq, alignment, frame_ref, scale) -> list[TrackedSpine]:
        if alignment is None:
            key = f"{unit}-r{next(self._row_ids)}"
            self.rows[key] = []
            offset = 0
        else:
            key, offset = alignment
        row = self.rows[key]
        if offset < 0:
            row[:0] = [self._new_spine(unit, key) for _ in range(-offset)]
            offset = 0
        touched = []
        for i, spine in enumerate(seq):
            idx = offset + i
            if idx >= len(row):
                row.append(self._new_spine(unit, key))
            h, t = measure_spine(spine, scale) if scale else (None, None)
            row[idx].sightings.append(
                Sighting(frame_ref, spine, h, t, scale.method if scale else "", scale.confidence if scale else 0.0)
            )
            touched.append(row[idx])
        return touched

    def all_spines(self) -> list[tuple[str, int, TrackedSpine]]:
        """(shelf label, position, spine) in shelf order."""
        out = []
        for key in sorted(self.rows):
            for pos, spine in enumerate(self.rows[key], start=1):
                out.append((key, pos, spine))
        return out
