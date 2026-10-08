"""Audit log of raw stage outputs, transcripts and agent events.

Supabase Postgres `events` table (payload as jsonb, which suits schemaless VLM output) when configured;
otherwise JSONL files next to the frames. Logging never blocks or fails the pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings

log = logging.getLogger(__name__)


class EventLog:
    def __init__(self, settings: Settings) -> None:
        self._root = Path(settings.data_dir)
        self._sb = None
        if settings.supabase_url and settings.supabase_service_role_key:
            from supabase import create_client

            self._sb = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def _write_local(self, sweep_id: str, doc: dict) -> None:
        path = self._root / "sweeps" / sweep_id / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, default=str) + "\n")

    def _write(self, sweep_id: str, doc: dict) -> None:
        try:
            if self._sb is not None:
                # Round-trip through json so non-JSON values (datetimes, paths) serialise the same as locally.
                self._sb.table("events").insert(json.loads(json.dumps(doc, default=str))).execute()
            else:
                self._write_local(sweep_id, doc)
        except Exception:
            log.exception("event log write failed")
            self._write_local(sweep_id, doc)

    async def log(self, sweep_id: str, kind: str, payload: dict) -> None:
        doc = {"sweep_id": sweep_id, "kind": kind, "at": datetime.now(UTC).isoformat(), "payload": payload}
        await asyncio.to_thread(self._write, sweep_id, doc)
