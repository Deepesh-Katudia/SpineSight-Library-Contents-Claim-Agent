"""Regressions for issues found in code review."""

import asyncio

from app.config import Settings
from app.deps import build_deps
from app.sources.catalog import CatalogCandidate
from app.stages.detect import parse_detection
from app.stages.items import ItemTracker
from app.stages.measure import plausible_a4, scale_from_known_spines, scale_from_reference
from app.stages.observations import FrameObservation, ObjectObs, SpineObs, WallObs
from app.stages.price import Locale
from app.stages.room import measure_wall
from app.stages.track import SpineTracker, best_offset

A4_PX = ((100, 100), (310, 100), (310, 397), (100, 397))


def spine(x0, text="", legibility=0.0):
    return SpineObs(box=(x0, 100, x0 + 30, 310), row=0, orientation="vertical", text=text, title=text,
                    legibility=legibility)


def test_two_identical_objects_in_one_frame_stay_two_items():
    lamp = ObjectObs(box=(0, 0, 10, 10), category="lamp", description="brass table lamp", confidence=0.9)
    tracker = ItemTracker()
    tracker.ingest("f1", [lamp, lamp], None)
    assert len(tracker.items) == 2
    tracker.ingest("f2", [lamp], None)  # seen again later: merges with one of them
    assert len(tracker.items) == 2


def test_subset_description_is_not_the_same_object():
    tracker = ItemTracker()
    tracker.ingest("f1", [ObjectObs((0, 0, 1, 1), "lamp", "lamp")], None)
    tracker.ingest("f2", [ObjectObs((0, 0, 1, 1), "lamp", "brass table lamp with green shade")], None)
    assert len(tracker.items) == 2


def test_stationary_camera_does_not_add_phantom_books():
    # Identical consecutive frames of indistinguishable spines are the same books (user holding still).
    # A true pan over uniform unreadable spines is ambiguous; see docs/failure-log.md.
    tracker = SpineTracker()
    for f in ("f1", "f2", "f3"):
        tracker.ingest(FrameObservation(f, 0, 1000, 1000, "shelf:A", [spine(i * 40) for i in range(5)]), lambda o: None)
    assert len(tracker.all_spines()) == 5


def test_weak_mean_alignment_is_rejected():
    row_tracker = SpineTracker()
    row_tracker.ingest(FrameObservation("f1", 0, 1000, 1000, "shelf:A",
                                        [spine(0, "Dune Herbert", 0.9), spine(40, "Emma Austen", 0.9)]), lambda o: None)
    row = next(iter(row_tracker.rows.values()))
    _, score = best_offset(row, [spine(0, "Moby Dick", 0.9), spine(40, "Ulysses", 0.9)])
    assert score == float("-inf")


def test_chained_confidence_decays():
    first = scale_from_known_spines([(200, 20.0), (210, 21.0)], source_confidence=0.9)
    second = scale_from_known_spines([(200, 20.0), (210, 21.0)], source_confidence=first.confidence)
    assert first.confidence == 0.75 and second.confidence < first.confidence


def test_plausible_a4():
    assert plausible_a4(A4_PX)
    assert not plausible_a4(((0, 0), (100, 0), (100, 100), (0, 100)))  # square
    assert not plausible_a4(((0, 0), (3, 0), (3, 4), (0, 4)))  # too small


def test_implausible_wall_is_dropped():
    huge = FrameObservation("w", 0, 9000, 9000, "wall:1", reference=((0, 0), (21, 0), (21, 29.7), (0, 29.7)),
                            wall=WallObs(corners=((0, 0), (5000, 0), (5000, 270), (0, 270))))
    assert measure_wall(huge, "IN") is None


def test_unrowed_spine_goes_to_containing_shelf_row():
    raw = {"shelf_rows": [{"x0": 0, "y0": 0, "x1": 1000, "y1": 400}, {"x0": 0, "y0": 500, "x1": 1000, "y1": 900}],
           "spines": [{"x0": 10, "y0": 600, "x1": 30, "y1": 850, "row": -1}]}
    obs = parse_detection(raw, "f", 0, 1000, 1000)
    assert obs.spines[0].row == 1


def test_illegible_read_is_not_cached_and_failures_retry(tmp_path):
    from app.session import SweepSession
    from app.stages.track import Sighting, TrackedSpine

    async def run():
        deps = build_deps(Settings(_env_file=None, data_dir=tmp_path))
        calls = []

        async def search(title, author, country=None):
            calls.append(title)
            if len(calls) == 1:
                raise RuntimeError("429")
            return [CatalogCandidate("Dune", ("Frank Herbert",), "", "", "1965", "open_library", "https://x")]

        deps.catalog_search = search
        session = SweepSession(deps=deps, locale=Locale("IN", "INR"))
        t = TrackedSpine("bk_1", "A", "A-r1")
        blurry = SpineObs((0, 0, 1, 1), 0, "vertical", "Dune Frank Herbert", "Dune", "Frank Herbert", "", 0.3)
        t.sightings.append(Sighting("f1", blurry, None, None, "", 0.0))
        session._maybe_identify(t)
        assert not session._identifications  # too blurry: not looked up, not cached

        sharp = SpineObs((0, 0, 1, 1), 0, "vertical", "Dune Frank Herbert", "Dune", "Frank Herbert", "", 0.95)
        t.sightings.append(Sighting("f2", sharp, None, None, "", 0.0))
        session._identify_sem = asyncio.Semaphore(1)
        import app.session as s
        s.IDENTIFY_RETRIES, old = 1, s.IDENTIFY_RETRIES
        try:
            ident = await session.identification_for(t)
        finally:
            s.IDENTIFY_RETRIES = old
        await deps.aclose()
        return ident, calls

    ident, calls = asyncio.run(run())
    assert ident.status == "identified" and len(calls) == 2
