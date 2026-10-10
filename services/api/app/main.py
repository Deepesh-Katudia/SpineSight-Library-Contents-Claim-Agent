"""SpineSight API."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.deps import Deps, build_deps
from app.finalize import finalize
from app.live import conversation_token
from app.report import render_report
from app.schema.claim_packet import ClaimPacket
from app.session import SweepSession
from app.stages.price import Locale

log = logging.getLogger("spinesight")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs every request URL at INFO, and Google Books takes its API key as a query parameter.
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

MAX_FRAME_BYTES = 4 * 1024 * 1024
MAX_SWEEP_MS = 60 * 60 * 1000
JPEG_MAGIC = b"\xff\xd8\xff"
TARGET_RE = re.compile(r"^(shelf:[A-Za-z0-9]{1,3}|wall:\d{1,2}|room|)$")
SWEEP_ID_RE = re.compile(r"^[a-f0-9]{12}$")


class CreateSweep(BaseModel):
    country: str = Field(default="", max_length=2)
    currency: str = Field(default="", max_length=3)
    device: str = Field(default="", max_length=200)


class TargetIn(BaseModel):
    target: str = Field(pattern=TARGET_RE.pattern)


class FactIn(BaseModel):
    kind: str = Field(pattern=r"^(exclude_shelf|exclude_item|book_note|item_note|room_note)$")
    text: str = Field(min_length=1, max_length=500)
    ref_hint: str = Field(default="", max_length=200)


class TranscriptIn(BaseModel):
    role: str = Field(pattern=r"^(agent|user|system)$")
    text: str = Field(max_length=4000)


class LocaleIn(BaseModel):
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.deps = build_deps(get_settings())
    app.state.sessions = {}
    yield
    await app.state.deps.aclose()


def get_deps(request: Request) -> Deps:
    return request.app.state.deps


def get_session(sweep_id: str, request: Request) -> SweepSession:
    session = request.app.state.sessions.get(sweep_id)
    if session is None:
        raise HTTPException(404, "unknown or finished sweep")
    return session


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SpineSight API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.web_origin.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health(deps: Deps = Depends(get_deps)) -> dict:
        s = deps.settings
        return {"ok": True, "configured": {
            "elevenlabs": bool(s.elevenlabs_api_key and s.elevenlabs_agent_id),
            "openrouter": bool(s.openrouter_api_key),
            "google_books": bool(s.google_books_api_key), "ebay": deps.ebay.configured,
            "supabase": bool(s.supabase_url)}}

    @app.post("/live/token")
    async def live_token(deps: Deps = Depends(get_deps)) -> dict:
        try:
            token = await conversation_token(deps.settings, deps.http)
        except Exception as exc:
            log.exception("live token failed")
            raise HTTPException(503, "live voice is not available") from exc
        return {"token": token}

    @app.post("/sweeps")
    async def create_sweep(body: CreateSweep, request: Request, deps: Deps = Depends(get_deps)) -> dict:
        s = deps.settings
        if len(request.app.state.sessions) >= s.max_open_sweeps:
            raise HTTPException(429, "too many open sweeps")
        locale = Locale((body.country or s.primary_country).upper(), (body.currency or s.primary_currency).upper())
        session = SweepSession(deps=deps, locale=locale, device=body.device)
        session.start()
        request.app.state.sessions[session.id] = session
        await deps.events.log(session.id, "sweep_started", {"locale": locale.__dict__, "device": body.device})
        return {"id": session.id, "country": locale.country, "currency": locale.currency}

    @app.post("/sweeps/{sweep_id}/frames", status_code=202)
    async def upload_frame(
        file: UploadFile = File(...),
        t_ms: int = Form(..., ge=0, le=MAX_SWEEP_MS),
        width: int = Form(..., gt=0, le=8000),
        height: int = Form(..., gt=0, le=8000),
        target: str = Form(""),
        session: SweepSession = Depends(get_session),
    ) -> dict:
        if not TARGET_RE.match(target):
            raise HTTPException(422, "invalid target")
        if file.content_type not in ("image/jpeg", "image/jpg"):
            raise HTTPException(415, "frames must be JPEG")
        data = await file.read(MAX_FRAME_BYTES + 1)
        if len(data) > MAX_FRAME_BYTES:
            raise HTTPException(413, "frame too large")
        if not data.startswith(JPEG_MAGIC):
            raise HTTPException(415, "frames must be JPEG")
        if session.frames_received >= session.deps.settings.max_frames_per_sweep:
            raise HTTPException(429, "frame limit for this sweep reached")
        ref = await session.enqueue_frame(data, t_ms, width, height, target)
        return {"frame_ref": ref, "queued": ref is not None}

    @app.post("/sweeps/{sweep_id}/target")
    async def set_target(body: TargetIn, session: SweepSession = Depends(get_session)) -> dict:
        session.target = body.target
        session.emit({"type": "target", "target": body.target})
        return {"target": body.target}

    @app.post("/sweeps/{sweep_id}/facts")
    async def add_fact(body: FactIn, session: SweepSession = Depends(get_session)) -> dict:
        fact = session.add_fact(body.kind, body.text, body.ref_hint)
        await session.deps.events.log(session.id, "user_fact", fact.__dict__)
        return {"recorded": True}

    @app.post("/sweeps/{sweep_id}/locale")
    async def set_locale(body: LocaleIn, session: SweepSession = Depends(get_session)) -> dict:
        session.locale = Locale(body.country.upper(), body.currency.upper())
        return {"country": session.locale.country, "currency": session.locale.currency}

    @app.post("/sweeps/{sweep_id}/transcript")
    async def transcript(body: TranscriptIn, session: SweepSession = Depends(get_session)) -> dict:
        await session.deps.events.log(session.id, "transcript", body.model_dump())
        return {"ok": True}

    @app.get("/sweeps/{sweep_id}/status")
    async def status(session: SweepSession = Depends(get_session)) -> dict:
        rows = {k: len(v) for k, v in session.spines.rows.items()}
        return {"books_seen": sum(rows.values()), "rows": rows, "items_seen": len(session.items.items),
                "walls_measured": sorted({w.label for w in session.walls}), "frames": session.frames_processed,
                "target": session.target}

    @app.get("/sweeps/{sweep_id}/events")
    async def events(request: Request, session: SweepSession = Depends(get_session)):
        queue = session.subscribe()

        async def stream():
            try:
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield {"event": "ping", "data": "{}"}
                        continue
                    yield {"event": event["type"], "data": json.dumps(event, default=str)}
            finally:
                session.unsubscribe(queue)

        return EventSourceResponse(stream())

    @app.post("/sweeps/{sweep_id}/finish")
    async def finish(sweep_id: str, request: Request, session: SweepSession = Depends(get_session)) -> dict:
        if session.finishing:
            raise HTTPException(409, "packet is already being built")
        session.finishing = True
        session.ended_at = session.ended_at or datetime.now(UTC)
        session.emit({"type": "stage", "stage": "finalize", "status": "started"})
        try:
            packet = await finalize(session)
        finally:
            session.finishing = False
        await session.deps.packets.save(packet)
        report_path = session.deps.packets.packet_path(sweep_id).with_name("report.html")
        report_path.write_text(render_report(packet, session.deps.settings.api_base_url), encoding="utf-8")
        summary = packet_summary(packet)
        session.emit({"type": "packet_ready", **summary})
        await session.deps.events.log(sweep_id, "packet_ready", summary)
        request.app.state.sessions.pop(sweep_id, None)
        return summary

    @app.get("/sweeps/{sweep_id}/packet", response_model=ClaimPacket)
    async def get_packet(sweep_id: str, deps: Deps = Depends(get_deps)) -> ClaimPacket:
        return load_packet(deps, sweep_id)

    @app.get("/sweeps/{sweep_id}/report", response_class=HTMLResponse)
    async def get_report(sweep_id: str, request: Request, deps: Deps = Depends(get_deps)) -> str:
        return render_report(load_packet(deps, sweep_id), deps.settings.api_base_url)

    @app.get("/frames/{ref:path}")
    async def frame(ref: str, deps: Deps = Depends(get_deps)) -> FileResponse:
        try:
            path = deps.store.path_for(ref)
        except ValueError as exc:
            raise HTTPException(400, "invalid frame ref") from exc
        if not path.is_file():
            raise HTTPException(404, "frame not found")
        return FileResponse(path, media_type="image/jpeg")

    return app


def load_packet(deps: Deps, sweep_id: str) -> ClaimPacket:
    if not SWEEP_ID_RE.match(sweep_id):
        raise HTTPException(400, "invalid sweep id")
    packet = deps.packets.load(sweep_id)
    if packet is None:
        raise HTTPException(404, "no packet for this sweep yet")
    return packet


def packet_summary(p: ClaimPacket) -> dict:
    t, r = p.totals, p.room
    return {
        "sweep_id": p.sweep.id, "currency": t.currency, "book_count": t.book_count,
        "books_identified": t.books_identified, "books_unidentified": t.books_unidentified,
        "books_needs_appraisal": t.books_needs_appraisal, "shelf_run_m": t.shelf_run_m,
        "books_replacement_cost": t.books_replacement_cost, "books_used_value": t.books_used_value,
        "items": len(p.items), "items_low": t.items_replacement_cost_low, "items_high": t.items_replacement_cost_high,
        "floor_area_m2": r.floor_area_m2, "wall_area_m2": r.wall_area_m2, "review_queue": len(p.review_queue),
        "time_to_packet_s": next((m.latency_s for m in p.metrics if m.stage == "time_to_packet"), None),
    }


app = create_app()
