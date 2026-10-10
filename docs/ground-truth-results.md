# Ground truth and results

> **Not collected.** No compliant sweep was recorded (see
> [assumptions-and-deviations.md](assumptions-and-deviations.md)), so there is no ground truth and
> **no accuracy is claimed against any pass bar.** The development test run has no ground truth, so
> its counts are not reported here as results.

## How it would be produced

Copy `eval/ground_truth_template/` to `eval/ground_truth/` and fill it in from the real room:

- True book count, and hand-read titles for every legible spine: `books.csv`
- 20 hand-measured spines (tape, cm): same file, `height_cm` / `thickness_cm`
- 15 hand-checked prices (same source type: eBay listing medians and retail pages): `replacement_price` / `used_price`
- Non-book items: `items.csv`
- Room tape measurements: `room.csv`

Then score the sweep's packet against it. Accuracy is reported on **all** shelves in the sweep, not
a selected subset:

```bash
services/api/.venv/Scripts/python eval/score.py \
  --packet services/api/data/sweeps/<id>/claim_packet.json \
  --truth eval/ground_truth --out docs/ground-truth-results.md
```

The scorer is tested (`eval/test_score.py`).
