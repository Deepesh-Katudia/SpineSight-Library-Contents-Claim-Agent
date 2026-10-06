"""Shared helpers for external sources."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
USER_AGENT = "SpineSight/0.1 (contents-claim research tool)"


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})


@dataclass(frozen=True)
class Listing:
    """One observed price on a retrievable page."""

    amount: float
    currency: str
    url: str
    title: str
    condition: str


@dataclass(frozen=True)
class SourcedPrice:
    """A price aggregated from listings, with the evidence needed to trace it."""

    amount: float
    low: float
    high: float
    currency: str
    source: str
    url: str
    retrieved_at: str
    sample_size: int
    condition: str


def summarize_listings(
    listings: list[Listing], source: str, condition: str, retrieved_at: str
) -> SourcedPrice | None:
    """Median of same-currency listings; url points to the listing closest to the median."""
    if not listings:
        return None
    currency = listings[0].currency
    same = [x for x in listings if x.currency == currency]
    amounts = sorted(x.amount for x in same)
    median = statistics.median(amounts)
    closest = min(same, key=lambda x: abs(x.amount - median))
    return SourcedPrice(
        amount=round(median, 2),
        low=amounts[0],
        high=amounts[-1],
        currency=currency,
        source=f"{source} (median of {len(same)} listings)",
        url=closest.url,
        retrieved_at=retrieved_at,
        sample_size=len(same),
        condition=condition,
    )
