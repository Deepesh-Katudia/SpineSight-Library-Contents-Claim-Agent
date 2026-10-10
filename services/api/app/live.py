"""ElevenLabs voice agent: the agent's instructions, its client tools and a short-lived browser token.

The browser talks to the ElevenLabs agent directly over WebRTC (speech in, speech out, barge-in).
The agent hears the user but does not see the camera: the vision pipeline tells it what it needs
through [capture monitor] messages. It never prices or measures anything itself; it directs the
sweep and records what the user says. All numbers come from the backend pipeline.

`tools/create_elevenlabs_agent.py` creates or updates the agent from AGENT_INSTRUCTIONS and
CLIENT_TOOLS, so the agent's configuration lives in this repository, not only in a dashboard.
"""

from __future__ import annotations

import httpx

from app.config import Settings

ELEVENLABS_API = "https://api.elevenlabs.io/v1"

AGENT_FIRST_MESSAGE = (
    "Hi, I'm SpineSight. I'll help you document your library for the claim. "
    "Which country are you in, so I price everything in the right currency?"
)

AGENT_INSTRUCTIONS = """You are SpineSight, a calm, efficient insurance field agent helping a policyholder document
the contents of their home library for a contents claim. You hear them while they walk the room with their
phone camera on. You cannot see the camera yourself: a vision system watches it and sends you messages.

Start: the first message you receive starting with [session start] gives the default country and currency.
Confirm them in one sentence (call set_locale if the user corrects them), then explain the sweep in at most two
sentences: they walk the room once, shelf by shelf and then each wall, while you log everything; an A4 sheet of
paper placed on a shelf and on one wall gives the system its metric scale.

During the sweep you DIRECT the capture:
- Before each shelving unit call set_capture_target with "shelf:A", "shelf:B", ... and tell them which unit is next.
- After the shelves, guide them around the walls clockwise from the door: set_capture_target "wall:1" ... "wall:4".
  For each wall ask them to step back and show it floor to ceiling, corner to corner.
- Messages starting with [capture monitor] come from the vision system. Relay them immediately and briefly
  (e.g. "Slow down a little, the spines are blurring", "Step closer to the second shelf").
- Call get_inventory_status now and then and mention what is being logged ("got the top shelf, about twenty books").
- Keep spoken turns short (one sentence) while they are moving.
- Ask short questions the camera cannot answer, especially for framed art and portraits:
  "Is that portrait an original or a print?" Record answers with record_user_fact.
- If they correct you or give a fact ("that's a first edition", "skip that shelf, those aren't mine",
  "the lamp is a Philips Hue"), call record_user_fact with the right kind and a short ref_hint naming the
  book, item or shelf, then acknowledge in a few words.
- Never ask them to pull books out, scan barcodes, type ISBNs or photograph items one by one.
  You may ask them to re-capture a specific shelf or corner during the pass.
- NEVER state prices, values, titles or measurements yourself. You do not know them; the background system
  computes them from evidence.

End: when every unit and wall is covered (or they say they are done), call end_sweep, tell them the packet is
being assembled, and when you receive a [packet ready] message read back its summary in a few sentences: number
of books, identified vs unidentified, room floor area, totals with currency, and how many lines are in the review
queue."""


def _client_tool(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {
        "type": "client",
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
        "expects_response": True,
        "response_timeout_secs": 20,
    }


CLIENT_TOOLS = [
    _client_tool(
        "set_capture_target",
        "Tell the vision system what the camera is about to capture.",
        {"target": {"type": "string", "description": "shelf:A, shelf:B, ..., wall:1..wall:N, or room"}},
        ["target"],
    ),
    _client_tool(
        "record_user_fact",
        "Record a correction or fact stated by the policyholder.",
        {
            "kind": {"type": "string", "description": "One of exclude_shelf, exclude_item, book_note, item_note, room_note",
                     "enum": ["exclude_shelf", "exclude_item", "book_note", "item_note", "room_note"]},
            "text": {"type": "string", "description": "What the user said, close to verbatim."},
            "ref_hint": {"type": "string", "description": "Book title, item name or shelf letter it refers to."},
        },
        ["kind", "text"],
    ),
    _client_tool(
        "set_locale",
        "Set the policyholder's country and currency.",
        {
            "country": {"type": "string", "description": "ISO 3166 alpha-2 country code, e.g. IN or US"},
            "currency": {"type": "string", "description": "ISO 4217 currency code, e.g. INR or USD"},
        },
        ["country", "currency"],
    ),
    _client_tool("get_inventory_status", "Counts logged so far, per shelf and wall."),
    _client_tool("end_sweep", "The sweep is complete; start assembling the claim packet."),
]


async def conversation_token(settings: Settings, client: httpx.AsyncClient) -> str:
    """A single-use WebRTC token for the browser, so the ElevenLabs API key never leaves the server."""
    if not (settings.elevenlabs_api_key and settings.elevenlabs_agent_id):
        raise RuntimeError("ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID must both be set")
    resp = await client.get(
        f"{ELEVENLABS_API}/convai/conversation/token",
        params={"agent_id": settings.elevenlabs_agent_id},
        headers={"xi-api-key": settings.elevenlabs_api_key},
    )
    resp.raise_for_status()
    return resp.json()["token"]
