# Assumptions and deviations

This page states plainly where this submission falls short of the brief, and the assumptions made
where the brief was ambiguous. Nothing in this repository was fabricated to fill a gap. Where a
deliverable is missing, it says so.

## Deviations from the brief

| Requirement | What was delivered | Why |
|---|---|---|
| Real sweep: ≥ 60 books on ≥ 2 shelving units, ≥ 8 non-book items, one enclosed room | **Not done.** | The room available to me has no shelving units, and I could not get to a space with shelves before the deadline. |
| Deliverable 2: demo video | **Missing.** | No real sweep was recorded. |
| Deliverable 3: claim packet from the video's sweep | **Missing.** The only packet is from a development test run (`cca8408e71e8`, see below), and it is not the demo. | Same as above. |
| Deliverable 4: ground truth and results against the pass bars | **Missing.** No ground truth was collected, so no accuracy is claimed against any pass bar. | Ground truth needs the real room. `eval/score.py` and `eval/ground_truth_template/` are ready for it. |
| Deliverable 6: failure log | **Partial.** Written from the development test run, not from a scored sweep. | No scored sweep exists. |
| Reference app run first | **Not run.** `docs/reference-app-notes.md` comes from reading its code. | Time. |

The pipeline itself is complete and runs end to end: live voice agent, per-frame vision, tracking,
identification, pricing, room geometry and packet assembly. It is covered by 85 offline tests plus
2 tests for the scorer, and it was run on a phone over HTTPS tunnels.

## The development test run (not the demo)

Sweep `cca8408e71e8` (2026-10-08, device label `pan-test`, 187.7 s) was a pipeline test, not a
compliant sweep. What it produced, unedited:

- 150 spines detected; 37 identified, 113 logged as unidentified with no title guessed.
- 0 spines measured: no frame gave a metric scale reference.
- 0 books priced: no sourced price was found for any of the 37 identified books.
- Room not measured: no wall was captured edge to edge with a planar reference.
- 8 non-book items detected, all unpriced. 373 review-queue entries.

There is no ground truth for this run, so its counts are not accuracy figures. Details are in
[failure-log.md](failure-log.md).

## Assumptions made where the brief was ambiguous

- **Locale.** The primary locale is India / INR. The second locale is US / USD, priced through the same code path.
- **Metric scale.** An A4 sheet (21.0 × 29.7 cm) on a shelf and on a wall is the primary reference. Scale is carried along a shelf through books re-seen in overlapping frames. If no reference exists, the median upright spine is assumed to be a 21.6 cm trade paperback (confidence 0.3), and that line always goes to review.
- **Room without an A4 sheet on the wall.** A door is assumed to be the Indian standard, 90 × 210 cm. A room with more than 4 walls is reported as non-rectangular: wall area only, floor area left blank.
- **Replacement cost means new; used value means "good" condition.** eBay Browse returns asking prices for active listings, not sold prices, so used values lean high.
- **India prices.** India has no eBay marketplace, so prices come from eBay US listings that deliver to India, converted at the ECB reference rate and labelled `converted`. Google Books retail prices in India are usually for the e-book edition and are labelled as such.
- **Appraisal threshold.** Items above ₹10,000, plus signed, first-edition, leather-bound and pre-1950 books, and any art the user has not called a print, go to `needs_appraisal` and are never auto-priced.
- **Identification.** A title is assigned only when spine legibility is ≥ 0.6 and the catalogue match is ≥ 0.82, with no ambiguous rival. Otherwise the book is logged as unidentified. An identified book with
  confidence below 0.9 keeps its title but also goes to the review queue.
