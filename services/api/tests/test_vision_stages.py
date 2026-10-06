import numpy as np
import pytest

from app.llm import LLMError, parse_json
from app.sources.catalog import CatalogCandidate
from app.stages.detect import parse_detection
from app.stages.identify import choose, identify
from app.stages.measure import (
    measure_spine,
    order_quad,
    pick_scale,
    refine_quad,
    scale_from_format_prior,
    scale_from_known_spines,
    scale_from_reference,
)
from app.stages.observations import FrameObservation, SpineObs
from app.stages.read import apply_reads, build_sheet, crop_spine
from app.stages.track import SpineTracker, best_offset, match_score

# A4 sheet seen head-on at 10 px per cm
A4_PX = ((100, 100), (310, 100), (310, 397), (100, 397))


def spine(x0, w=30, h=210, text="", legibility=0.0, row=0, orientation="vertical", y0=100):
    return SpineObs(box=(x0, y0, x0 + w, y0 + h), row=row, orientation=orientation, text=text,
                    title=text, legibility=legibility)


# ---------- measure ----------

def test_a4_reference_gives_metric_spine():
    scale = scale_from_reference(A4_PX)
    assert measure_spine(spine(400), scale) == (21.0, 3.0)


def test_a4_reference_handles_landscape_and_shuffled_corners():
    landscape = ((100, 100), (397, 100), (397, 310), (100, 310))
    shuffled = (landscape[2], landscape[0], landscape[3], landscape[1])
    scale = scale_from_reference(shuffled)
    assert measure_spine(spine(400), scale) == (21.0, 3.0)


def test_perspective_is_corrected_by_homography():
    # Sheet foreshortened: right edge shorter than left (camera turned)
    quad = ((100, 100), (300, 120), (300, 377), (100, 397))
    scale = scale_from_reference(quad)
    top = scale.to_cm(100, 100)
    br = scale.to_cm(300, 377)
    assert top == pytest.approx((0, 0), abs=1e-6)
    assert br == pytest.approx((21.0, 29.7), abs=1e-6)


def test_flat_book_swaps_axes():
    scale = scale_from_reference(A4_PX)
    assert measure_spine(spine(400, w=240, h=40, orientation="flat"), scale) == (24.0, 4.0)


def test_implausible_dimensions_become_none():
    scale = scale_from_reference(A4_PX)
    assert measure_spine(spine(400, w=300, h=2000), scale) == (None, None)


def test_chained_scale_needs_two_known_spines_and_beats_prior():
    assert scale_from_known_spines([(200, 20.0)]) is None
    chained = scale_from_known_spines([(200, 20.0), (220, 22.0)])
    prior = scale_from_format_prior([spine(0), spine(40), spine(80)])
    assert pick_scale(None, prior, chained).method == "chained_spines"
    assert measure_spine(spine(0, w=30, h=210), chained)[0] == 21.0


def test_format_prior_is_low_confidence():
    prior = scale_from_format_prior([spine(0), spine(40), spine(80)])
    assert prior.method == "format_prior" and prior.confidence < 0.5
    assert scale_from_format_prior([spine(0)]) is None


def test_order_quad():
    assert order_quad(((310, 397), (100, 100), (100, 397), (310, 100))).tolist() == [
        [100, 100], [310, 100], [310, 397], [100, 397]]


def test_refine_quad_snaps_to_white_sheet():
    img = np.full((600, 600, 3), 40, np.uint8)
    img[100:397, 100:310] = 250
    rough = ((110, 92), (300, 108), (318, 390), (95, 405))
    refined = order_quad(refine_quad(img, rough))
    assert refined[0] == pytest.approx([100, 100], abs=3)
    assert refined[2] == pytest.approx([309, 396], abs=3)


# ---------- detect / read ----------

def test_parse_detection_scales_and_sorts():
    raw = {
        "spines": [{"x0": 500, "y0": 0, "x1": 520, "y1": 500, "row": 0},
                   {"x0": 100, "y0": 0, "x1": 120, "y1": 500, "row": 0}],
        "objects": [{"x0": 0, "y0": 0, "x1": 100, "y1": 100, "category": "lamp", "confidence": 0.8}],
        "reference_a4": {"corners": [[0, 0], [100, 0], [100, 100], [0, 100]]},
        "wall": {"corners": [[0, 0], [1000, 0], [1000, 1000], [0, 1000]], "openings": []},
        "quality": {"blur": 0.7, "issues": ["motion blur"]},
    }
    obs = parse_detection(raw, "f1", 10, 2000, 1000, target="shelf:A")
    assert obs.spines[0].box[0] == 200
    assert obs.objects[0].category == "lamp"
    assert obs.reference[1] == (200.0, 0.0)
    assert obs.wall is not None and obs.quality.blur == 0.7


def test_crop_rotates_vertical_spine_and_sheet_numbers():
    img = np.zeros((400, 400, 3), np.uint8)
    crop = crop_spine(img, spine(10, w=20, h=200, y0=10))
    assert crop.shape[1] > crop.shape[0]
    sheet = build_sheet([crop, crop])
    assert sheet.shape[0] == 2 * (96 + 8)


def test_apply_reads_clamps_and_never_invents():
    spines = [spine(0), spine(40)]
    out = apply_reads(spines, [{"n": 1, "text": "DUNE Herbert", "title": "Dune", "legibility": 1.4}])
    assert out[0].title == "Dune" and out[0].legibility == 1.0
    assert out[1].title == "" and out[1].legibility == 0.0


def test_parse_json_strips_fences():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure: {"a": 2} done') == {"a": 2}
    with pytest.raises(LLMError):
        parse_json("no json here")


# ---------- track ----------

def obs(frame, spines, target="shelf:A"):
    return FrameObservation(frame_ref=frame, t_ms=0, width=1000, height=1000, target=target, spines=spines)


def test_overlapping_frames_count_each_book_once():
    tracker = SpineTracker()
    a4 = lambda o: scale_from_reference(A4_PX)  # noqa: E731
    f1 = [spine(0, text="Dune Herbert", legibility=0.9), spine(40, text="Emma Austen", legibility=0.9),
          spine(80, text="Ulysses Joyce", legibility=0.9)]
    f2 = [spine(0, text="Emma Austen", legibility=0.9), spine(40, text="Ulysses Joyce", legibility=0.8),
          spine(80, text="Beloved Morrison", legibility=0.9)]
    tracker.ingest(obs("f1", f1), a4)
    tracker.ingest(obs("f2", f2), lambda o: None)

    spines = tracker.all_spines()
    assert [s.best_read.text for _, _, s in spines] == ["Dune Herbert", "Emma Austen", "Ulysses Joyce", "Beloved Morrison"]
    # Beloved was only seen in f2 (no A4) -> scale chained from the known books
    beloved = spines[-1][2]
    assert beloved.scale_method == "chained_spines" and beloved.height_cm == 21.0


def test_panning_left_prepends():
    tracker = SpineTracker()
    tracker.ingest(obs("f1", [spine(0, text="Emma Austen", legibility=0.9), spine(40, text="Ulysses Joyce", legibility=0.9)]), lambda o: None)
    tracker.ingest(obs("f2", [spine(0, text="Dune Herbert", legibility=0.9), spine(40, text="Emma Austen", legibility=0.9)]), lambda o: None)
    assert [s.best_read.text for _, _, s in tracker.all_spines()] == ["Dune Herbert", "Emma Austen", "Ulysses Joyce"]


def test_unrelated_row_starts_new_row():
    tracker = SpineTracker()
    tracker.ingest(obs("f1", [spine(0, text="Dune Herbert", legibility=0.9)]), lambda o: None)
    tracker.ingest(obs("f2", [spine(0, text="Moby Dick Melville", legibility=0.9)]), lambda o: None)
    assert len(tracker.rows) == 2


def test_match_score_rules():
    assert match_score(spine(0, text="Dune", legibility=0.9), spine(0, text="Dune", legibility=0.9)) == 2.0
    assert match_score(spine(0, text="Dune", legibility=0.9), spine(0, text="Zzyzx Road", legibility=0.9)) == -2.0
    assert match_score(spine(0), spine(0)) == 0.5
    assert match_score(spine(0), spine(0, orientation="flat")) == -1.0
    assert best_offset([], [spine(0)])[1] == float("-inf")


# ---------- identify ----------

def cand(title, authors=("Frank Herbert",), publisher="Ace", isbn="9780441013593", source="google_books"):
    return CatalogCandidate(title, authors, publisher, isbn, "1990", source, "https://x")


def read(title="Dune", author="Frank Herbert", publisher="", legibility=0.9):
    return SpineObs(box=(0, 0, 1, 1), row=0, orientation="vertical", text=f"{title} {author}",
                    title=title, author=author, publisher=publisher, legibility=legibility)


def test_identifies_work_but_not_edition_without_publisher():
    ident = choose(read(), [cand("Dune")], 0.82)
    assert ident.status == "identified" and ident.title == "Dune"
    assert ident.isbn == "" and ident.edition == ""


def test_identifies_edition_when_publisher_on_spine_matches():
    ident = choose(read(publisher="ACE"), [cand("Dune")], 0.82)
    assert ident.isbn == "9780441013593" and ident.edition == "Ace 1990"


def test_weak_match_stays_unidentified():
    ident = choose(read(title="Dun Messiah?", author=""), [cand("The Dune Encyclopedia", ("Willis McNelly",))], 0.82)
    assert ident.status == "unidentified" and ident.title == ""


def test_ambiguous_candidates_stay_unidentified():
    ident = choose(read(title="Collected Poems", author=""),
                   [cand("Collected Poems", ()), cand("Collected Poems.", ()), cand("Collected Poems 1909-1962", ())], 0.82)
    assert ident.status in ("identified", "unidentified")
    two = choose(read(title="Emma", author=""), [cand("Emma", ()), cand("Emma.", ())], 0.82)
    assert two.status == "identified"  # same normalised work is not ambiguity


async def test_illegible_spine_is_never_looked_up():
    calls = []

    async def search(t, a):
        calls.append(t)
        return [cand("Dune")]

    ident = await identify(read(legibility=0.3), search, 0.6, 0.82)
    assert ident.status == "unidentified" and calls == []
