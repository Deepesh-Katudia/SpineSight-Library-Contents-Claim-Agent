"""Score a claim packet against hand-collected ground truth, one row per pass bar.

Usage:
    python eval/score.py --packet path/to/claim_packet.json --truth eval/ground_truth [--out eval/results.md]

Ground truth folder (templates in eval/ground_truth_template/):
    books.csv  shelf,position,title,author,legible,height_cm,thickness_cm,replacement_price,used_price,price_source
               - one row per physical book (this IS the true count)
               - legible = y when a human can read the title from the spine in the sweep video
               - height/thickness filled for the hand-measured sample (>= 20 rows)
               - replacement/used price filled for the hand-checked sample (>= 15 rows), same source type
    items.csv  category,description
    room.csv   key,value   (length_m, width_m, height_m, floor_area_m2, wall_area_m2)
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

TITLE_MATCH = 85
ITEM_MATCH = 45


@dataclass(frozen=True)
class Bar:
    measure: str
    target: str
    value: str
    passed: bool | None
    detail: str = ""


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def _num(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _title_score(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a.lower(), b.lower())


def match_books(truth: list[dict], books: list[dict]) -> dict[int, dict]:
    """Greedy one-to-one match of ground-truth rows to identified packet books by title."""
    identified = [b for b in books if b.get("status") == "identified" and b.get("title")]
    pairs = sorted(
        ((_title_score(t["title"], b["title"]), i, j) for i, t in enumerate(truth) if t.get("title")
         for j, b in enumerate(identified)),
        reverse=True,
    )
    used_t, used_b, out = set(), set(), {}
    for score, i, j in pairs:
        if score < TITLE_MATCH or i in used_t or j in used_b:
            continue
        used_t.add(i)
        used_b.add(j)
        out[i] = identified[j]
    return out


def ape(sys_v: float | None, true_v: float | None) -> float | None:
    if sys_v is None or not true_v:
        return None
    return abs(sys_v - true_v) / true_v


def _mape_bar(name: str, limit: float, errors: list[float], n_sample: int) -> Bar:
    if not errors:
        return Bar(name, f"within {limit:.0%}", "no matched sample", None, f"0 of {n_sample} sample rows matched")
    mape = statistics.mean(errors)
    within = sum(e <= limit for e in errors) / len(errors)
    return Bar(name, f"within {limit:.0%}", f"MAPE {mape:.1%}", mape <= limit,
               f"{len(errors)} of {n_sample} sample rows matched; {within:.0%} individually within bar")


def score_books(truth: list[dict], packet: dict) -> list[Bar]:
    books = [b for b in packet["books"] if not b.get("excluded")]
    bars = []
    true_count = len(truth)
    sys_count = packet["totals"]["book_count"]
    err = abs(sys_count - true_count) / true_count if true_count else None
    bars.append(Bar("Book count", "within 5%", f"{sys_count} vs {true_count} true",
                    err is not None and err <= 0.05, f"error {err:.1%}" if err is not None else ""))

    matched = match_books(truth, books)
    legible = [i for i, t in enumerate(truth) if t.get("legible", "").lower() in ("y", "yes", "1", "true")]
    correct = sum(1 for i in legible if i in matched)
    identified = [b for b in books if b.get("status") == "identified"]
    all_titles = [t["title"] for t in truth if t.get("title")]
    wrong = [b for b in identified if not any(_title_score(b["title"], t) >= TITLE_MATCH for t in all_titles)]
    rate = correct / len(legible) if legible else 0
    wrong_rate = len(wrong) / len(identified) if identified else 0
    bars.append(Bar("Title identification", ">=70% correct, <=3% confidently wrong",
                    f"{rate:.0%} correct, {wrong_rate:.1%} wrong", rate >= 0.70 and wrong_rate <= 0.03,
                    f"{correct}/{len(legible)} legible spines; wrong: {', '.join(b['title'] for b in wrong[:5])}"))

    dims = [i for i, t in enumerate(truth) if _num(t.get("height_cm"))]
    h_err = [e for i in dims if i in matched for e in [ape(matched[i].get("spine_height_cm"), _num(truth[i]["height_cm"]))] if e is not None]
    t_err = [e for i in dims if i in matched for e in [ape(matched[i].get("spine_thickness_cm"), _num(truth[i]["thickness_cm"]))] if e is not None]
    bars.append(_mape_bar("Spine height", 0.15, h_err, len(dims)))
    bars.append(_mape_bar("Spine thickness", 0.15, t_err, len(dims)))

    priced = [i for i, t in enumerate(truth) if _num(t.get("replacement_price")) or _num(t.get("used_price"))]
    r_err = [e for i in priced if i in matched for e in [ape((matched[i].get("replacement_cost") or {}).get("amount"), _num(truth[i].get("replacement_price")))] if e is not None]
    u_err = [e for i in priced if i in matched for e in [ape((matched[i].get("used_value") or {}).get("amount"), _num(truth[i].get("used_price")))] if e is not None]
    bars.append(_mape_bar("Book price (replacement)", 0.25, r_err, len(priced)))
    bars.append(_mape_bar("Book price (used)", 0.25, u_err, len(priced)))
    return bars


def score_items(truth: list[dict], packet: dict) -> Bar:
    items = list(packet["items"])
    found = 0
    for t in truth:
        best = max(
            ((fuzz.token_set_ratio(t.get("description", "").lower(), i.get("description", "").lower()), k)
             for k, i in enumerate(items) if i["category"] == t["category"]),
            default=(0, None),
        )
        if best[1] is not None and (best[0] >= ITEM_MATCH or not t.get("description")):
            found += 1
            items.pop(best[1])
    rate = found / len(truth) if truth else 0
    return Bar("Non-book items", ">=80% found, correct category", f"{rate:.0%}", rate >= 0.8 if truth else None,
               f"{found}/{len(truth)} found; {len(packet['items'])} reported")


def score_room(truth: dict[str, float], packet: dict) -> list[Bar]:
    room = packet["room"]
    out = []
    for key, name, limit in (("floor_area_m2", "Floor area", 0.10), ("wall_area_m2", "Wall area", 0.15)):
        e = ape(room.get(key), truth.get(key))
        out.append(Bar(name, f"within {limit:.0%}", f"{room.get(key)} vs {truth.get(key)} m2",
                       None if e is None else e <= limit, "" if e is None else f"error {e:.1%}"))
    return out


def score_time(packet: dict) -> Bar:
    t = next((m["latency_s"] for m in packet.get("metrics", []) if m["stage"] == "time_to_packet"), None)
    cost = next((m["cost_usd"] for m in packet.get("metrics", []) if m["stage"] == "time_to_packet"), None)
    return Bar("Time to packet", "< 300 s", f"{t} s" if t is not None else "n/a",
               None if t is None else t < 300, f"model cost ${cost}" if cost is not None else "")


def score(packet: dict, truth_dir: Path) -> list[Bar]:
    books = _read_csv(truth_dir / "books.csv")
    items = _read_csv(truth_dir / "items.csv")
    room = {r["key"]: _num(r["value"]) for r in _read_csv(truth_dir / "room.csv")}
    return score_books(books, packet) + [score_items(items, packet)] + score_room(room, packet) + [score_time(packet)]


def to_markdown(bars: list[Bar]) -> str:
    mark = {True: "PASS", False: "FAIL", None: "n/a"}
    lines = ["| Measure | Pass bar | System | Result | Detail |", "|---|---|---|---|---|"]
    lines += [f"| {b.measure} | {b.target} | {b.value} | {mark[b.passed]} | {b.detail} |" for b in bars]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packet", required=True, type=Path)
    ap.add_argument("--truth", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    table = to_markdown(score(packet, args.truth))
    print(table)
    if args.out:
        args.out.write_text(f"# Results for sweep {packet['sweep']['id']}\n\n{table}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
