import httpx
import pytest
import respx

from app.config import Settings
from app.live import CLIENT_TOOLS, ELEVENLABS_API, conversation_token

TOKEN_URL = f"{ELEVENLABS_API}/convai/conversation/token"


@respx.mock
async def test_conversation_token_uses_server_key_and_agent_id():
    route = respx.get(TOKEN_URL).mock(return_value=httpx.Response(200, json={"token": "tok", "conversation_id": "c1"}))
    settings = Settings(_env_file=None, elevenlabs_api_key="xi-secret", elevenlabs_agent_id="agent_123")

    async with httpx.AsyncClient() as client:
        token = await conversation_token(settings, client)

    request = route.calls[0].request
    assert token == "tok"
    assert request.headers["xi-api-key"] == "xi-secret"
    assert request.url.params["agent_id"] == "agent_123"


async def test_conversation_token_requires_key_and_agent():
    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="ELEVENLABS"):
            await conversation_token(Settings(_env_file=None, elevenlabs_api_key="k"), client)


def test_client_tools_match_the_browser_handlers():
    # apps/web/lib/live-agent.ts implements exactly these client tools; names must match the agent config.
    assert {t["name"] for t in CLIENT_TOOLS} == {
        "set_capture_target", "record_user_fact", "set_locale", "get_inventory_status", "end_sweep",
    }
    assert all(t["type"] == "client" and t["expects_response"] for t in CLIENT_TOOLS)
