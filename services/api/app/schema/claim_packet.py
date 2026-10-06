"""The claim packet output contract.

Every field from the brief's contract is present. Unknown values are ``None`` (an empty
field is correct when the system does not know). Extra fields are additive only.
"""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _http_only(value: str) -> str:
    """Third-party URLs are rendered as links: anything but http(s) is dropped (and a price
    without a usable URL is then rejected by the evidence check)."""
    return value if not value or urlparse(value).scheme in ("http", "https") else ""


HttpUrlStr = Annotated[str, AfterValidator(_http_only)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Sweep(_Model):
    id: str
    captured_at: str
    device: str = ""
    duration_s: float = 0
    country: str
    currency: str
    second_locale: dict[str, str] | None = None


class Room(_Model):
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    floor_area_m2: float | None = None
    wall_area_m2: float | None = None
    shelved_wall_area_m2: float | None = None
    floor_area_ft2: float | None = None
    wall_area_ft2: float | None = None
    shelved_wall_area_ft2: float | None = None
    shape: str = ""
    scale_method: str = ""
    confidence: float = 0
    frame_refs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PriceQuote(_Model):
    """One sourced price. A quote without url + retrieved_at cannot be constructed."""

    amount: float | None = None
    currency: str = ""
    source: str = ""
    url: HttpUrlStr = ""
    retrieved_at: str = ""
    converted: bool = False
    original_amount: float | None = None
    original_currency: str = ""
    fx_rate: float | None = None
    fx_source: str = ""
    condition_assumed: str = ""
    sample_size: int | None = None

    @model_validator(mode="after")
    def _evidence_required(self) -> "PriceQuote":
        if self.amount is not None and (not self.url or not self.retrieved_at or not self.source):
            raise ValueError("a price amount requires source, url and retrieved_at")
        if self.converted and (self.fx_rate is None or not self.original_currency):
            raise ValueError("a converted price must carry fx_rate and original_currency")
        return self


BookStatus = Literal["identified", "unidentified", "needs_appraisal"]


class Book(_Model):
    id: str
    shelf: str = ""
    position: int = 0
    frame_ref: str = ""
    frame_refs: list[str] = Field(default_factory=list)
    status: BookStatus = "unidentified"
    title: str = ""
    author: str = ""
    publisher: str = ""
    edition: str = ""
    isbn: str = ""
    spine_text_raw: str = ""
    orientation: Literal["vertical", "flat", "unknown"] = "unknown"
    spine_height_cm: float | None = None
    spine_thickness_cm: float | None = None
    id_confidence: float = 0
    catalog_source: str = ""
    catalog_url: HttpUrlStr = ""
    replacement_cost: PriceQuote = Field(default_factory=PriceQuote)
    used_value: PriceQuote = Field(default_factory=PriceQuote)
    appraisal_reason: str = ""
    unidentified_reason: str = ""
    user_notes: list[str] = Field(default_factory=list)
    excluded: bool = False


class Dimensions(_Model):
    w: float | None = None
    h: float | None = None
    d: float | None = None


class ItemPrice(_Model):
    low: float | None = None
    high: float | None = None
    currency: str = ""
    source: str = ""
    url: HttpUrlStr = ""
    retrieved_at: str = ""
    converted: bool = False
    fx_rate: float | None = None
    sample_size: int | None = None

    @model_validator(mode="after")
    def _evidence_required(self) -> "ItemPrice":
        has_amount = self.low is not None or self.high is not None
        if has_amount and (not self.url or not self.retrieved_at or not self.source):
            raise ValueError("an item price requires source, url and retrieved_at")
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError("low must not exceed high")
        return self


ItemStatus = Literal["priced", "range", "needs_appraisal", "unpriced"]


class Item(_Model):
    id: str
    category: str
    description: str = ""
    material: str = ""
    brand_model: str = ""
    frame_ref: str = ""
    frame_refs: list[str] = Field(default_factory=list)
    dimensions_cm: Dimensions = Field(default_factory=Dimensions)
    status: ItemStatus = "unpriced"
    replacement_cost: ItemPrice = Field(default_factory=ItemPrice)
    confidence: float = 0
    user_notes: list[str] = Field(default_factory=list)
    excluded: bool = False


class Totals(_Model):
    book_count: int = 0
    books_identified: int = 0
    books_unidentified: int = 0
    books_needs_appraisal: int = 0
    shelf_run_m: float = 0
    books_replacement_cost: float = 0
    books_used_value: float = 0
    items_replacement_cost_low: float = 0
    items_replacement_cost_high: float = 0
    excluded_from_totals: int = 0
    currency: str = ""


class ReviewEntry(_Model):
    ref_id: str
    reason: str


class StageMetric(_Model):
    stage: str
    latency_s: float
    calls: int = 0
    cost_usd: float = 0


class LocaleComparison(_Model):
    """The same book priced in a second country, proving locale is a setting."""

    book_id: str
    title: str
    country: str
    currency: str
    replacement_cost: PriceQuote = Field(default_factory=PriceQuote)
    used_value: PriceQuote = Field(default_factory=PriceQuote)
    appraisal_reason: str = ""


class ClaimPacket(_Model):
    sweep: Sweep
    room: Room
    books: list[Book]
    items: list[Item]
    totals: Totals
    review_queue: list[ReviewEntry]
    metrics: list[StageMetric] = Field(default_factory=list)
    second_locale: list[LocaleComparison] = Field(default_factory=list)
    unattached_notes: list[str] = Field(default_factory=list)
