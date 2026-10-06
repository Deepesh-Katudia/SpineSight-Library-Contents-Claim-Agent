"""Small builders for test data."""

from app.schema.claim_packet import Book, Item, ItemPrice, PriceQuote, Room, Sweep

NOW = "2026-10-06T10:00:00Z"


def quote(amount: float, **kw) -> PriceQuote:
    return PriceQuote(
        amount=amount,
        currency=kw.pop("currency", "INR"),
        source=kw.pop("source", "google_books"),
        url=kw.pop("url", "https://example.org/p"),
        retrieved_at=kw.pop("retrieved_at", NOW),
        **kw,
    )


def book(id_: str, **kw) -> Book:
    defaults = dict(
        status="identified",
        title="Dune",
        id_confidence=0.95,
        spine_height_cm=21.0,
        spine_thickness_cm=3.0,
        orientation="vertical",
        replacement_cost=quote(500),
        used_value=quote(200, source="ebay", condition_assumed="good"),
    )
    defaults.update(kw)
    return Book(id=id_, **defaults)


def item(id_: str, **kw) -> Item:
    defaults = dict(
        category="lamp",
        brand_model="IKEA HEKTAR",
        status="priced",
        confidence=0.9,
        replacement_cost=ItemPrice(
            low=1000, high=1500, currency="INR", source="ebay", url="https://e/x", retrieved_at=NOW
        ),
    )
    defaults.update(kw)
    return Item(id=id_, **defaults)


def sweep() -> Sweep:
    return Sweep(id="s1", captured_at=NOW, country="IN", currency="INR", duration_s=150)


def room(**kw) -> Room:
    defaults = dict(
        length_m=4.0,
        width_m=3.0,
        height_m=2.7,
        floor_area_m2=12.0,
        wall_area_m2=37.8,
        shelved_wall_area_m2=6.0,
        scale_method="a4_reference",
        confidence=0.8,
    )
    defaults.update(kw)
    return Room(**defaults)
