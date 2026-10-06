"""End-to-end through the HTTP API with a scripted VLM and fake price sources (no network)."""

import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import build_deps
from app.main import create_app
from app.sources.catalog import CatalogCandidate
from app.sources.common import Listing, SourcedPrice
from app.sources.fx import FxRate
from app.stages import detect, read

W, H = 1000, 1000
# A4 drawn at 10 px/cm, portrait, at x 50..260, y 50..347
A4 = [[50, 50], [260, 50], [260, 347], [50, 347]]
TITLES = ["Dune|Frank Herbert", "Emma|Jane Austen", "", "Beloved|Toni Morrison"]


def frame_jpeg() -> bytes:
    img = np.full((H, W, 3), 60, np.uint8)
    cv2.rectangle(img, (50, 50), (260, 347), (250, 250, 250), -1)
    for i in range(4):
        cv2.rectangle(img, (400 + i * 40, 400), (430 + i * 40, 610), (30 + 40 * i, 90, 160), -1)
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


class ScriptedLLM:
    async def json_call(self, stage, system, content, model=None):
        if stage == "detect":
            return {
                "quality": {"blur": 0.1, "glare": 0.0},
                "shelf_rows": [{"x0": 380, "y0": 380, "x1": 700, "y1": 620}],
                "spines": [{"x0": 400 + i * 40, "y0": 400, "x1": 430 + i * 40, "y1": 610, "row": 0} for i in range(4)],
                "objects": [{"x0": 800, "y0": 100, "x1": 900, "y1": 300, "category": "portrait",
                             "description": "oil portrait in gilt frame", "confidence": 0.9},
                            {"x0": 700, "y0": 700, "x1": 800, "y1": 900, "category": "lamp",
                             "description": "brass floor lamp", "confidence": 0.85}],
                "reference_a4": {"corners": A4},
                "wall": None,
            }
        reads = []
        for n, t in enumerate(TITLES, start=1):
            title, _, author = t.partition("|")
            reads.append({"n": n, "text": t.replace("|", " "), "title": title, "author": author,
                          "legibility": 0.95 if t else 0.1})
        return {"reads": reads}


class FakeEbay:
    configured = True

    async def price(self, query="", gtin="", condition="used", country="US", **kw):
        amount = 12.0 if condition == "new" else 5.0
        return SourcedPrice(amount, amount, amount, "USD", "eBay EBAY_US", f"https://ebay/{query}", "2026-10-06T00:00:00Z", 4, condition)

    async def listings(self, query="", gtin="", condition="new", country="US", **kw):
        return [Listing(a, "USD", f"https://ebay/item/{a}", query, "new") for a in (40, 50, 60, 70)]

    async def aclose(self):
        pass


class FakeFx:
    async def rate(self, base, quote):
        return FxRate(base, quote, 1.0 if base == quote else 88.0, "2026-10-05", "https://fx", "2026-10-06T00:00:00Z")


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, data_dir=tmp_path, appraisal_threshold=10000)
    deps = build_deps(settings)
    deps.ebay, deps.fx = FakeEbay(), FakeFx()
    deps.llm = lambda stats: ScriptedLLM()

    async def catalog_search(title, author, country=None):
        return [CatalogCandidate(title, (author,), "", "", "1990", "open_library", f"https://openlibrary.org/{title}")]

    async def retail_offer(title, author, isbn, country):
        return None

    deps.catalog_search, deps.retail_offer = catalog_search, retail_offer
    monkeypatch.setattr("app.main.build_deps", lambda s: deps)
    with TestClient(create_app()) as c:
        yield c


def test_full_sweep_produces_traceable_packet(client):
    sweep = client.post("/sweeps", json={"device": "test"}).json()
    sid = sweep["id"]
    assert sweep["currency"] == "INR"

    assert client.post(f"/sweeps/{sid}/target", json={"target": "shelf:A"}).status_code == 200
    r = client.post(f"/sweeps/{sid}/frames", files={"file": ("f.jpg", frame_jpeg(), "image/jpeg")},
                    data={"t_ms": "1000", "width": str(W), "height": str(H), "target": "shelf:A"})
    assert r.status_code == 202 and r.json()["queued"]
    client.post(f"/sweeps/{sid}/facts", json={"kind": "book_note", "text": "Emma is signed by the author", "ref_hint": "Emma"})

    summary = client.post(f"/sweeps/{sid}/finish").json()
    assert summary["book_count"] == 4
    assert summary["books_identified"] == 2  # Dune, Beloved
    assert summary["books_needs_appraisal"] == 1  # Emma (user said signed)
    assert summary["books_unidentified"] == 1  # unreadable spine, no guessed title

    packet = client.get(f"/sweeps/{sid}/packet").json()
    books = {b["title"] or b["status"]: b for b in packet["books"]}
    dune = books["Dune"]
    assert dune["spine_height_cm"] == pytest.approx(21.0, abs=0.3)
    assert dune["spine_thickness_cm"] == pytest.approx(3.0, abs=0.3)
    assert dune["replacement_cost"]["converted"] is True
    assert dune["replacement_cost"]["amount"] == pytest.approx(12 * 88)
    assert dune["used_value"]["url"].startswith("https://ebay/")
    assert books["unidentified"]["title"] == "" and books["unidentified"]["spine_height_cm"]

    assert packet["totals"]["books_replacement_cost"] == pytest.approx(2 * 12 * 88)
    items = {i["category"]: i for i in packet["items"]}
    assert items["portrait"]["status"] == "needs_appraisal"
    assert items["lamp"]["status"] == "range" and items["lamp"]["replacement_cost"]["low"] == pytest.approx(47.5 * 88)
    assert len(packet["second_locale"]) == 2 and packet["second_locale"][0]["currency"] == "USD"
    assert any(e["ref_id"] == "room" for e in packet["review_queue"])

    # every frame_ref opens
    assert client.get(f"/frames/{dune['frame_ref']}").status_code == 200
    report = client.get(f"/sweeps/{sid}/report")
    assert report.status_code == 200 and "Dune" in report.text
    assert any(m["stage"] == "time_to_packet" for m in packet["metrics"])


def test_rejects_bad_inputs(client):
    sid = client.post("/sweeps", json={}).json()["id"]
    bad_target = client.post(f"/sweeps/{sid}/frames", files={"file": ("f.jpg", b"x", "image/jpeg")},
                             data={"t_ms": "1", "width": "10", "height": "10", "target": "../etc"})
    assert bad_target.status_code == 422
    png = client.post(f"/sweeps/{sid}/frames", files={"file": ("f.png", b"x", "image/png")},
                      data={"t_ms": "1", "width": "10", "height": "10"})
    assert png.status_code == 415
    assert client.get("/frames/../../secret.jpg").status_code in (400, 404)
    assert client.get("/sweeps/nothex/packet").status_code == 400
    assert client.post("/sweeps/unknown/finish").status_code == 404
    assert client.post(f"/sweeps/{sid}/facts", json={"kind": "drop_table", "text": "x"}).status_code == 422


def test_rejects_non_jpeg_bytes_and_bad_transcript(client):
    sid = client.post("/sweeps", json={}).json()["id"]
    fake = client.post(f"/sweeps/{sid}/frames", files={"file": ("f.jpg", b"GIF89a-not-a-jpeg", "image/jpeg")},
                       data={"t_ms": "1", "width": "10", "height": "10"})
    assert fake.status_code == 415
    assert client.post(f"/sweeps/{sid}/transcript", json=["not", "a", "dict"]).status_code == 422
    assert client.post(f"/sweeps/{sid}/transcript", json={"role": "agent", "text": "hi"}).status_code == 200
    assert client.post("/live/token").status_code == 503
    assert "not available" in client.post("/live/token").json()["detail"]
