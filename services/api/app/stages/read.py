"""Stage 3: read spines. Spines are cropped, rotated to horizontal, tiled with numbers,
and read in one VLM call per tile sheet. The model may only transcribe what is printed."""

from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np

from app.llm import OpenRouterClient, image_part
from app.stages.observations import FrameObservation, SpineObs

TILE_HEIGHT = 96
TILE_MAX_WIDTH = 900
LABEL_WIDTH = 70
TILES_PER_SHEET = 15
CROP_PAD = 0.06

READ_SYSTEM = """You transcribe book spines for an insurance inventory. The image is a sheet of numbered
spine crops (rotated so text runs left to right; some may be upside down).
For each number return what is LITERALLY printed. Return STRICT JSON:
{"reads":[{"n":1,"text":"all legible spine text verbatim","title":"","author":"","publisher":"",
 "legibility":0-1, "visual_flags":["signed"|"leather"|"gilt"|"first edition"|"library binding"|"ex-library", ...]}]}
Rules: fill title/author/publisher ONLY from text you can actually read on that crop. If text is blurred,
cut off or ambiguous, leave the field empty and lower legibility. Never infer a title from colours, design
or your knowledge of popular books. legibility = fraction of the spine's text you can read with confidence."""


def decode_jpeg(jpeg: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode frame")
    return img


def crop_spine(img: np.ndarray, spine: SpineObs) -> np.ndarray:
    h, w = img.shape[:2]
    x0, y0, x1, y1 = spine.box
    px, py = (x1 - x0) * CROP_PAD, (y1 - y0) * CROP_PAD
    xa, ya = max(0, int(x0 - px)), max(0, int(y0 - py))
    xb, yb = min(w, int(x1 + px)), min(h, int(y1 + py))
    crop = img[ya:yb, xa:xb]
    if crop.size and spine.orientation != "flat" and crop.shape[0] > crop.shape[1]:
        crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return crop


def _fit(crop: np.ndarray) -> np.ndarray:
    if crop.size == 0:
        return np.zeros((TILE_HEIGHT, 10, 3), np.uint8)
    scale = TILE_HEIGHT / crop.shape[0]
    width = max(10, min(TILE_MAX_WIDTH, int(crop.shape[1] * scale)))
    return cv2.resize(crop, (width, TILE_HEIGHT), interpolation=cv2.INTER_AREA)


def build_sheet(crops: list[np.ndarray], start_number: int = 1) -> np.ndarray:
    """Stack crops vertically, each with a white label strip carrying its number."""
    rows = []
    for i, crop in enumerate(crops):
        tile = _fit(crop)
        row = np.full((TILE_HEIGHT + 8, LABEL_WIDTH + TILE_MAX_WIDTH, 3), 255, np.uint8)
        row[4 : 4 + TILE_HEIGHT, LABEL_WIDTH : LABEL_WIDTH + tile.shape[1]] = tile
        cv2.putText(row, f"#{start_number + i}", (6, TILE_HEIGHT // 2 + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 200), 2)
        rows.append(row)
    return np.vstack(rows) if rows else np.zeros((1, 1, 3), np.uint8)


def encode_jpeg(img: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("jpeg encode failed")
    return buf.tobytes()


def apply_reads(spines: list[SpineObs], reads: list[dict], offset: int = 0) -> list[SpineObs]:
    by_n = {int(r.get("n", -1)): r for r in reads}
    out = []
    for i, spine in enumerate(spines):
        r = by_n.get(offset + i + 1)
        if not r:
            out.append(spine)
            continue
        out.append(
            replace(
                spine,
                text=str(r.get("text", "")).strip(),
                title=str(r.get("title", "")).strip(),
                author=str(r.get("author", "")).strip(),
                publisher=str(r.get("publisher", "")).strip(),
                legibility=max(0.0, min(1.0, float(r.get("legibility", 0)))),
                visual_flags=tuple(str(f).lower() for f in r.get("visual_flags", [])),
            )
        )
    return out


async def read_spines(llm: OpenRouterClient, jpeg: bytes, obs: FrameObservation) -> FrameObservation:
    if not obs.spines:
        return obs
    img = decode_jpeg(jpeg)
    read: list[SpineObs] = []
    for start in range(0, len(obs.spines), TILES_PER_SHEET):
        batch = obs.spines[start : start + TILES_PER_SHEET]
        sheet = build_sheet([crop_spine(img, s) for s in batch], start_number=1)
        raw = await llm.json_call(
            "read",
            READ_SYSTEM,
            [{"type": "text", "text": f"{len(batch)} numbered spines."}, image_part(encode_jpeg(sheet))],
        )
        read.extend(apply_reads(batch, raw.get("reads", [])))
    obs.spines = read
    return obs
