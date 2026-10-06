"""Packet persistence: local JSON always (the deliverable file), Supabase Postgres when configured."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.config import Settings
from app.schema.claim_packet import ClaimPacket

log = logging.getLogger(__name__)


class PacketRepository:
    def __init__(self, settings: Settings) -> None:
        self._root = Path(settings.data_dir) / "sweeps"
        self._sb = None
        if settings.supabase_url and settings.supabase_service_role_key:
            from supabase import create_client

            self._sb = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def packet_path(self, sweep_id: str) -> Path:
        return self._root / sweep_id / "claim_packet.json"

    def load(self, sweep_id: str) -> ClaimPacket | None:
        path = self.packet_path(sweep_id)
        if not path.is_file():
            return None
        return ClaimPacket.model_validate_json(path.read_text(encoding="utf-8"))

    async def save(self, packet: ClaimPacket) -> Path:
        path = self.packet_path(packet.sweep.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, packet.model_dump_json(indent=2), "utf-8")
        if self._sb is not None:
            try:
                await asyncio.to_thread(self._save_supabase, packet)
            except Exception:
                log.exception("supabase save failed for sweep %s", packet.sweep.id)
        return path

    def _save_supabase(self, p: ClaimPacket) -> None:
        sid = p.sweep.id
        self._sb.table("sweeps").upsert({
            "id": sid, "captured_at": p.sweep.captured_at, "country": p.sweep.country,
            "currency": p.sweep.currency, "device": p.sweep.device, "duration_s": p.sweep.duration_s,
            "packet": json.loads(p.model_dump_json()),
        }).execute()
        for table in ("books", "items", "review_queue"):
            self._sb.table(table).delete().eq("sweep_id", sid).execute()
        if p.books:
            self._sb.table("books").insert([{
                "sweep_id": sid, "id": b.id, "shelf": b.shelf, "position": b.position, "frame_ref": b.frame_ref,
                "status": b.status, "title": b.title, "author": b.author, "edition": b.edition, "isbn": b.isbn,
                "spine_height_cm": b.spine_height_cm, "spine_thickness_cm": b.spine_thickness_cm,
                "id_confidence": b.id_confidence,
                "replacement_amount": b.replacement_cost.amount, "replacement_source": b.replacement_cost.source,
                "replacement_url": b.replacement_cost.url, "used_amount": b.used_value.amount,
                "used_source": b.used_value.source, "used_url": b.used_value.url, "excluded": b.excluded,
            } for b in p.books]).execute()
        if p.items:
            self._sb.table("items").insert([{
                "sweep_id": sid, "id": i.id, "category": i.category, "description": i.description,
                "brand_model": i.brand_model, "frame_ref": i.frame_ref, "status": i.status,
                "low": i.replacement_cost.low, "high": i.replacement_cost.high,
                "source": i.replacement_cost.source, "url": i.replacement_cost.url, "confidence": i.confidence,
            } for i in p.items]).execute()
        if p.review_queue:
            self._sb.table("review_queue").insert(
                [{"sweep_id": sid, "ref_id": r.ref_id, "reason": r.reason} for r in p.review_queue]
            ).execute()
