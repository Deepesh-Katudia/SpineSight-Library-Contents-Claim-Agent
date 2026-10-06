"""Open Library search: resolves spine text to a work / edition / ISBN. No prices."""

from __future__ import annotations

import httpx

from app.sources.catalog import CatalogCandidate
from app.sources.common import make_client

SEARCH_URL = "https://openlibrary.org/search.json"
FIELDS = "key,title,author_name,publisher,isbn,first_publish_year,edition_count"


def _parse(doc: dict) -> CatalogCandidate:
    isbns = doc.get("isbn") or []
    isbn13 = next((i for i in isbns if len(i) == 13), "")
    return CatalogCandidate(
        title=doc.get("title", ""),
        authors=tuple(doc.get("author_name") or ()),
        publisher=(doc.get("publisher") or [""])[0],
        isbn=isbn13 or (isbns[0] if isbns else ""),
        year=str(doc.get("first_publish_year") or ""),
        source="open_library",
        url=f"https://openlibrary.org{doc['key']}" if doc.get("key") else "",
        edition_count=int(doc.get("edition_count") or 0),
    )


async def search(
    title: str, author: str = "", client: httpx.AsyncClient | None = None, limit: int = 5
) -> list[CatalogCandidate]:
    if not title:
        return []
    params = {"title": title, "fields": FIELDS, "limit": str(limit)}
    if author:
        params["author"] = author
    owned = client is None
    client = client or make_client()
    try:
        resp = await client.get(SEARCH_URL, params=params)
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
    finally:
        if owned:
            await client.aclose()
    return [_parse(d) for d in docs]
