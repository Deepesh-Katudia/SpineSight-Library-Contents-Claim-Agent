"""Stage 9: assemble the claim packet.

Totals are computed here, in code, from the line items. No language model touches this.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.schema.claim_packet import (
    Book,
    ClaimPacket,
    Item,
    ReviewEntry,
    Room,
    StageMetric,
    Sweep,
    Totals,
)

M2_TO_FT2 = 10.7639
ID_CONFIDENCE_REVIEW = 0.9
ITEM_CONFIDENCE_REVIEW = 0.7
ROOM_CONFIDENCE_REVIEW = 0.6


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def finalize_room(room: Room) -> Room:
    """Fill derived areas (ft²) from the metric figures without inventing missing ones."""
    return room.model_copy(
        update={
            "floor_area_ft2": _round(room.floor_area_m2 and room.floor_area_m2 * M2_TO_FT2),
            "wall_area_ft2": _round(room.wall_area_m2 and room.wall_area_m2 * M2_TO_FT2),
            "shelved_wall_area_ft2": _round(
                room.shelved_wall_area_m2 and room.shelved_wall_area_m2 * M2_TO_FT2
            ),
        }
    )


def book_counts_toward_totals(book: Book) -> bool:
    return book.status == "identified" and not book.excluded


def item_counts_toward_totals(item: Item) -> bool:
    return item.status in ("priced", "range") and not item.excluded


def shelf_run_cm(book: Book) -> float:
    """Linear shelf length a book occupies: thickness when upright, height when lying flat."""
    if book.excluded:
        return 0.0
    if book.orientation == "flat":
        return book.spine_height_cm or 0.0
    return book.spine_thickness_cm or 0.0


def compute_totals(books: list[Book], items: list[Item], currency: str) -> Totals:
    counted_books = [b for b in books if book_counts_toward_totals(b)]
    counted_items = [i for i in items if item_counts_toward_totals(i)]

    books_replacement = sum(b.replacement_cost.amount or 0 for b in counted_books)
    books_used = sum(b.used_value.amount or 0 for b in counted_books)
    items_low = sum(i.replacement_cost.low or 0 for i in counted_items)
    items_high = sum(i.replacement_cost.high or 0 for i in counted_items)

    excluded_books = [
        b for b in books if not book_counts_toward_totals(b) or b.replacement_cost.amount is None
    ]
    excluded_items = [
        i for i in items if not item_counts_toward_totals(i) or i.replacement_cost.low is None
    ]

    owned_books = [b for b in books if not b.excluded]
    return Totals(
        book_count=len(owned_books),
        books_identified=sum(1 for b in owned_books if b.status == "identified"),
        books_unidentified=sum(1 for b in owned_books if b.status == "unidentified"),
        books_needs_appraisal=sum(1 for b in owned_books if b.status == "needs_appraisal"),
        shelf_run_m=round(sum(shelf_run_cm(b) for b in books) / 100, 2),
        books_replacement_cost=round(books_replacement, 2),
        books_used_value=round(books_used, 2),
        items_replacement_cost_low=round(items_low, 2),
        items_replacement_cost_high=round(items_high, 2),
        excluded_from_totals=len(excluded_books) + len(excluded_items),
        currency=currency,
    )


def _book_reasons(book: Book) -> Iterable[str]:
    if book.excluded:
        yield "excluded by policyholder: " + "; ".join(book.user_notes or ["no reason given"])
        return
    if book.status == "unidentified":
        why = book.unidentified_reason or "spine unreadable or no confident catalogue match"
        yield f"unidentified: {why}; logged with dimensions only"
    if book.status == "needs_appraisal":
        yield f"needs human appraisal: {book.appraisal_reason or 'flagged'}"
    if book.status == "identified":
        if book.id_confidence < ID_CONFIDENCE_REVIEW:
            yield f"identification confidence {book.id_confidence:.2f} below {ID_CONFIDENCE_REVIEW}"
        if book.replacement_cost.amount is None:
            yield "no replacement price found from any source; excluded from totals"
        elif book.replacement_cost.converted:
            yield (
                f"replacement price converted from {book.replacement_cost.original_currency}; "
                "no local listing"
            )
        if book.used_value.amount is None:
            yield "no used-market price found"
    if book.spine_height_cm is None or book.spine_thickness_cm is None:
        yield "no metric scale for this spine; dimensions missing"


def _item_reasons(item: Item) -> Iterable[str]:
    if item.excluded:
        yield "excluded by policyholder"
        return
    if item.status == "needs_appraisal":
        yield "art / high-value item routed to human appraisal; not auto-priced"
    if item.status == "unpriced":
        yield "no sourced replacement price found; excluded from totals"
    if item.status == "range" and not item.brand_model:
        yield "brand/model not legible; priced as a sourced range"
    if item.confidence < ITEM_CONFIDENCE_REVIEW:
        yield f"classification confidence {item.confidence:.2f} below {ITEM_CONFIDENCE_REVIEW}"


def build_review_queue(room: Room, books: list[Book], items: list[Item]) -> list[ReviewEntry]:
    queue: list[ReviewEntry] = []
    if room.confidence < ROOM_CONFIDENCE_REVIEW:
        queue.append(
            ReviewEntry(
                ref_id="room",
                reason=f"room measurement confidence {room.confidence:.2f} ({room.scale_method or 'no scale'})",
            )
        )
    for book in books:
        queue.extend(ReviewEntry(ref_id=book.id, reason=r) for r in _book_reasons(book))
    for item in items:
        queue.extend(ReviewEntry(ref_id=item.id, reason=r) for r in _item_reasons(item))
    return queue


def build_packet(
    sweep: Sweep,
    room: Room,
    books: list[Book],
    items: list[Item],
    metrics: list[StageMetric] | None = None,
) -> ClaimPacket:
    ordered_books = sorted(books, key=lambda b: (b.shelf, b.position))
    final_room = finalize_room(room)
    return ClaimPacket(
        sweep=sweep,
        room=final_room,
        books=ordered_books,
        items=items,
        totals=compute_totals(ordered_books, items, sweep.currency),
        review_queue=build_review_queue(final_room, ordered_books, items),
        metrics=metrics or [],
    )
