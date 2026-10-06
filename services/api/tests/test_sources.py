import httpx
import respx

from app.sources import google_books, open_library
from app.sources.common import Listing, summarize_listings
from app.sources.ebay import EbayClient, SEARCH_URL, TOKEN_URL, marketplace_for
from app.sources.fx import FRANKFURTER_URL, FxService


@respx.mock
async def test_open_library_parses_isbn13_and_url():
    respx.get(open_library.SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={"docs": [{"key": "/works/OL1W", "title": "Dune", "author_name": ["Frank Herbert"],
                             "isbn": ["0441013597", "9780441013593"], "publisher": ["Ace"],
                             "first_publish_year": 1965, "edition_count": 120}]},
        )
    )
    async with httpx.AsyncClient() as client:
        cands = await open_library.search("Dune", "Herbert", client=client)

    assert cands[0].isbn == "9780441013593"
    assert cands[0].url == "https://openlibrary.org/works/OL1W"
    assert cands[0].authors == ("Frank Herbert",)


async def test_open_library_skips_empty_title():
    assert await open_library.search("") == []


@respx.mock
async def test_google_books_reads_country_retail_price():
    route = respx.get(google_books.VOLUMES_URL).mock(
        return_value=httpx.Response(
            200,
            json={"items": [{
                "volumeInfo": {"title": "Sapiens", "authors": ["Yuval Noah Harari"],
                               "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9780099590088"}],
                               "publishedDate": "2014-09-04", "canonicalVolumeLink": "https://books.google.com/x"},
                "saleInfo": {"country": "IN", "isEbook": True,
                             "retailPrice": {"amount": 399.0, "currencyCode": "INR"},
                             "buyLink": "https://play.google.com/store/books/details?id=x"},
            }]},
        )
    )
    async with httpx.AsyncClient() as client:
        cands = await google_books.search(title="Sapiens", country="IN", client=client)

    assert route.calls[0].request.url.params["country"] == "IN"
    assert cands[0].retail_amount == 399.0
    assert cands[0].retail_currency == "INR"
    assert cands[0].is_ebook_offer is True
    assert cands[0].year == "2014"


def test_google_books_query_prefers_isbn():
    assert google_books.build_query("Dune", "Herbert", "978") == "isbn:978"
    assert google_books.build_query("Dune", "Herbert") == 'intitle:"Dune" inauthor:"Herbert"'


@respx.mock
async def test_fx_rate_is_cached_and_sourced():
    route = respx.get(FRANKFURTER_URL).mock(
        return_value=httpx.Response(200, json={"date": "2026-10-05", "rates": {"INR": 88.5}})
    )
    async with httpx.AsyncClient() as client:
        fx = FxService(client)
        first = await fx.rate("USD", "INR")
        second = await fx.rate("usd", "inr")

    assert first.rate == 88.5 and second is first
    assert route.call_count == 1
    assert "frankfurter" in first.url


async def test_fx_identity_needs_no_call():
    assert (await FxService().rate("INR", "INR")).rate == 1.0


def test_marketplace_fallback_for_india():
    assert marketplace_for("US") == ("EBAY_US", True)
    assert marketplace_for("IN") == ("EBAY_US", False)


@respx.mock
async def test_ebay_used_price_median_with_delivery_filter_for_india():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 7200}))
    search = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"itemSummaries": [
            {"price": {"value": "5.00", "currency": "USD"}, "itemWebUrl": "https://ebay/a", "title": "a"},
            {"price": {"value": "9.00", "currency": "USD"}, "itemWebUrl": "https://ebay/b", "title": "b"},
            {"price": {"value": "20.00", "currency": "USD"}, "itemWebUrl": "https://ebay/c", "title": "c"},
        ]})
    )
    async with httpx.AsyncClient() as http:
        ebay = EbayClient("id", "secret", http)
        price = await ebay.price(gtin="9780441013593", condition="used", country="IN")

    req = search.calls[0].request
    assert "deliveryCountry:IN" in req.url.params["filter"]
    assert req.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
    assert price.amount == 9.0 and price.url == "https://ebay/b" and price.sample_size == 3


async def test_ebay_unconfigured_returns_nothing():
    assert await EbayClient("", "").price(query="dune") is None


def test_summarize_listings_empty():
    assert summarize_listings([], "x", "new", "t") is None
    one = summarize_listings([Listing(4, "USD", "u", "t", "new")], "x", "new", "now")
    assert one.amount == 4 and one.low == one.high == 4
