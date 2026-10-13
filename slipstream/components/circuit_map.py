"""Reflex wrapper for the local animated SVG circuit component."""

from typing import TypedDict

import reflex as rx

_CIRCUIT_MAP_PATH = rx.asset("./circuit_map.jsx", shared=True)
_CIRCUIT_MAP_CSS_PATH = rx.asset("./circuit_map.css", shared=True)


class CircuitPoint(TypedDict):
    """One ordered coordinate in the displayed circuit path."""

    x: float
    y: float


class CircuitSegment(TypedDict):
    """A colored inclusive range within the circuit point list."""

    start_index: int
    end_index: int
    color: str


class CircuitCorner(TypedDict):
    """A corner marker with track and outward label coordinates."""

    label: str
    track_x: float
    track_y: float
    label_x: float
    label_y: float


class CircuitMap(rx.Component):
    """Render a responsive local SVG component without an npm dependency."""

    library: str = f"$/public{_CIRCUIT_MAP_PATH}"
    tag: str = "CircuitMap"

    points: rx.Var[list[CircuitPoint]]
    segments: rx.Var[list[CircuitSegment]]
    corners: rx.Var[list[CircuitCorner]]
    animation_key: rx.Var[str]
    duration_ms: rx.Var[int] = rx.Var.create(2500)

    def add_imports(self) -> dict[str, str]:
        """Copy and import the component stylesheet with the local module."""
        return {"": f"$/public{_CIRCUIT_MAP_CSS_PATH}"}


circuit_map = CircuitMap.create
