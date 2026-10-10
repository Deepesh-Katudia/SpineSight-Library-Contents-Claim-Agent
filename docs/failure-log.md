# Failure log

> **Scope.** No compliant sweep was recorded (see [assumptions-and-deviations.md](assumptions-and-deviations.md)).
> This log comes from the one development test run. Its numbers are copied from that run's packet,
> unedited. There is no ground truth for it, so none of this is an accuracy figure.

## Run
- Sweep id: `cca8408e71e8` · 2026-10-08 · device label `pan-test` · 187.7 s
- Cost per sweep: **$0.354** (OpenRouter usage, `packet.metrics[time_to_packet].cost_usd`)
- Time from end of sweep to packet: **63.0 s**

| Stage | Latency (s) | Model calls | Cost (USD) |
|---|---:|---:|---:|
| live_detect | 176.91 | 6 | 0.1094 |
| live_read | 493.65 | 30 | 0.2447 |
| drain_frames | 59.48 | 0 | 0 |
| identify | 0.01 | 0 | 0 |
| price_books | 2.37 | 0 | 0 |
| price_items | 0.00 | 0 | 0 |
| room | 0.00 | 0 | 0 |
| second_locale | 1.14 | 0 | 0 |
| **time_to_packet** | **63.0** | — | **0.354** |

`live_detect` and `live_read` are summed across 3 parallel frame workers during the sweep, so they
are larger than the sweep's wall-clock time.

## Three worst errors

| # | Error (measured in this run) | Root cause | What I would change |
|---|---|---|---|
| 1 | **0 of 150 spines measured.** Every spine is in review with "no metric scale for this spine". | No frame in the run gave a scale reference, so neither the A4 homography nor chained scale ever started. The format-prior fallback did not fill the gap either. Why it didn't fire was not established before the deadline. | Make the missing scale reference a blocking live hint ("put the A4 sheet on this shelf") before shelf capture continues. Add a test that a sweep with no reference still gets prior-based heights with conf 0.3. |
| 2 | **0 of 37 identified books priced.** Every identified book is "no replacement price found from any source". | Not verified. India pricing depends on eBay US listings that deliver to India, plus Google Books retail for IN. The eBay source was changed after this run (`sources/ebay.py`, with new tests), but **no new sweep was run, so there is no measured fix.** | Re-run the identified titles through the pricing stage alone and log each source's raw response, to find which filter drops them. |
| 3 | **Room not measured.** Packet note: "no wall was captured edge to edge with a planar reference". | The run did not capture each wall corner to corner with an A4 sheet or a door in the same frame. On an iPhone's main lens this is hard in a small room, and the browser cannot use the ultra-wide lens. | Measure from partial views: stitch wall frames with feature matching before the homography, or use ARKit depth in a native capture app. |

What worked as designed in the same run: 113 of 150 spines were logged as unidentified rather than
guessed (legibility 0.1–0.5, or no catalogue record), and 10 spines matching both *Head First Java*
and *Java* were held back as ambiguous rather than assigned.

## Known risks (from design and tests, not measured)
- **Spine boxes are axis-aligned.** Leaning books inflate their thickness. Fix: ask the detector for rotated quads, or fit minAreaRect on edges inside the box.
- **Pans over unreadable spines can undercount.** Consecutive frames of near-identical unreadable spines are treated as the same books. Mitigation: overlap with at least one legible spine.
- **Tracking needs overlap.** A fast pan with no overlap between keyframes starts a new row and double-counts. Mitigations: the client sharpness gate, the agent's "slow down" hints, and `track.MIN_ALIGN_SCORE`.
- **Prices are asking prices.** eBay Browse returns active listings, not sold prices, so used values lean high.
- **Google Books prices are usually e-book prices**, and replacement cost for India leans on them.

## With two more weeks
- Run the compliant sweep, collect ground truth, and score it with `eval/score.py`.
- Native iOS capture with ARKit LiDAR depth, for metric scale without the A4 sheet.
- Sold-listing data (eBay Marketplace Insights, or AbeBooks / BookFinder) for used values.
- An independent checker agent that re-reads a random 10% of spines and reports disagreement.
