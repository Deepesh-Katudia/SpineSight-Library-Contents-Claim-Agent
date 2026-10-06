"""Run with: services/api/.venv/Scripts/python -m pytest eval"""

from pathlib import Path

from score import score, to_markdown

TEMPLATE = Path(__file__).parent / "ground_truth_template"


def quote(amount):
    return {"amount": amount}


def packet(books, items=(), room=None, t=120.0):
    return {
        "sweep": {"id": "s"},
        "books": books,
        "items": list(items),
        "room": room or {"floor_area_m2": 13.5, "wall_area_m2": 30.0},
        "totals": {"book_count": len(books)},
        "metrics": [{"stage": "time_to_packet", "latency_s": t, "cost_usd": 0.4}],
    }


def test_template_scores_all_bars():
    p = packet(
        [
            {"status": "identified", "title": "Dune", "spine_height_cm": 18.0, "spine_thickness_cm": 3.3,
             "replacement_cost": quote(520), "used_value": quote(400)},
            {"status": "unidentified", "title": ""},
        ],
        items=[{"category": "lamp", "description": "brass floor lamp"}],
    )
    bars = {b.measure: b for b in score(p, TEMPLATE)}

    assert bars["Book count"].passed is True
    assert bars["Title identification"].passed is True
    assert bars["Spine height"].passed is True
    assert bars["Book price (replacement)"].passed is True
    assert bars["Book price (used)"].passed is False  # 400 vs 250
    assert bars["Non-book items"].passed is False  # portrait missed
    assert bars["Floor area"].passed is True
    assert bars["Wall area"].passed is False
    assert bars["Time to packet"].passed is True
    assert "| Book count |" in to_markdown(list(bars.values()))


def test_confidently_wrong_titles_fail_the_bar():
    p = packet([
        {"status": "identified", "title": "Dune"},
        {"status": "identified", "title": "Moby Dick"},
    ])
    bars = {b.measure: b for b in score(p, TEMPLATE)}
    assert bars["Title identification"].passed is False
    assert "Moby Dick" in bars["Title identification"].detail
