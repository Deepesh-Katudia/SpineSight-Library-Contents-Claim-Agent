"""OpenRouter client for vision/text calls, traced in LangSmith with cost + latency."""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field

import httpx
from langsmith import traceable

from app.config import get_settings

log = logging.getLogger(__name__)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(RuntimeError):
    pass


@dataclass
class CallStats:
    """Accumulates per-stage latency, call count and cost for the packet's metrics block."""

    latency_s: dict[str, float] = field(default_factory=dict)
    calls: dict[str, int] = field(default_factory=dict)
    cost_usd: dict[str, float] = field(default_factory=dict)

    def record(self, stage: str, latency: float, cost: float = 0.0) -> None:
        self.latency_s[stage] = self.latency_s.get(stage, 0.0) + latency
        self.calls[stage] = self.calls.get(stage, 0) + 1
        self.cost_usd[stage] = self.cost_usd.get(stage, 0.0) + cost


def image_part(jpeg: bytes) -> dict:
    data = base64.b64encode(jpeg).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json(text: str) -> dict:
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise LLMError(f"model did not return JSON: {text[:200]}") from None


class OpenRouterClient:
    def __init__(self, stats: CallStats | None = None, client: httpx.AsyncClient | None = None):
        settings = get_settings()
        self._key = settings.openrouter_api_key
        self.vision_model = settings.openrouter_vision_model
        self.text_model = settings.openrouter_text_model
        self.stats = stats or CallStats()
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0))

    @traceable(run_type="llm", name="openrouter_json")
    async def json_call(
        self, stage: str, system: str, content: list[dict], model: str | None = None
    ) -> dict:
        if not self._key:
            raise LLMError("OPENROUTER_API_KEY is not set")
        body = {
            "model": model or self.vision_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "usage": {"include": True},
        }
        started = time.perf_counter()
        resp = await self._client.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {self._key}", "X-Title": "SpineSight"},
            json=body,
        )
        elapsed = time.perf_counter() - started
        if resp.status_code >= 400:
            raise LLMError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")
        payload = resp.json()
        cost = float((payload.get("usage") or {}).get("cost") or 0.0)
        self.stats.record(stage, elapsed, cost)
        text = payload["choices"][0]["message"]["content"] or ""
        return parse_json(text)

    async def aclose(self) -> None:
        await self._client.aclose()
