"""Google Books: catalogue match plus country-specific retail price where Google sells it.

Google Books retail prices are almost always for the e-book edition. We keep that flag so
the pricing stage can label it honestly ("e-book equivalent") and prefer physical listings.
"""

from __future__ import annotations

import httpx

from app.sources.catalog import CatalogCandidate
from app.sources.common import make_client

VOLUMES_URL = "https://www.googleapis.com/books/v1/volumes"


def _isbn(info: dict) -> str:
    ids = {i.get("type"): i.get("identifier", "") for i in info.get("industryIdentifiers", [])}
    return ids.get("ISBN_13") or ids.get("ISBN_10") or ""


def _parse(item: dict) -> CatalogCandidate:
    info = item.get("volumeInfo", {})
    sale = item.get("saleInfo", {})
    retail = sale.get("retailPrice") or sale.get("listPrice") or {}
    amount = retail.get("amount")
    return CatalogCandidate(
        title=" ".join(x for x in (info.get("title", ""), info.get("subtitle", "")) if x),
        authors=tuple(info.get("authors") or ()),
        publisher=info.get("publisher", ""),
        isbn=_isbn(info),
        year=(info.get("publishedDate") or "")[:4],
        source="google_books",
        url=info.get("canonicalVolumeLink") or info.get("infoLink", ""),
        retail_amount=float(amount) if amount is not None else None,
        retail_currency=retail.get("currencyCode", ""),
        retail_url=sale.get("buyLink", ""),
        is_ebook_offer=bool(sale.get("isEbook")),
    )


def build_query(title: str, author: str = "", isbn: str = "") -> str:
    if isbn:
        return f"isbn:{isbn}"
    query = f'intitle:"{title}"'
    if author:
        query += f' inauthor:"{author}"'
    return query


async def search(
    title: str = "",
    author: str = "",
    isbn: str = "",
    country: str = "IN",
    api_key: str = "",
    client: httpx.AsyncClient | None = None,
    limit: int = 5,
) -> list[CatalogCandidate]:
    if not (title or isbn):
        return []
    params = {
        "q": build_query(title, author, isbn),
        "country": country,
        "maxResults": str(limit),
        "printType": "books",
    }
    if api_key:
        params["key"] = api_key
    owned = client is None
    client = client or make_client()
    try:
        resp = await client.get(VOLUMES_URL, params=params)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    finally:
        if owned:
            await client.aclose()
    return [_parse(i) for i in items]
