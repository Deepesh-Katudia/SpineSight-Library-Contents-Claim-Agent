"""Audit log of raw stage outputs, transcripts and agent events.

MongoDB Atlas when MONGODB_URI is set (schemaless documents suit raw VLM output); otherwise JSONL
files next to the frames. Logging never blocks or fails the pipeline.
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
        self._db = None
        if settings.mongodb_uri:
            from pymongo import MongoClient

            self._db = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)[settings.mongodb_db]

    def _write_local(self, sweep_id: str, doc: dict) -> None:
        path = self._root / "sweeps" / sweep_id / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, default=str) + "\n")

    def _write(self, sweep_id: str, doc: dict) -> None:
        try:
            if self._db is not None:
                self._db.events.insert_one(dict(doc))
            else:
                self._write_local(sweep_id, doc)
        except Exception:
            log.exception("event log write failed")
            self._write_local(sweep_id, doc)

    async def log(self, sweep_id: str, kind: str, payload: dict) -> None:
        doc = {"sweep_id": sweep_id, "kind": kind, "at": datetime.now(UTC).isoformat(), "payload": payload}
        await asyncio.to_thread(self._write, sweep_id, doc)
