# SpineSight — Library Contents Claim Agent

A live voice-and-vision insurance agent that inventories and values a home library in one continuous
camera sweep. The policyholder walks the room once while talking to the agent. The agent directs the
capture, and background stages identify, measure and price every book from its spine, plus every
non-book item and the room's surface areas. The output is a traceable claim packet
(`claim_packet.json` + HTML report).

```
apps/web/          Next.js 16 — landing page, /sweep live console (phone), /claims/[id] packet view
services/api/      FastAPI — per-frame vision pipeline, pricing, room geometry, packet assembly
eval/              score.py — scores a packet against hand-collected ground truth per pass bar
docs/              architecture note, failure log, ground-truth results, reference-app notes
```

## Quick start (under 15 minutes)

Prerequisites: Python 3.12, Node 22, and an HTTPS tunnel (e.g. `cloudflared`) for phone testing,
because iOS Safari only grants camera and microphone access over HTTPS.

```bash
# 1. secrets
cp .env.example .env            # fill in the keys listed below

# 2. API
cd services/api
python -m venv .venv
.venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                          # 85 offline tests, no keys needed
python tools/create_elevenlabs_agent.py   # once: creates the voice agent, prints ELEVENLABS_AGENT_ID for .env
uvicorn app.main:app --port 8000

# 3. Web (new terminal)
cd apps/web
cp .env.example .env.local      # API URL for the browser
npm install
npm run dev                     # http://localhost:3000
```

On a phone:

1. Tunnel both ports, e.g. `cloudflared tunnel --url http://localhost:3000` and `...:8000`.
2. Set `NEXT_PUBLIC_API_BASE_URL` to the API tunnel URL.
3. Add the web tunnel URL to `WEB_ORIGIN`.
4. Open the web URL in Safari and tap **Start sweep**.

`GET /health` shows which integrations are configured.

### Keys

| Variable | What for | Where |
|---|---|---|
| `ELEVENLABS_API_KEY` | Live voice agent (single-use WebRTC tokens are minted server-side) | elevenlabs.io → Settings → API keys |
| `ELEVENLABS_AGENT_ID` | The agent to talk to. Create it from this repo: `python services/api/tools/create_elevenlabs_agent.py` (re-run to update) | printed by that script |
| `OPENROUTER_API_KEY` | Detection + spine reading (`google/gemini-3.8-flash`) | openrouter.ai/keys |
| `GOOGLE_BOOKS_API_KEY` | Catalogue match + country retail prices | Google Cloud console → Books API |
| `EBAY_CLIENT_ID/SECRET` | New and used listing prices (Browse API) | developer.ebay.com |
| `SUPABASE_URL/SERVICE_ROLE_KEY` | Optional: Postgres rows, event log (raw VLM outputs, transcripts) + Storage mirror of frames; falls back to local files. Run `services/api/supabase/schema.sql` | supabase.com |
| `LANGSMITH_API_KEY` | Optional: traces of every model call | smith.langchain.com |

Open Library and Frankfurter (ECB foreign-exchange rates) need no key.

## How a sweep works

1. **Greeting.** The agent greets the user, confirms the country and currency (default IN/INR), and asks them to place one A4 sheet on a shelf and one on a wall.
2. **Shelves.** The agent calls `set_capture_target("shelf:A")` for each shelving unit. The phone uploads a sharp keyframe about every 0.7 s. Each frame goes through detect → read → track → measure, and the inventory streams back over SSE.
3. **Capture monitor.** When frames are blurry, glary, unreadable or have no scale reference, the vision pipeline emits hints. The browser injects them into the Live session as `[capture monitor] …`, and the agent says them to the user while they are still standing at the shelf.
4. **Walls.** The agent walks the user around `wall:1..4`. Each wall is measured from a homography against the A4 sheet on it, or else against the door frame.
5. **Corrections.** Spoken corrections ("skip that shelf", "that portrait is a print", "that one is signed") become `record_user_fact` tool calls.
6. **Packet.** `end_sweep` triggers the packet build: finish identification, price, measure the room, then assemble. The agent reads the summary back.

The architecture is in [docs/architecture.md](docs/architecture.md).

## Honesty rules (enforced in code, covered by tests)

- **No guessed titles.** A title is filled in only when spine legibility is ≥ 0.6 and the catalogue match is ≥ 0.82, with no ambiguous rival. Anything else is `unidentified`, with its dimensions recorded and an entry in the review queue.
- **Editions need evidence.** An edition or ISBN is set only when the publisher printed on the spine matches the catalogue record.
- **Prices need a source.** `PriceQuote` and `ItemPrice` refuse to hold an amount without a `source`, `url` and `retrieved_at`. Converted prices must carry the FX rate and original currency.
- **No price, no total.** A line with no price stays empty and is counted in `excluded_from_totals`.
- **Appraisal, not pricing.** Signed, first-edition, leather, pre-1950 or above-threshold books, and all art that the user has not called a print, go to `needs_appraisal` and are never auto-priced.
- **Totals come from code.** `stages/packet.py` sums the lines. No model output reaches a numeric field.
- **Every frame is saved.** Every `frame_ref` must exist on disk before the packet is written; otherwise packet assembly fails.

## Second locale

The packet's `second_locale` block re-prices the first 10 identified books for `SECOND_COUNTRY` and
`SECOND_CURRENCY` (US/USD by default) through the same code path. Locale is a setting, not a branch.

## Evaluation

```bash
services/api/.venv/Scripts/python eval/score.py \
  --packet services/api/data/sweeps/<id>/claim_packet.json \
  --truth eval/ground_truth --out docs/ground-truth-results.md
```

Copy `eval/ground_truth_template/` to `eval/ground_truth/` and fill it in from the real room before
tuning anything. `services/api/tools/replay.py` re-runs a recorded sweep video through the API for
regression checks. It is not used for the demo.

## Tools and models used

| Role | Tool |
|---|---|
| Live conversation | ElevenLabs Agents over WebRTC (LLM `gemini-2.5-flash`), configured from `app/live.py` |
| Detection and spine OCR | Gemini 3.8 Flash via OpenRouter |
| Geometry | OpenCV (homography, quad refinement) |
| Fuzzy matching | rapidfuzz |
| Catalogue and price sources | Google Books, Open Library, eBay Browse, Frankfurter |
| Storage | Supabase (Postgres + Storage) |
| Tracing | LangSmith |
| Frontend | Next.js 16, Tailwind 4, Motion, `@elevenlabs/client` |
| Coding assistance | AI coding tools were used during development |

## What was kept, changed and thrown away from the reference app

See [docs/reference-app-notes.md](docs/reference-app-notes.md).
