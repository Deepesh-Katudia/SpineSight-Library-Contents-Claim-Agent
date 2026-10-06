"""Stage 7: price books at local market value.

Rules (from the brief):
* Every price carries source, url, retrieval date and assumed condition.
* No local price -> convert from another market and label it converted.
* No price at all -> leave empty; the packet stage excludes it from totals.
* Rare / signed / antiquarian / above threshold -> needs_appraisal, never auto-priced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.schema.claim_packet import Book, PriceQuote
from app.sources.catalog import CatalogCandidate
from app.sources.common import SourcedPrice, now_iso
from app.sources.ebay import marketplace_for
from app.sources.fx import FxRate

ANTIQUARIAN_BEFORE_YEAR = 1950
RARITY_KEYWORDS = ("signed", "first edition", "1st edition", "limited edition", "inscribed", "leather", "antique")
USED_CONDITION = "good (used; median of eBay Good/Very Good/Acceptable listings)"
NEW_CONDITION = "new"


class PriceSource(Protocol):
    async def price(
        self, query: str = "", gtin: str = "", condition: str = "used", country: str = "US", **kw
    ) -> SourcedPrice | None: ...


class FxSource(Protocol):
    async def rate(self, base: str, quote: str) -> FxRate: ...


class CatalogSource(Protocol):
    async def __call__(self, isbn: str, country: str) -> CatalogCandidate | None: ...


@dataclass(frozen=True)
class Locale:
    country: str
    currency: str


@dataclass(frozen=True)
class BookSignals:
    """Evidence gathered before pricing that may force human appraisal."""

    year: str = ""
    visual_flags: tuple[str, ...] = ()
    user_notes: tuple[str, ...] = ()


@dataclass
class PricingResult:
    replacement: PriceQuote = field(default_factory=PriceQuote)
    used: PriceQuote = field(default_factory=PriceQuote)
    appraisal_reason: str = ""


def appraisal_reason_from_signals(signals: BookSignals) -> str:
    text = " ".join(signals.visual_flags + signals.user_notes).lower()
    hits = [k for k in RARITY_KEYWORDS if k in text]
    if hits:
        return f"rarity signal: {', '.join(hits)}"
    if signals.year.isdigit() and int(signals.year) < ANTIQUARIAN_BEFORE_YEAR:
        return f"possible antiquarian edition (published {signals.year})"
    return ""


async def to_quote(
    price: SourcedPrice, target: Locale, fx: FxSource, condition: str
) -> PriceQuote:
    if price.currency.upper() == target.currency.upper():
        return PriceQuote(
            amount=price.amount,
            currency=target.currency,
            source=price.source,
            url=price.url,
            retrieved_at=price.retrieved_at,
            condition_assumed=condition,
            sample_size=price.sample_size,
        )
    rate = await fx.rate(price.currency, target.currency)
    return PriceQuote(
        amount=round(price.amount * rate.rate, 2),
        currency=target.currency,
        source=price.source,
        url=price.url,
        retrieved_at=price.retrieved_at,
        converted=True,
        original_amount=price.amount,
        original_currency=price.currency,
        fx_rate=rate.rate,
        fx_source=f"{rate.source} {rate.rate_date} {rate.url}".strip(),
        condition_assumed=condition,
        sample_size=price.sample_size,
    )


def google_retail_price(candidate: CatalogCandidate | None, target: Locale) -> SourcedPrice | None:
    if not candidate or candidate.retail_amount is None or not candidate.retail_currency:
        return None
    label = "Google Books retail" + (" (e-book edition as equivalent)" if candidate.is_ebook_offer else "")
    return SourcedPrice(
        amount=candidate.retail_amount,
        low=candidate.retail_amount,
        high=candidate.retail_amount,
        currency=candidate.retail_currency,
        source=f"{label}, {target.country}",
        url=candidate.retail_url or candidate.url,
        retrieved_at=now_iso(),
        sample_size=1,
        condition=NEW_CONDITION,
    )


def book_query(book: Book) -> str:
    return " ".join(x for x in (book.title, book.author) if x)


async def price_book(
    book: Book,
    target: Locale,
    listings: PriceSource,
    fx: FxSource,
    retail: CatalogCandidate | None,
    signals: BookSignals,
    threshold: float,
) -> PricingResult:
    reason = appraisal_reason_from_signals(signals)
    if reason:
        return PricingResult(appraisal_reason=reason)

    query, gtin = book_query(book), book.isbn
    _, native = marketplace_for(target.country)
    new_listing = await listings.price(query=query, gtin=gtin, condition="new", country=target.country)
    local_retail = google_retail_price(retail, target)

    # Preference: a local, unconverted price first; converted only when nothing local exists.
    replacement_src = None
    if native and new_listing:
        replacement_src = new_listing
    elif local_retail and local_retail.currency == target.currency:
        replacement_src = local_retail
    else:
        replacement_src = new_listing or local_retail

    used_listing = await listings.price(query=query, gtin=gtin, condition="used", country=target.country)

    result = PricingResult()
    if replacement_src:
        result.replacement = await to_quote(replacement_src, target, fx, NEW_CONDITION)
    if used_listing:
        result.used = await to_quote(used_listing, target, fx, USED_CONDITION)

    highest = max(result.replacement.amount or 0, result.used.amount or 0)
    if highest > threshold:
        return PricingResult(
            appraisal_reason=f"sourced price {highest:.0f} {target.currency} exceeds appraisal threshold {threshold:.0f}"
        )
    return result


def apply_pricing(book: Book, result: PricingResult) -> Book:
    if result.appraisal_reason:
        return book.model_copy(
            update={
                "status": "needs_appraisal",
                "appraisal_reason": result.appraisal_reason,
                "replacement_cost": PriceQuote(),
                "used_value": PriceQuote(),
            }
        )
    return book.model_copy(update={"replacement_cost": result.replacement, "used_value": result.used})
