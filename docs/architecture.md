# Architecture (one page)

```
 iPhone Safari  (apps/web /sweep)
 ┌──────────────────────────────────────────────────────────────┐
 │ mic 16 kHz PCM ─┐                     ┌─ agent voice 24 kHz  │
 │ video 1 fps 768px┼──► Gemini Live ◄───┘   tool calls ──┐     │
 │                  │   (ephemeral token from API)         │     │
 │ keyframes ~1.4 fps, 1920px, client sharpness/glare gate │     │
 └────────┬─────────────────────────────────▲──────────────┼─────┘
          │ POST /frames                    │ SSE /events  │ POST /target /facts /finish
          ▼                                 │ (inventory,  ▼
 FastAPI (services/api)                     │  hints)
 ┌──────────────────────────────────────────┴───────────────────────────────┐
 │ per frame (3 workers)                                                      │
 │  ingest ─► detect (VLM boxes) ─► read (VLM, tiled crops) ─► track ─► measure │
 │    │                                                         │             │
 │    frames → disk + Supabase Storage        identify starts in background   │
 │ after end_sweep                                                            │
 │  identify ─► price books ─► price items ─► room ─► 2nd locale ─► packet    │
 │  Google Books / Open Library   eBay Browse + Google Books + ECB FX   (code)│
 └────────────────────────────────────────────────────────────────────────────┘
   claim_packet.json + report.html · Postgres rows · Mongo event log · LangSmith traces
```

## Which model does what

| Stage | Model / method | May output | May NOT output |
|---|---|---|---|
| Live agent | Gemini Live `gemini-3.8-live` | speech, tool calls (target, facts, end) | prices, sizes, titles it hasn't seen |
| Detect | Gemini 3.8 Flash (OpenRouter) | boxes for spines, shelf rows, objects, A4 corners, wall/door quads, blur/glare scores | text, sizes, prices |
| Read | Gemini 3.8 Flash | verbatim spine text, title/author/publisher **only if printed**, legibility | inferred titles |
| Track | rapidfuzz sequence alignment (code) | one identity per physical book across frames | — |
| Measure | OpenCV homography (code) | cm from pixels | — |
| Identify | Google Books + Open Library + fuzzy scoring (code) | work, and edition only with publisher evidence | — |
| Price | eBay Browse, Google Books saleInfo, Frankfurter (code) | sourced quotes | — |
| Packet | Python | totals, review queue | — |

## Where metric scale comes from

1. **A4 reference (primary).** The policyholder puts an A4 sheet (21.0 × 29.7 cm) on a shelf. The VLM gives its rough corners; OpenCV snaps them to the paper edges (Otsu threshold + polygon fit). A homography maps the pixels on that plane to cm, and spine boxes on the same shelf face are mapped through it.
2. **Chained scale.** When the pan moves past the sheet, books measured in an earlier frame and re-seen in this frame (matched by tracking) give a median cm-per-pixel. Overlapping frames carry the scale along the shelf.
3. **Format prior (fallback, conf 0.3).** The median upright spine is taken as a 21.6 cm trade paperback. This is used only when nothing else exists, and the line always goes to review.
4. **Room.** For each wall, the A4 sheet on that wall (or else the door frame, assuming the national standard door, 90 × 210 cm for India) gives a wall-plane homography. The wall's corners map to width × height. Opposite walls are averaged. Doors and windows are subtracted. Shelf fronts give the shelved wall area. A room with more than 4 walls is reported as non-rectangular: wall area only, and floor area left blank.

## Where prices come from

| Figure | Order of sources | Condition assumed |
|---|---|---|
| Book replacement | eBay new listings in a native marketplace → Google Books retail in the user's country (usually the e-book edition, labelled as such) → eBay US new listings, converted | new |
| Book used | eBay used listings (Good / Very Good / Acceptable), median | good |
| Item replacement | eBay new listings for brand/model (or a visible description), 25th–75th percentile range | new |
| FX | Frankfurter (ECB reference rate), with date and URL stored on the quote | — |

India has no eBay marketplace. India prices therefore use eBay US listings filtered to `deliveryCountry:IN` and are labelled `converted`.

Cost and latency per stage are written into `packet.metrics` (from OpenRouter usage cost and stage timers) and traced in LangSmith.
