"""Frame storage. Frames are always written locally (fast reads for the pipeline) and mirrored to
Supabase Storage when configured. A frame_ref is a stable relative path that the API serves."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from app.config import Settings

log = logging.getLogger(__name__)
SAFE_REF = re.compile(r"sweeps/[a-z0-9_-]+/(frames|crops)/[a-z0-9_.-]+\.jpg")


class FrameStore:
    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self._bucket = settings.supabase_bucket
        self._supabase = None
        if settings.supabase_url and settings.supabase_service_role_key:
            from supabase import create_client

            self._supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    @staticmethod
    def frame_ref(sweep_id: str, t_ms: int) -> str:
        return f"sweeps/{sweep_id}/frames/{t_ms:08d}.jpg"

    def path_for(self, ref: str) -> Path:
        if not SAFE_REF.fullmatch(ref):
            raise ValueError(f"invalid frame_ref: {ref}")
        return self.root / ref

    def exists(self, ref: str) -> bool:
        try:
            return self.path_for(ref).is_file()
        except ValueError:
            return False

    async def save(self, ref: str, data: bytes) -> str:
        path = self.path_for(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        if self._supabase is not None:
            asyncio.create_task(self._mirror(ref, data))
        return ref

    async def _mirror(self, ref: str, data: bytes) -> None:
        try:
            await asyncio.to_thread(
                self._supabase.storage.from_(self._bucket).upload,
                ref,
                data,
                {"content-type": "image/jpeg", "upsert": "true"},
            )
        except Exception:  # mirror is best-effort; local copy is the source of truth for the run
            log.exception("supabase mirror failed for %s", ref)

    def read(self, ref: str) -> bytes:
        return self.path_for(ref).read_bytes()
