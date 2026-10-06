"""Long-lived service clients shared by all sweeps (created once at app startup)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import Settings
from app.eventlog import EventLog
from app.llm import OpenRouterClient
from app.repository import PacketRepository
from app.sources import google_books, open_library
from app.sources.catalog import CatalogCandidate
from app.sources.common import make_client
from app.sources.ebay import EbayClient
from app.sources.fx import FxService
from app.storage import FrameStore


@dataclass
class Deps:
    settings: Settings
    http: httpx.AsyncClient
    store: FrameStore
    events: EventLog
    packets: PacketRepository
    ebay: EbayClient
    fx: FxService

    def llm(self, stats) -> OpenRouterClient:
        return OpenRouterClient(stats=stats, client=self.http)

    async def catalog_search(self, title: str, author: str, country: str | None = None) -> list[CatalogCandidate]:
        """Google Books (with country retail offers) first, Open Library as a second opinion."""
        country = country or self.settings.primary_country
        found: list[CatalogCandidate] = []
        for search in (
            lambda: google_books.search(title=title, author=author, country=country,
                                        api_key=self.settings.google_books_api_key, client=self.http),
            lambda: open_library.search(title, author, client=self.http),
        ):
            try:
                found.extend(await search())
            except httpx.HTTPError:
                continue
        return found

    async def retail_offer(self, title: str, author: str, isbn: str, country: str) -> CatalogCandidate | None:
        try:
            cands = await google_books.search(title=title, author=author, isbn=isbn, country=country,
                                              api_key=self.settings.google_books_api_key, client=self.http)
        except httpx.HTTPError:
            return None
        return next((c for c in cands if c.retail_amount is not None), None)

    async def aclose(self) -> None:
        await self.http.aclose()


def build_deps(settings: Settings) -> Deps:
    http = make_client()
    http.timeout = httpx.Timeout(90.0, connect=10.0)
    return Deps(
        settings=settings,
        http=http,
        store=FrameStore(settings),
        events=EventLog(settings),
        packets=PacketRepository(settings),
        ebay=EbayClient(settings.ebay_client_id, settings.ebay_client_secret, http),
        fx=FxService(http),
    )
