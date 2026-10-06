# Failure log

> To fill in after the real sweep. Keep it to one page and report the worst errors, not the easy ones.

## Run
- Sweep id: `…` · date · device · duration
- Cost per sweep: `$…` (from `packet.metrics[time_to_packet].cost_usd`)
- Latency per stage: copy the `metrics` table from the report (`live_detect`, `live_read`, `identify`, `price_books`, `price_items`, `room`, `packet`, `time_to_packet`)

## Three worst errors

| # | Error (measured) | Root cause | Fix tried | Result after fix |
|---|---|---|---|---|
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |

## Known risks going in (from design and tests, not yet measured)
- **Spine boxes are axis-aligned.** Leaning books inflate their thickness. Fix: ask the detector for rotated quads, or fit minAreaRect on edges inside the box.
- **Ambiguous pans over unreadable spines.** Consecutive frames of near-identical unreadable spines are treated as the same books (safe for a steady camera), so a true pan over them can undercount. Mitigation is overlap with at least one legible spine.
- **Tracking needs overlap.** A fast pan with no overlap between keyframes starts a new row and double-counts. Mitigations: the client sharpness gate, the agent's "slow down" hints, and the alignment threshold (`track.MIN_ALIGN_SCORE`).
- **Unreadable runs can align to the wrong place.** A long run of unreadable spines aligns only on aspect ratio and could merge with the wrong segment.
- **Prices are asking prices.** eBay Browse returns asking prices for active listings, not sold prices (Marketplace Insights is restricted), so used values lean high.
- **Google Books prices are usually e-book prices**, and replacement cost for India leans on them.
- **Room size depends on a full wall view.** It needs each wall seen corner to corner in one frame. In a small room on an iPhone's main lens this can be impossible; the ultra-wide lens is not exposed to the browser.

## With two more weeks
- Native iOS capture app with ARKit LiDAR depth, for metric scale without the A4 sheet.
- Sold-listing data (eBay Marketplace Insights, or AbeBooks / BookFinder) for used values.
- A second, independent checker agent that re-reads a random 10% of spines and reports disagreement.
