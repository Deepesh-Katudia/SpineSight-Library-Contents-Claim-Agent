"""eBay Browse API: active listings for new and used copies / items.

eBay has no India marketplace, so for country=IN we query EBAY_US restricted to listings that
deliver to India and convert to INR downstream (labelled ``converted``).
"""

from __future__ import annotations

import base64
import time

import httpx

from app.sources.common import Listing, SourcedPrice, make_client, now_iso, summarize_listings

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"

# eBay condition ids: 1000 New; 3000 Used; 4000 Very Good; 5000 Good; 6000 Acceptable
CONDITION_IDS = {"new": "1000", "used": "3000|4000|5000|6000"}
MARKETPLACE_BY_COUNTRY = {"US": "EBAY_US", "GB": "EBAY_GB", "DE": "EBAY_DE", "AU": "EBAY_AU", "CA": "EBAY_CA"}


def marketplace_for(country: str) -> tuple[str, bool]:
    """Return (marketplace id, is_native). Non-native countries fall back to EBAY_US."""
    native = MARKETPLACE_BY_COUNTRY.get(country.upper())
    return (native, True) if native else ("EBAY_US", False)


class EbayClient:
    def __init__(self, client_id: str, client_secret: str, client: httpx.AsyncClient | None = None):
        self._id = client_id
        self._secret = client_secret
        self._client = client
        self._token = ""
        self._token_expiry = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._id and self._secret)

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = make_client()
        return self._client

    async def _access_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        basic = base64.b64encode(f"{self._id}:{self._secret}".encode()).decode()
        http = await self._http()
        resp = await http.post(
            TOKEN_URL,
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": SCOPE},
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + float(payload.get("expires_in", 7200))
        return self._token

    async def listings(
        self,
        query: str = "",
        gtin: str = "",
        condition: str = "used",
        country: str = "US",
        category_ids: str = "",
        limit: int = 20,
    ) -> list[Listing]:
        if not self.configured or not (query or gtin):
            return []
        marketplace, native = marketplace_for(country)
        filters = [f"conditionIds:{{{CONDITION_IDS[condition]}}}", "buyingOptions:{FIXED_PRICE}"]
        if not native:
            filters.append(f"deliveryCountry:{country.upper()}")
        params = {"limit": str(limit), "filter": ",".join(filters)}
        if gtin:
            params["gtin"] = gtin
        else:
            params["q"] = query
        if category_ids:
            params["category_ids"] = category_ids
        http = await self._http()
        resp = await http.get(
            SEARCH_URL,
            params=params,
            headers={
                "Authorization": f"Bearer {await self._access_token()}",
                "X-EBAY-C-MARKETPLACE-ID": marketplace,
            },
        )
        resp.raise_for_status()
        return [
            Listing(
                amount=float(s["price"]["value"]),
                currency=s["price"]["currency"],
                url=s.get("itemWebUrl", ""),
                title=s.get("title", ""),
                condition=s.get("condition", condition),
            )
            for s in resp.json().get("itemSummaries", [])
            if s.get("price") and s.get("itemWebUrl")
        ]

    async def price(
        self, query: str = "", gtin: str = "", condition: str = "used", country: str = "US", **kw
    ) -> SourcedPrice | None:
        listings = await self.listings(query=query, gtin=gtin, condition=condition, country=country, **kw)
        marketplace, _ = marketplace_for(country)
        label = f"eBay {marketplace} active {condition} listings"
        return summarize_listings(listings, label, condition, now_iso())

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
