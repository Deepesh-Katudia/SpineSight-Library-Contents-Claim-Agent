"""Stage 6b: room dimensions and surface areas from the same sweep.

The live agent directs the user to show each wall edge to edge ("wall:1".."wall:N", clockwise
from the door). For a wall frame we need a planar reference ON that wall:
* an A4 sheet on the wall (best), or
* the door frame, assuming the national standard door size (weaker).
The reference gives a homography for the whole wall plane, so the wall's corners map to cm.
Opposite walls are averaged; a room with other than 4 walls is reported as non-rectangular.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

import cv2
import numpy as np

from app.schema.claim_packet import Room
from app.stages.measure import A4_H_CM, A4_W_CM, FrameScale, order_quad, quad_homography
from app.stages.observations import FrameObservation, Quad

# Standard internal door leaf sizes (w, h) in cm
DOOR_SIZE_CM = {"IN": (90.0, 210.0), "US": (91.4, 203.2)}
DEFAULT_DOOR_CM = (90.0, 205.0)
WALL_CONFIDENCE = {"a4_on_wall": 0.85, "door_standard": 0.5}
MISSING_OPPOSITE_PENALTY = 0.85
WALL_WIDTH_RANGE_M = (0.8, 20.0)
WALL_HEIGHT_RANGE_M = (1.8, 6.0)


@dataclass(frozen=True)
class WallMeasurement:
    label: str
    width_m: float
    height_m: float
    openings_m2: float
    shelf_fronts_m2: float
    method: str
    confidence: float
    frame_ref: str


def _center(quad: Quad) -> tuple[float, float]:
    pts = np.array(quad)
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def _inside(point: tuple[float, float], quad: Quad) -> bool:
    contour = order_quad(quad).astype(np.float32).reshape(-1, 1, 2)
    return cv2.pointPolygonTest(contour, point, False) >= 0


def _area_m2(quad: Quad, scale: FrameScale) -> float:
    pts = np.array([scale.to_cm(x, y) for x, y in order_quad(quad)])
    x, y = pts[:, 0], pts[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))) / 10_000


def wall_scale(obs: FrameObservation, country: str) -> FrameScale | None:
    wall = obs.wall
    if wall is None:
        return None
    if obs.reference and _inside(_center(obs.reference), wall.corners):
        return FrameScale(quad_homography(obs.reference, A4_W_CM, A4_H_CM), "a4_on_wall", WALL_CONFIDENCE["a4_on_wall"])
    if wall.door:
        w, h = DOOR_SIZE_CM.get(country.upper(), DEFAULT_DOOR_CM)
        return FrameScale(quad_homography(wall.door, w, h), "door_standard", WALL_CONFIDENCE["door_standard"])
    return None


def measure_wall(obs: FrameObservation, country: str) -> WallMeasurement | None:
    scale = wall_scale(obs, country)
    if scale is None or not obs.target.startswith("wall:"):
        return None
    tl, tr, br, bl = [tuple(p) for p in order_quad(obs.wall.corners)]
    mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)  # noqa: E731
    width_cm = scale.distance_cm(mid(tl, bl), mid(tr, br))
    height_cm = scale.distance_cm(mid(tl, tr), mid(bl, br))
    w_m, h_m = width_cm / 100, height_cm / 100
    if not (np.isfinite(w_m) and np.isfinite(h_m)):
        return None
    if not (WALL_WIDTH_RANGE_M[0] <= w_m <= WALL_WIDTH_RANGE_M[1]
            and WALL_HEIGHT_RANGE_M[0] <= h_m <= WALL_HEIGHT_RANGE_M[1]):
        return None
    return WallMeasurement(
        label=obs.target.split(":", 1)[1],
        width_m=round(width_cm / 100, 3),
        height_m=round(height_cm / 100, 3),
        openings_m2=sum(_area_m2(q, scale) for q in obs.wall.openings + ((obs.wall.door,) if obs.wall.door else ())),
        shelf_fronts_m2=sum(_area_m2(q, scale) for q in obs.wall.shelf_fronts),
        method=scale.method,
        confidence=scale.confidence,
        frame_ref=obs.frame_ref,
    )


def best_per_wall(measurements: list[WallMeasurement]) -> dict[str, WallMeasurement]:
    """Per wall label keep the highest-confidence method, taking the median-width frame among those."""
    by_label: dict[str, list[WallMeasurement]] = {}
    for m in measurements:
        by_label.setdefault(m.label, []).append(m)
    best = {}
    for label, ms in by_label.items():
        top = max(m.confidence for m in ms)
        tier = sorted((m for m in ms if m.confidence == top), key=lambda m: m.width_m)
        best[label] = tier[len(tier) // 2]
    return best


def _pair(a: WallMeasurement | None, b: WallMeasurement | None) -> tuple[float | None, float]:
    present = [m for m in (a, b) if m]
    if not present:
        return None, 0.0
    conf = min(m.confidence for m in present) * (1 if len(present) == 2 else MISSING_OPPOSITE_PENALTY)
    return statistics.mean(m.width_m for m in present), conf


def assemble_room(measurements: list[WallMeasurement]) -> Room:
    walls = best_per_wall(measurements)
    refs = [w.frame_ref for w in walls.values()]
    methods = sorted({w.method for w in walls.values()})
    if not walls:
        return Room(scale_method="none", confidence=0, notes=["no wall was captured edge to edge with a planar reference"])

    height = round(statistics.median(w.height_m for w in walls.values()), 2)
    openings = sum(w.openings_m2 for w in walls.values())
    shelved = round(sum(w.shelf_fronts_m2 for w in walls.values()), 2)
    method = "+".join(methods)

    if len(walls) > 4:
        perimeter = sum(w.width_m for w in walls.values())
        return Room(
            height_m=height,
            wall_area_m2=round(perimeter * height - openings, 2),
            shelved_wall_area_m2=shelved,
            shape=f"non-rectangular ({len(walls)} walls); floor area needs corner angles, not computed",
            scale_method=method,
            confidence=round(min(w.confidence for w in walls.values()) * 0.7, 2),
            frame_refs=refs,
        )

    length, c1 = _pair(walls.get("1"), walls.get("3"))
    width, c2 = _pair(walls.get("2"), walls.get("4"))
    notes = []
    if len(walls) < 4:
        notes.append(f"only walls {sorted(walls)} measured; opposite walls assumed equal (rectangle)")
    if length is None or width is None:
        return Room(
            height_m=height, shelved_wall_area_m2=shelved, shape="rectangle assumed",
            scale_method=method, confidence=0.2, frame_refs=refs,
            notes=notes + ["need at least one wall from each direction to compute floor area"],
        )
    return Room(
        length_m=round(max(length, width), 2),
        width_m=round(min(length, width), 2),
        height_m=height,
        floor_area_m2=round(length * width, 2),
        wall_area_m2=round(2 * (length + width) * height - openings, 2),
        shelved_wall_area_m2=shelved,
        shape="rectangle",
        scale_method=method,
        confidence=round(min(c1, c2), 2),
        frame_refs=refs,
        notes=notes + [f"door/window openings subtracted: {openings:.2f} m2"],
    )
