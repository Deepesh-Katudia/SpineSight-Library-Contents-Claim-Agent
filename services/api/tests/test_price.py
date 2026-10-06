from app.sources.catalog import CatalogCandidate
from app.sources.common import SourcedPrice
from app.sources.fx import FxRate
from app.stages.price import BookSignals, Locale, apply_pricing, price_book

from .factories import NOW, book

IN = Locale("IN", "INR")
US = Locale("US", "USD")


def sp(amount, currency="USD", condition="used"):
    return SourcedPrice(amount, amount, amount, currency, "eBay EBAY_US", "https://ebay/x", NOW, 5, condition)


class FakeListings:
    def __init__(self, new=None, used=None):
        self.new, self.used, self.calls = new, used, []

    async def price(self, query="", gtin="", condition="used", country="US", **kw):
        self.calls.append((condition, country))
        return self.new if condition == "new" else self.used


class FakeFx:
    async def rate(self, base, quote):
        return FxRate(base, quote, 88.0, "2026-10-05", "https://fx", NOW)


def retail(amount=399.0, currency="INR"):
    return CatalogCandidate("Dune", ("Herbert",), "", "978", "1965", "google_books", "https://gb",
                            retail_amount=amount, retail_currency=currency, retail_url="https://play/x",
                            is_ebook_offer=True)


async def test_india_prefers_local_retail_over_converted_listing():
    res = await price_book(book("b1"), IN, FakeListings(new=sp(10), used=sp(4)), FakeFx(), retail(),
                           BookSignals(year="1990"), threshold=10000)

    assert res.replacement.amount == 399.0 and not res.replacement.converted
    assert "e-book" in res.replacement.source
    assert res.used.converted and res.used.amount == 352.0
    assert res.used.original_currency == "USD" and res.used.fx_rate == 88.0
    assert res.used.condition_assumed.startswith("good")


async def test_india_converts_when_no_local_price():
    res = await price_book(book("b1"), IN, FakeListings(new=sp(10), used=None), FakeFx(), None,
                           BookSignals(), threshold=10000)

    assert res.replacement.converted and res.replacement.amount == 880.0
    assert res.used.amount is None


async def test_us_uses_native_listing_unconverted():
    res = await price_book(book("b1"), US, FakeListings(new=sp(18, condition="new"), used=sp(7)), FakeFx(),
                           retail(9.99, "USD"), BookSignals(), threshold=500)

    assert res.replacement.amount == 18 and not res.replacement.converted
    assert res.used.amount == 7


async def test_no_price_anywhere_stays_empty():
    res = await price_book(book("b1"), IN, FakeListings(), FakeFx(), None, BookSignals(), 10000)
    priced = apply_pricing(book("b1"), res)

    assert priced.replacement_cost.amount is None and priced.status == "identified"


async def test_signed_copy_goes_to_appraisal_without_lookup():
    listings = FakeListings(new=sp(10))
    res = await price_book(book("b1"), IN, listings, FakeFx(), None,
                           BookSignals(user_notes=("this one is signed by the author",)), 10000)

    assert "signed" in res.appraisal_reason and listings.calls == []
    priced = apply_pricing(book("b1"), res)
    assert priced.status == "needs_appraisal" and priced.replacement_cost.amount is None


async def test_old_book_is_antiquarian():
    res = await price_book(book("b1"), IN, FakeListings(), FakeFx(), None, BookSignals(year="1921"), 10000)
    assert "antiquarian" in res.appraisal_reason


async def test_over_threshold_is_not_auto_priced():
    res = await price_book(book("b1"), IN, FakeListings(new=sp(300), used=sp(250)), FakeFx(), None,
                           BookSignals(), threshold=10000)
    assert "threshold" in res.appraisal_reason
    assert res.replacement.amount is None
