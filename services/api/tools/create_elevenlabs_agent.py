"""Create or update the SpineSight ElevenLabs voice agent from app/live.py.

    python tools/create_elevenlabs_agent.py

Reads ELEVENLABS_API_KEY (and ELEVENLABS_AGENT_ID, ELEVENLABS_LLM) from .env. Client tools are matched
by name, so re-running updates them in place instead of creating duplicates. With no ELEVENLABS_AGENT_ID
it creates a new agent and prints the id to put in .env; with one it updates that agent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.live import AGENT_FIRST_MESSAGE, AGENT_INSTRUCTIONS, CLIENT_TOOLS, ELEVENLABS_API  # noqa: E402

AGENT_NAME = "SpineSight field agent"


def existing_tools(api: httpx.Client) -> dict[str, str]:
    """Tool name -> id for every client tool in the workspace."""
    found: dict[str, str] = {}
    cursor = None
    while True:
        resp = api.get("/convai/tools", params={"cursor": cursor} if cursor else None)
        resp.raise_for_status()
        body = resp.json()
        for tool in body.get("tools", []):
            name = (tool.get("tool_config") or {}).get("name")
            if name:
                found[name] = tool["id"]
        cursor = body.get("next_cursor")
        if not body.get("has_more") or not cursor:
            return found


def upsert_tools(api: httpx.Client) -> list[str]:
    have = existing_tools(api)
    ids = []
    for config in CLIENT_TOOLS:
        name = config["name"]
        if name in have:
            api.patch(f"/convai/tools/{have[name]}", json={"tool_config": config}).raise_for_status()
            ids.append(have[name])
            print(f"updated tool {name}")
        else:
            resp = api.post("/convai/tools", json={"tool_config": config})
            resp.raise_for_status()
            ids.append(resp.json()["id"])
            print(f"created tool {name}")
    return ids


def agent_body(tool_ids: list[str], llm: str) -> dict:
    return {
        "name": AGENT_NAME,
        "conversation_config": {
            "agent": {
                "first_message": AGENT_FIRST_MESSAGE,
                "language": "en",
                "prompt": {"prompt": AGENT_INSTRUCTIONS, "llm": llm, "tool_ids": tool_ids},
            },
        },
    }


def main() -> int:
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        print("ELEVENLABS_API_KEY is not set in .env", file=sys.stderr)
        return 1
    with httpx.Client(base_url=ELEVENLABS_API, headers={"xi-api-key": settings.elevenlabs_api_key}, timeout=30) as api:
        body = agent_body(upsert_tools(api), settings.elevenlabs_llm)
        if settings.elevenlabs_agent_id:
            api.patch(f"/convai/agents/{settings.elevenlabs_agent_id}", json=body).raise_for_status()
            print(f"updated agent {settings.elevenlabs_agent_id}")
        else:
            resp = api.post("/convai/agents/create", json=body)
            resp.raise_for_status()
            print(f"created agent. Add this line to .env:\nELEVENLABS_AGENT_ID={resp.json()['agent_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
