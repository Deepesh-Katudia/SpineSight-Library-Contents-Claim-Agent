"""Typed per-frame observations produced by the detect/read stages (pixel coordinates)."""

from __future__ import annotations

from dataclasses import dataclass, field

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in pixels
Quad = tuple[tuple[float, float], ...]  # 4 points, pixels, order: TL, TR, BR, BL


@dataclass(frozen=True)
class SpineObs:
    box: Box
    row: int
    orientation: str  # vertical | flat
    text: str = ""
    title: str = ""
    author: str = ""
    publisher: str = ""
    legibility: float = 0.0
    visual_flags: tuple[str, ...] = ()

    @property
    def height_px(self) -> float:
        x0, y0, x1, y1 = self.box
        return (y1 - y0) if self.orientation != "flat" else (x1 - x0)

    @property
    def thickness_px(self) -> float:
        x0, y0, x1, y1 = self.box
        return (x1 - x0) if self.orientation != "flat" else (y1 - y0)


@dataclass(frozen=True)
class ObjectObs:
    box: Box
    category: str
    description: str = ""
    material: str = ""
    brand_model: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class WallObs:
    """A wall seen edge to edge in one frame: its 4 corners and planar references on it."""

    corners: Quad
    door: Quad | None = None
    openings: tuple[Quad, ...] = ()  # windows / doors to subtract from wall area
    shelf_fronts: tuple[Quad, ...] = ()


@dataclass(frozen=True)
class Quality:
    blur: float = 0.0
    glare: float = 0.0
    occlusion: float = 0.0
    unreadable_spines: int = 0
    issues: tuple[str, ...] = ()


@dataclass
class FrameObservation:
    frame_ref: str
    t_ms: int
    width: int
    height: int
    target: str = ""  # capture target announced by the live agent, e.g. "shelf:A" or "wall:2"
    spines: list[SpineObs] = field(default_factory=list)
    objects: list[ObjectObs] = field(default_factory=list)
    reference: Quad | None = None  # A4 sheet corners
    shelf_rows: list[Box] = field(default_factory=list)
    wall: WallObs | None = None
    quality: Quality = field(default_factory=Quality)
