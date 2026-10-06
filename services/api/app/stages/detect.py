"""Stage 2: detection. One VLM call per keyframe returns boxes only — no prices, no sizes.

Sizes come from the measure stage (pixel geometry x metric scale), never from the model.
"""

from __future__ import annotations

from dataclasses import replace

from app.llm import OpenRouterClient, image_part
from app.stages.observations import (
    Box,
    FrameObservation,
    ObjectObs,
    Quad,
    Quality,
    SpineObs,
    WallObs,
)

DETECT_SYSTEM = """You are the detection stage of a home-contents insurance inventory system.
Look at ONE video frame of a home library and return STRICT JSON. Coordinates are integers
normalised to 0..1000 of the image width (x) and height (y).

Return:
{
  "quality": {"blur":0-1, "glare":0-1, "occlusion":0-1, "issues":["short phrase", ...]},
  "shelf_rows": [{"x0":..,"y0":..,"x1":..,"y1":..}],            // each shelf row, top to bottom
  "spines": [{"x0":..,"y0":..,"x1":..,"y1":.., "row": index into shelf_rows or -1,
              "orientation":"vertical"|"flat"}],               // EVERY book spine, incl. flat/stacked, left to right
  "objects": [{"x0":..,"y0":..,"x1":..,"y1":.., "category": one of
               ["shelving","furniture","seating","table","lamp","coffee_machine","appliance","electronics",
                "framed_art","portrait","rug","decor","plant","clock","other"],
               "description":"what is visible", "material":"", "brand_model":"only if a logo/model text is legible else empty",
               "confidence":0-1}],                              // everything that is NOT a book
  "reference_a4": null | {"corners":[[x,y],[x,y],[x,y],[x,y]]},  // a plain A4 sheet, corners TL,TR,BR,BL
  "wall": null | {"corners":[[x,y]x4], "door": null|[[x,y]x4], "openings":[[[x,y]x4],...],
                  "shelf_fronts":[[[x,y]x4],...]}               // only if one wall is visible floor-to-ceiling, corner-to-corner
}
Rules: never read or guess titles here; never estimate sizes or prices; omit anything you are unsure exists;
a spine you can see but cannot read is still a spine. Do not include people or documents."""


def _box(d: dict, w: int, h: int) -> Box:
    return (d["x0"] * w / 1000, d["y0"] * h / 1000, d["x1"] * w / 1000, d["y1"] * h / 1000)


def _quad(points: list | None, w: int, h: int) -> Quad | None:
    if not points or len(points) != 4:
        return None
    return tuple((float(x) * w / 1000, float(y) * h / 1000) for x, y in points)


def _assign_row(spine: SpineObs, rows: list[Box]) -> SpineObs:
    """Spines the model left without a row go to the shelf row containing (or nearest) their centre."""
    if 0 <= spine.row < len(rows) or not rows:
        return spine
    cy = (spine.box[1] + spine.box[3]) / 2

    def distance(i: int) -> float:
        y0, y1 = rows[i][1], rows[i][3]
        return 0.0 if y0 <= cy <= y1 else min(abs(cy - y0), abs(cy - y1))

    return replace(spine, row=min(range(len(rows)), key=distance))


def parse_detection(
    raw: dict, frame_ref: str, t_ms: int, width: int, height: int, target: str = ""
) -> FrameObservation:
    q = raw.get("quality") or {}
    spines = [
        SpineObs(box=_box(s, width, height), row=int(s.get("row", -1)), orientation=s.get("orientation", "vertical"))
        for s in raw.get("spines", [])
        if all(k in s for k in ("x0", "y0", "x1", "y1"))
    ]
    rows = [_box(r, width, height) for r in raw.get("shelf_rows", []) if "x0" in r]
    spines = [_assign_row(s, rows) for s in spines]
    spines.sort(key=lambda s: (s.row, s.box[0], s.box[1]))
    objects = [
        ObjectObs(
            box=_box(o, width, height),
            category=o.get("category", "other"),
            description=o.get("description", ""),
            material=o.get("material", ""),
            brand_model=o.get("brand_model", ""),
            confidence=float(o.get("confidence", 0)),
        )
        for o in raw.get("objects", [])
        if all(k in o for k in ("x0", "y0", "x1", "y1"))
    ]
    ref = raw.get("reference_a4") or {}
    wall_raw = raw.get("wall") or None
    wall = None
    if wall_raw and _quad(wall_raw.get("corners"), width, height):
        wall = WallObs(
            corners=_quad(wall_raw["corners"], width, height),
            door=_quad(wall_raw.get("door"), width, height),
            openings=tuple(q_ for q_ in (_quad(o, width, height) for o in wall_raw.get("openings", [])) if q_),
            shelf_fronts=tuple(q_ for q_ in (_quad(s, width, height) for s in wall_raw.get("shelf_fronts", [])) if q_),
        )
    return FrameObservation(
        frame_ref=frame_ref,
        t_ms=t_ms,
        width=width,
        height=height,
        target=target,
        spines=spines,
        objects=objects,
        reference=_quad(ref.get("corners"), width, height),
        shelf_rows=[_box(r, width, height) for r in raw.get("shelf_rows", []) if "x0" in r],
        wall=wall,
        quality=Quality(
            blur=float(q.get("blur", 0)),
            glare=float(q.get("glare", 0)),
            occlusion=float(q.get("occlusion", 0)),
            issues=tuple(q.get("issues", [])),
        ),
    )


async def detect_frame(
    llm: OpenRouterClient, jpeg: bytes, frame_ref: str, t_ms: int, width: int, height: int, target: str = ""
) -> FrameObservation:
    raw = await llm.json_call(
        "detect",
        DETECT_SYSTEM,
        [{"type": "text", "text": f"Frame {frame_ref}. Capture target: {target or 'unknown'}."}, image_part(jpeg)],
    )
    return parse_detection(raw, frame_ref, t_ms, width, height, target)
