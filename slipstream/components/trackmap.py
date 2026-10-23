"""Reflex wrapper for the local animated SVG track map component."""

from typing import TypedDict

import reflex as rx

_TRACKMAP_PATH = rx.asset("./trackmap.jsx", shared=True)
_TRACKMAP_CSS_PATH = rx.asset("./trackmap.css", shared=True)


class TrackmapPoint(TypedDict):
    """One track coordinate aligned to its chart distance sample."""

    x: float
    y: float
    distance: float


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


class TrackmapPlaybackLap(TypedDict):
    """One selected lap's presentation and elapsed-time track samples."""

    key: str
    label: str
    color: str
    duration: float
    start_index: int
    elapsed: list[float]


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


class TelemetryTrackSync(Trackmap):
    """Keep the track position marker synchronized with chart hover locally."""

    tag: str = "TelemetryTrackSync"
    playback_laps: rx.Var[list[TrackmapPlaybackLap]]
    playback_key: rx.Var[str]
    distance_metres: rx.Var[float]


# Reflex validates Recharts children by Python class name; the local tag below
# selects the context-aware React wrapper instead of Recharts' static component.
class ReferenceLine(rx.Component):
    """Render the local playback playhead inside a Recharts chart."""

    library: str = f"$/public{_TRACKMAP_PATH}"
    tag: str = "TelemetryPlaybackLine"
    distance_metres: rx.Var[float]


TelemetryPlaybackLine = ReferenceLine


trackmap = Trackmap.create
telemetry_track_sync = TelemetryTrackSync.create
telemetry_playback_line = TelemetryPlaybackLine.create
