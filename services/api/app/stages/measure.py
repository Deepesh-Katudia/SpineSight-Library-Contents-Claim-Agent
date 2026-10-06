"""Stage 6a: metric scale and spine measurement.

Scale sources, in order of trust (each frame picks the best one available):
1. ``a4_reference``   – an A4 sheet (21.0 x 29.7 cm) in the frame -> homography px -> cm on that plane.
2. ``chained_spines`` – books already measured in an earlier A4 frame and re-seen here
                        (overlapping pan) -> median cm/px from their known heights.
3. ``format_prior``   – no metric evidence: median spine assumed a trade paperback (21.6 cm).
                        Low confidence, always routed to review.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

import cv2
import numpy as np

from app.stages.observations import Quad, SpineObs

A4_W_CM, A4_H_CM = 21.0, 29.7
TRADE_PAPERBACK_CM = 21.6
SPINE_HEIGHT_RANGE_CM = (9.0, 60.0)
SPINE_THICKNESS_RANGE_CM = (0.2, 15.0)

CONFIDENCE = {"a4_reference": 0.9, "chained_spines": 0.75, "format_prior": 0.3}
CHAIN_DECAY = 0.9
A4_ASPECT = A4_H_CM / A4_W_CM
A4_ASPECT_TOLERANCE = 0.2


@dataclass(frozen=True)
class FrameScale:
    matrix: np.ndarray  # 3x3 homography, pixel -> cm on the measured plane
    method: str
    confidence: float

    def to_cm(self, x: float, y: float) -> tuple[float, float]:
        pt = cv2.perspectiveTransform(np.array([[[x, y]]], dtype=np.float64), self.matrix)
        return float(pt[0, 0, 0]), float(pt[0, 0, 1])

    def distance_cm(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        (ax, ay), (bx, by) = self.to_cm(*a), self.to_cm(*b)
        return float(np.hypot(ax - bx, ay - by))


def order_quad(quad: Quad) -> np.ndarray:
    """Order 4 points TL, TR, BR, BL regardless of input order."""
    pts = np.array(quad, dtype=np.float64)
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]])


def quad_homography(quad: Quad, width_cm: float, height_cm: float) -> np.ndarray:
    """Homography mapping the pixel quad onto a width x height cm rectangle.

    Orientation (portrait/landscape) is chosen to match the quad's pixel aspect.
    """
    src = order_quad(quad)
    w_px = np.linalg.norm(src[1] - src[0])
    h_px = np.linalg.norm(src[3] - src[0])
    if (w_px > h_px) != (width_cm > height_cm):
        width_cm, height_cm = height_cm, width_cm
    dst = np.array([[0, 0], [width_cm, 0], [width_cm, height_cm], [0, height_cm]], dtype=np.float64)
    return cv2.getPerspectiveTransform(src.astype(np.float32), dst.astype(np.float32)).astype(np.float64)


def refine_quad(img: np.ndarray, quad: Quad, pad: float = 0.15) -> Quad:
    """Snap a VLM-approximate quad of a bright sheet to the real paper edges with OpenCV."""
    pts = order_quad(quad)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    px, py = (x1 - x0) * pad, (y1 - y0) * pad
    h, w = img.shape[:2]
    xa, ya, xb, yb = int(max(0, x0 - px)), int(max(0, y0 - py)), int(min(w, x1 + px)), int(min(h, y1 + py))
    roi = img[ya:yb, xa:xb]
    if roi.size == 0:
        return quad
    gray = cv2.GaussianBlur(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return quad
    best = max(contours, key=cv2.contourArea)
    approx = cv2.approxPolyDP(best, 0.02 * cv2.arcLength(best, True), True)
    expected = (x1 - x0) * (y1 - y0)
    if len(approx) != 4 or not (0.5 * expected < cv2.contourArea(approx) < 1.6 * expected):
        return quad
    return tuple((float(p[0][0] + xa), float(p[0][1] + ya)) for p in approx)


def plausible_a4(quad: Quad) -> bool:
    """Reject a detected 'A4 sheet' whose pixel aspect is far from 1.414 (wrong object or extreme angle)."""
    pts = order_quad(quad)
    w = (np.linalg.norm(pts[1] - pts[0]) + np.linalg.norm(pts[2] - pts[3])) / 2
    h = (np.linalg.norm(pts[3] - pts[0]) + np.linalg.norm(pts[2] - pts[1])) / 2
    if min(w, h) < 8:
        return False
    aspect = max(w, h) / min(w, h)
    return abs(aspect - A4_ASPECT) / A4_ASPECT <= A4_ASPECT_TOLERANCE


def scale_from_reference(quad: Quad) -> FrameScale:
    return FrameScale(quad_homography(quad, A4_W_CM, A4_H_CM), "a4_reference", CONFIDENCE["a4_reference"])


def uniform_scale(cm_per_px: float, method: str, confidence: float | None = None) -> FrameScale:
    conf = CONFIDENCE[method] if confidence is None else confidence
    return FrameScale(np.diag([cm_per_px, cm_per_px, 1.0]), method, conf)


def scale_from_known_spines(
    pairs: list[tuple[float, float]], source_confidence: float = CONFIDENCE["a4_reference"]
) -> FrameScale | None:
    """pairs = (height_px in this frame, height_cm measured earlier). Confidence decays with every
    chaining hop and never exceeds the confidence of the measurements it borrows from."""
    ratios = [cm / px for px, cm in pairs if px > 0 and cm > 0]
    if len(ratios) < 2:
        return None
    conf = round(min(CONFIDENCE["chained_spines"], source_confidence * CHAIN_DECAY), 3)
    return uniform_scale(statistics.median(ratios), "chained_spines", conf)


def scale_from_format_prior(spines: list[SpineObs]) -> FrameScale | None:
    heights = [s.height_px for s in spines if s.orientation != "flat" and s.height_px > 0]
    if len(heights) < 3:
        return None
    return uniform_scale(TRADE_PAPERBACK_CM / statistics.median(heights), "format_prior")


def pick_scale(*candidates: FrameScale | None) -> FrameScale | None:
    present = [c for c in candidates if c is not None]
    return max(present, key=lambda c: c.confidence) if present else None


def _in_range(value: float, bounds: tuple[float, float]) -> float | None:
    return round(value, 1) if bounds[0] <= value <= bounds[1] else None


def measure_spine(spine: SpineObs, scale: FrameScale) -> tuple[float | None, float | None]:
    """Return (height_cm, thickness_cm); a value outside physical bounds becomes None."""
    x0, y0, x1, y1 = spine.box
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    vertical = scale.distance_cm((mx, y0), (mx, y1))
    horizontal = scale.distance_cm((x0, my), (x1, my))
    height, thickness = (horizontal, vertical) if spine.orientation == "flat" else (vertical, horizontal)
    return _in_range(height, SPINE_HEIGHT_RANGE_CM), _in_range(thickness, SPINE_THICKNESS_RANGE_CM)
