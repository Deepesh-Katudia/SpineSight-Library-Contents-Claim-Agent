import pytest

from app.sources.common import Listing
from app.sources.fx import FxRate
from app.stages.items import ItemTracker, TrackedItem, measure_object, price_item, to_item
from app.stages.measure import scale_from_reference
from app.stages.observations import FrameObservation, ObjectObs, WallObs
from app.stages.price import Locale
from app.stages.room import assemble_room, measure_wall

from .factories import NOW

# 1 px == 1 cm: A4 sheet drawn at its true size
A4_1CM = ((100, 100), (121, 100), (121, 129.7), (100, 129.7))


def wall_obs(label, width_cm, height_cm=270, door=None, reference=A4_1CM, shelf_fronts=()):
    corners = ((0, 0), (width_cm, 0), (width_cm, height_cm), (0, height_cm))
    return FrameObservation(
        frame_ref=f"w{label}", t_ms=0, width=1000, height=1000, target=f"wall:{label}",
        reference=reference, wall=WallObs(corners=corners, door=door, shelf_fronts=shelf_fronts),
    )


def test_wall_measured_from_a4_on_wall():
    m = measure_wall(wall_obs("1", 400), "IN")
    assert m.width_m == pytest.approx(4.0) and m.height_m == pytest.approx(2.7)
    assert m.method == "a4_on_wall"


def test_wall_from_door_when_no_sheet_and_door_subtracted():
    door = ((200, 60), (290, 60), (290, 270), (200, 270))  # 90 x 210 px == IN standard door
    m = measure_wall(wall_obs("2", 300, door=door, reference=None), "IN")
    assert m.width_m == pytest.approx(3.0) and m.method == "door_standard"
    assert m.openings_m2 == pytest.approx(0.9 * 2.1)


def test_no_planar_reference_no_measurement():
    assert measure_wall(wall_obs("1", 400, reference=None), "IN") is None


def test_rectangular_room_from_four_walls():
    shelf = ((10, 50), (110, 50), (110, 250), (10, 250))  # 1 x 2 m shelving front
    walls = [measure_wall(wall_obs(str(i), w, shelf_fronts=(shelf,) if i == 1 else ()), "IN")
             for i, w in zip(range(1, 5), [400, 300, 404, 296])]
    room = assemble_room(walls)
    assert room.length_m == pytest.approx(4.02) and room.width_m == pytest.approx(2.98)
    assert room.floor_area_m2 == pytest.approx(4.02 * 2.98, abs=0.01)
    assert room.wall_area_m2 == pytest.approx(2 * (4.02 + 2.98) * 2.7, abs=0.01)
    assert room.shelved_wall_area_m2 == pytest.approx(2.0)
    assert room.shape == "rectangle" and room.confidence == pytest.approx(0.85)


def test_two_adjacent_walls_assume_rectangle_with_lower_confidence():
    room = assemble_room([measure_wall(wall_obs("1", 400), "IN"), measure_wall(wall_obs("2", 300), "IN")])
    assert room.floor_area_m2 == pytest.approx(12.0)
    assert room.confidence < 0.85 and room.notes


def test_missing_direction_leaves_floor_empty():
    room = assemble_room([measure_wall(wall_obs("1", 400), "IN")])
    assert room.floor_area_m2 is None and room.confidence <= 0.2


def test_no_walls():
    room = assemble_room([])
    assert room.floor_area_m2 is None and room.confidence == 0


def test_non_rectangular_room_reports_wall_area_only():
    walls = [measure_wall(wall_obs(str(i), 200), "IN") for i in range(1, 7)]
    room = assemble_room(walls)
    assert room.floor_area_m2 is None and room.wall_area_m2 == pytest.approx(12 * 2.7)
    assert "non-rectangular" in room.shape


# ---------- items ----------

class FakeListings:
    def __init__(self, amounts, currency="USD"):
        self.amounts, self.currency, self.calls = amounts, currency, []

    async def listings(self, query="", gtin="", condition="new", country="US", **kw):
        self.calls.append(query)
        return [Listing(a, self.currency, f"https://ebay/{a}", "t", "new") for a in self.amounts]


class FakeFx:
    async def rate(self, base, quote):
        return FxRate(base, quote, 1.0 if base == quote else 88.0, "d", "u", NOW)


def obj(category="lamp", description="brass floor lamp", brand="", conf=0.9):
    return ObjectObs(box=(100, 100, 150, 250), category=category, description=description, brand_model=brand, confidence=conf)


def test_item_tracker_dedupes_across_frames():
    tracker = ItemTracker()
    tracker.ingest("f1", [obj(), obj("rug", "persian rug")], None)
    tracker.ingest("f2", [obj(description="brass floor lamp, tall")], None)
    assert len(tracker.items) == 2


def test_item_dimensions_need_scale():
    assert measure_object(obj(), None).w is None
    dims = measure_object(obj(), scale_from_reference(A4_1CM))
    assert (dims.w, dims.h) == (50, 150)


async def test_art_goes_to_appraisal_unless_user_says_print():
    art = TrackedItem("it_1", "portrait", [("f1", obj("portrait", "oil portrait"), None)])
    status, price = await price_item(art, Locale("IN", "INR"), FakeListings([10, 20, 30]), FakeFx(), 10000)
    assert status == "needs_appraisal" and price.low is None

    art.user_notes.append("that's just a print")
    status, price = await price_item(art, Locale("IN", "INR"), FakeListings([10, 20, 30]), FakeFx(), 10000)
    assert status == "range" and price.converted


async def test_item_range_is_sourced_iqr_converted():
    t = TrackedItem("it_1", "lamp", [("f1", obj(), None)])
    status, price = await price_item(t, Locale("IN", "INR"), FakeListings([10, 20, 30, 40, 50]), FakeFx(), 10000)
    assert status == "range"
    assert price.low == pytest.approx(20 * 88) and price.high == pytest.approx(40 * 88)
    assert price.url.startswith("https://ebay/") and price.sample_size == 5


async def test_branded_item_is_priced_and_queries_model():
    src = FakeListings([100, 110, 120], currency="USD")
    t = TrackedItem("it_1", "coffee_machine", [("f1", obj("coffee_machine", "espresso", "De'Longhi EC685"), None)])
    status, price = await price_item(t, Locale("US", "USD"), src, FakeFx(), 1000)
    assert status == "priced" and src.calls == ["De'Longhi EC685"] and not price.converted


async def test_too_few_listings_is_unpriced_and_expensive_is_appraisal():
    t = TrackedItem("it_1", "lamp", [("f1", obj(), None)])
    assert (await price_item(t, Locale("US", "USD"), FakeListings([1, 2]), FakeFx(), 1000))[0] == "unpriced"
    assert (await price_item(t, Locale("US", "USD"), FakeListings([5000, 6000, 7000]), FakeFx(), 1000))[0] == "needs_appraisal"


def test_to_item_contract():
    t = TrackedItem("it_1", "lamp", [("f1", obj(), None), ("f2", obj(conf=0.95), None)])
    item = to_item(t, "unpriced", __import__("app.schema.claim_packet", fromlist=["ItemPrice"]).ItemPrice())
    assert item.frame_refs == ["f1", "f2"] and item.confidence == 0.95
