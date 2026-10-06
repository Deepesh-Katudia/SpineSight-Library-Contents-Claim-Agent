import pytest
from pydantic import ValidationError

from app.schema.claim_packet import Book, ItemPrice, PriceQuote
from app.stages.packet import build_packet, compute_totals

from .factories import NOW, book, item, quote, room, sweep


def test_totals_sum_only_identified_priced_books():
    books = [
        book("b1", replacement_cost=quote(500), used_value=quote(200)),
        book("b2", replacement_cost=quote(300), used_value=quote(100)),
        book("b3", status="unidentified", title="", replacement_cost=PriceQuote(), used_value=PriceQuote()),
        book("b4", status="needs_appraisal", appraisal_reason="signed"),
    ]
    totals = compute_totals(books, [], "INR")

    assert totals.book_count == 4
    assert totals.books_identified == 2
    assert totals.books_unidentified == 1
    assert totals.books_needs_appraisal == 1
    assert totals.books_replacement_cost == 800
    assert totals.books_used_value == 300
    assert totals.excluded_from_totals == 2


def test_identified_book_without_price_is_excluded_not_zeroed():
    books = [book("b1", replacement_cost=PriceQuote(), used_value=PriceQuote())]
    totals = compute_totals(books, [], "INR")

    assert totals.books_replacement_cost == 0
    assert totals.excluded_from_totals == 1


def test_user_excluded_book_is_not_counted():
    books = [book("b1"), book("b2", excluded=True, user_notes=["not mine"])]
    totals = compute_totals(books, [], "INR")

    assert totals.book_count == 1
    assert totals.books_replacement_cost == 500


def test_shelf_run_uses_thickness_upright_and_height_flat():
    books = [
        book("b1", spine_thickness_cm=3.0, orientation="vertical"),
        book("b2", spine_height_cm=24.0, orientation="flat"),
        book("b3", spine_thickness_cm=None),
    ]
    assert compute_totals(books, [], "INR").shelf_run_m == 0.27


def test_item_ranges_sum_low_and_high_and_skip_appraisal():
    items = [
        item("i1"),
        item("i2", status="needs_appraisal", category="framed_art", replacement_cost=ItemPrice()),
    ]
    totals = compute_totals([], items, "INR")

    assert totals.items_replacement_cost_low == 1000
    assert totals.items_replacement_cost_high == 1500
    assert totals.excluded_from_totals == 1


def test_price_without_source_cannot_exist():
    with pytest.raises(ValidationError):
        PriceQuote(amount=100, currency="INR", source="memory")
    with pytest.raises(ValidationError):
        ItemPrice(low=1, high=2, source="x")


def test_converted_price_requires_fx_evidence():
    with pytest.raises(ValidationError):
        PriceQuote(amount=1, source="s", url="u", retrieved_at=NOW, converted=True)


def test_review_queue_lists_every_unconfident_line():
    books = [
        book("b1", id_confidence=0.85),
        book("b2", status="unidentified", title="", replacement_cost=PriceQuote(), used_value=PriceQuote()),
        book("b3", replacement_cost=quote(10, converted=True, fx_rate=88.0, original_currency="USD", original_amount=10 / 88)),
    ]
    items = [item("i1", status="needs_appraisal", replacement_cost=ItemPrice(), category="framed_art")]
    packet = build_packet(sweep(), room(confidence=0.4), books, items)
    refs = {e.ref_id for e in packet.review_queue}

    assert refs == {"room", "b1", "b2", "b3", "i1"}


def test_packet_orders_books_and_fills_square_feet():
    packet = build_packet(
        sweep(), room(), [book("b2", shelf="A", position=2), book("b1", shelf="A", position=1)], []
    )
    assert [b.id for b in packet.books] == ["b1", "b2"]
    assert packet.room.floor_area_ft2 == pytest.approx(129.17, abs=0.01)


def test_unknown_room_dimensions_stay_empty():
    packet = build_packet(sweep(), room(floor_area_m2=None, wall_area_m2=None), [], [])
    assert packet.room.floor_area_ft2 is None
    assert packet.room.wall_area_ft2 is None


def test_book_contract_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Book(id="x", made_up_field=1)


def test_non_http_urls_are_dropped_and_price_rejected():
    assert PriceQuote(url="javascript:alert(1)").url == ""
    assert Book(id="x", catalog_url="data:text/html,hi").catalog_url == ""
    with pytest.raises(ValidationError):
        PriceQuote(amount=5, source="s", url="javascript:alert(1)", retrieved_at=NOW)
    assert ItemPrice(url="https://ebay.com/x").url == "https://ebay.com/x"
