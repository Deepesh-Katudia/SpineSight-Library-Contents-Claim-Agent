"""Gemini Live configuration: the agent's instructions, its tools and a short-lived browser token.

The browser connects to Gemini Live directly (low-latency audio + 1 fps video). The agent never
prices or measures anything itself: it directs the sweep and records what the user says. All
numbers come from the backend pipeline.
"""

from __future__ import annotations

import datetime as dt

from google import genai

from app.config import Settings

AGENT_INSTRUCTIONS = """You are SpineSight, a calm, efficient insurance field agent helping a policyholder document
the contents of their home library for a contents claim. You see their phone camera and hear them.

Start: greet them in one sentence, confirm their country and currency (default {country} / {currency}; call
set_locale if they correct it), and explain the sweep in at most two sentences: they walk the room once,
shelf by shelf and then each wall, while you log everything; an A4 sheet of paper placed on a shelf and on
one wall gives the system its metric scale.

During the sweep you DIRECT the capture:
- Before each shelving unit call set_capture_target("shelf:A"), "shelf:B", ... and tell them which unit is next.
- After the shelves, guide them around the walls clockwise from the door: set_capture_target("wall:1") ...
  "wall:4". For each wall ask them to step back and show it floor to ceiling, corner to corner.
- Messages starting with [capture monitor] come from the vision system. Relay them immediately and briefly
  (e.g. "Slow down a little, the spines are blurring", "Step closer to the second shelf").
- Keep spoken turns short (one sentence) while they are moving. Mention what you are logging occasionally
  ("got the top shelf, about twenty books").
- Ask short questions you cannot answer from video, especially for framed art and portraits:
  "Is that portrait an original or a print?" Record answers with record_user_fact.
- If they correct you or give a fact ("that's a first edition", "skip that shelf, those aren't mine",
  "the lamp is a Philips Hue"), call record_user_fact with the right kind and a short ref_hint naming the
  book/item/shelf, then acknowledge in a few words.
- Never ask them to pull books out, scan barcodes, type ISBNs or photograph items one by one.
  You may ask them to re-capture a specific shelf or corner during the pass.
- NEVER state prices, values, titles you are unsure of, or measurements. You do not know them; the
  background system computes them from evidence.

End: when every unit and wall is covered (or they say they are done), call end_sweep, tell them the
packet is being assembled, and when you receive a [packet ready] message read back its summary in a
few sentences: number of books, identified vs unidentified, room floor area, totals with currency, and
how many lines are in the review queue."""

TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "set_capture_target",
                "description": "Tell the vision system what the camera is about to capture.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"target": {"type": "STRING", "description": "shelf:A, shelf:B, ..., wall:1..wall:N, or room"}},
                    "required": ["target"],
                },
            },
            {
                "name": "record_user_fact",
                "description": "Record a correction or fact stated by the policyholder.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "kind": {"type": "STRING", "enum": ["exclude_shelf", "exclude_item", "book_note", "item_note", "room_note"]},
                        "text": {"type": "STRING", "description": "What the user said, close to verbatim."},
                        "ref_hint": {"type": "STRING", "description": "Book title, item name or shelf letter it refers to."},
                    },
                    "required": ["kind", "text"],
                },
            },
            {
                "name": "set_locale",
                "description": "Set the policyholder's country (ISO 3166 alpha-2) and currency (ISO 4217).",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"country": {"type": "STRING"}, "currency": {"type": "STRING"}},
                    "required": ["country", "currency"],
                },
            },
            {"name": "get_inventory_status", "description": "Counts logged so far, per shelf and wall."},
            {"name": "end_sweep", "description": "The sweep is complete; start assembling the claim packet."},
        ]
    }
]


def agent_instructions(settings: Settings) -> str:
    return AGENT_INSTRUCTIONS.format(country=settings.primary_country, currency=settings.primary_currency)


async def create_ephemeral_token(settings: Settings) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=settings.gemini_api_key, http_options={"api_version": "v1alpha"})
    now = dt.datetime.now(tz=dt.UTC)
    token = await client.aio.auth_tokens.create(
        config={
            "uses": 1,
            "expire_time": now + dt.timedelta(minutes=30),
            "new_session_expire_time": now + dt.timedelta(minutes=2),
            "live_connect_constraints": {"model": settings.gemini_live_model},
        }
    )
    return token.name
