"""FX conversion via Frankfurter (ECB reference rates, no key)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.sources.common import make_client, now_iso

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"


@dataclass(frozen=True)
class FxRate:
    base: str
    quote: str
    rate: float
    rate_date: str
    url: str
    retrieved_at: str
    source: str = "Frankfurter (ECB reference rate)"


class FxService:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._cache: dict[tuple[str, str], FxRate] = {}

    async def rate(self, base: str, quote: str) -> FxRate:
        base, quote = base.upper(), quote.upper()
        if base == quote:
            return FxRate(base, quote, 1.0, "", "", now_iso(), source="identity")
        key = (base, quote)
        if key not in self._cache:
            self._cache[key] = await self._fetch(base, quote)
        return self._cache[key]

    async def _fetch(self, base: str, quote: str) -> FxRate:
        params = {"base": base, "symbols": quote}
        client = self._client or make_client()
        try:
            resp = await client.get(FRANKFURTER_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._client is None:
                await client.aclose()
        rate = float(data["rates"][quote])
        url = f"{FRANKFURTER_URL}?base={base}&symbols={quote}"
        return FxRate(base, quote, rate, data.get("date", ""), url, now_iso())
