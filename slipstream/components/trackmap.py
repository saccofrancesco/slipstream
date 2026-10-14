"""Reflex wrapper for the local animated SVG track map component."""

from typing import TypedDict

import reflex as rx

_TRACKMAP_PATH = rx.asset("./trackmap.jsx", shared=True)
_TRACKMAP_CSS_PATH = rx.asset("./trackmap.css", shared=True)


class TrackmapPoint(TypedDict):
    """One ordered coordinate in the displayed track path."""

    x: float
    y: float


class TrackmapSegment(TypedDict):
    """A contiguous colored range within the track point list."""

    start_index: int
    end_index: int
    color: str
    winner: str


class TrackmapCorner(TypedDict):
    """A corner marker with track and outward label coordinates."""

    label: str
    track_x: float
    track_y: float
    label_x: float
    label_y: float


class Trackmap(rx.Component):
    """Render a responsive local SVG component without an npm dependency."""

    library: str = f"$/public{_TRACKMAP_PATH}"
    tag: str = "Trackmap"

    points: rx.Var[list[TrackmapPoint]]
    segments: rx.Var[list[TrackmapSegment]]
    corners: rx.Var[list[TrackmapCorner]]
    preserve_orientation: rx.Var[bool] = rx.Var.create(False)
    animation_key: rx.Var[str]
    duration_ms: rx.Var[int] = rx.Var.create(2200)

    def add_imports(self) -> dict[str, str]:
        """Copy and import the component stylesheet with the local module."""
        return {"": f"$/public{_TRACKMAP_CSS_PATH}"}


trackmap = Trackmap.create
