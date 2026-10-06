"""Catalogue candidate shared by Open Library and Google Books."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogCandidate:
    title: str
    authors: tuple[str, ...]
    publisher: str
    isbn: str
    year: str
    source: str
    url: str
    edition_count: int = 0
    # Google Books retail offer in the queried country, if any
    retail_amount: float | None = None
    retail_currency: str = ""
    retail_url: str = ""
    is_ebook_offer: bool = False
