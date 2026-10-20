"""Distance-aligned OpenF1 and FastF1 telemetry for selected session laps."""

import logging
from dataclasses import dataclass
from functools import lru_cache
from math import cos, isfinite, pi, sin
from threading import Lock
from typing import TypedDict

import fastf1
import numpy as np
import pandas as pd
from fastf1.core import Lap, Session
from fastf1.exceptions import DataNotLoadedError
from fastf1.mvapi import CircuitInfo
from fastf1.mvapi import get_circuit_info as get_mvapi_circuit_info
from requests import RequestException

from .api import parse_event_coordinates
from .catalog import SUPPORTED_SESSION_CODES
from .openf1 import (
    OPENF1_FIRST_HISTORICAL_SEASON,
    OpenF1CarSample,
    OpenF1Lap,
    OpenF1LocationSample,
    find_openf1_lap,
    get_openf1_car_data,
    get_openf1_circuit_key,
    get_openf1_location_data,
    get_openf1_session_key,
)

SAMPLE_SPACING_METRES: int = 5
MINI_SECTOR_COUNT: int = 50
MAX_SELECTED_TELEMETRY_LAPS: int = 4
TRACK_ROTATION_ADJUSTMENTS: dict[str, float] = {
    "Albert Park Grand Prix Circuit": -90.0,
    "Shanghai International Circuit": -115.0,
    "Suzuka Circuit": -48.0,
    "Circuit Gilles Villeneuve": -126.5,
    "Circuit de Barcelona-Catalunya": 114.5,
    "Red Bull Ring": -23.0,
    "Circuit de Spa-Francorchamps": -173.0,
    "Hungaroring": 10.0,
    "Circuit Park Zandvoort": -179.0,
    "Autodromo Nazionale di Monza": 170.5,
    "Madring": 148.0,
    "Baku City Circuit": 56.0,
    "Sepang International Circuit": -159.5,
    "Marina Bay Street Circuit": 26.0,
}
_SESSION_LOCK: Lock = Lock()
logger: logging.Logger = logging.getLogger(__name__)


class TelemetryLap(TypedDict):
    """Identity, official timing, and distance-aligned elapsed samples."""

    key: str
    driver: str
    number: int
    seconds: float
    elapsed: list[float]


class TelemetryCorner(TypedDict):
    """One circuit corner on the selected baseline lap's distance axis."""

    label: str
    distance: int


class TelemetrySector(TypedDict):
    """One sector boundary projected onto the selected baseline lap."""

    label: str
    distance: int


class TelemetryTrackPoint(TypedDict):
    """One rotated circuit coordinate aligned to the shared distance grid."""

    x: float
    y: float


class TelemetryTrackSegment(TypedDict):
    """A mini-sector and the selected lap that traversed it fastest."""

    start_index: int
    end_index: int
    winner_key: str


class TelemetryTrackCorner(TypedDict):
    """A numbered circuit corner and its outward label position."""

    label: str
    track_x: float
    track_y: float
    label_x: float
    label_y: float


class SessionTelemetry(TypedDict):
    """Six channel series sharing one distance grid."""

    rows: list[dict[str, float | int]]
    laps: list[TelemetryLap]
    corners: list[TelemetryCorner]
    sectors: list[TelemetrySector]
    track_points: list[TelemetryTrackPoint]
    track_segments: list[TelemetryTrackSegment]
    track_corners: list[TelemetryTrackCorner]
    preserve_orientation: bool
    unavailable: list[str]
    baseline_key: str
    distance_metres: float


@dataclass
class _LapSamples:
    """Original car samples for one timed lap."""

    lap: Lap | None
    openf1_lap: OpenF1Lap | None
    key: str
    driver: str
    number: int
    seconds: float
    distance: np.ndarray
    elapsed: np.ndarray
    speed: np.ndarray
    throttle: np.ndarray
    brake: np.ndarray
    rpm: np.ndarray
    gear: np.ndarray
    session_time: np.ndarray
    sector_boundaries: tuple[float, ...]


def _empty_session_telemetry(unavailable: list[str]) -> SessionTelemetry:
    """Build the shared empty result when none of the selected laps loaded."""
    return {
        "rows": [],
        "laps": [],
        "corners": [],
        "sectors": [],
        "track_points": [],
        "track_segments": [],
        "track_corners": [],
        "preserve_orientation": False,
        "unavailable": unavailable,
        "baseline_key": "",
        "distance_metres": 0,
    }


def _telemetry_rows(
    grid: np.ndarray,
    available: list[_LapSamples],
    sampled: dict[str, dict[str, np.ndarray]],
    baseline: _LapSamples,
) -> list[dict[str, float | int]]:
    """Serialize the shared six-channel rows for either timing provider."""
    baseline_elapsed = sampled[baseline.key]["elapsed"]
    rows: list[dict[str, float | int]] = []
    for index, distance in enumerate(grid):
        row: dict[str, float | int] = {"distance": round(float(distance), 2)}
        for lap in available:
            values = sampled[lap.key]
            key = lap.key
            row[f"speed_{key}"] = round(float(values["speed"][index]), 1)
            row[f"delta_{key}"] = round(
                float(values["elapsed"][index] - baseline_elapsed[index]), 3
            )
            row[f"throttle_{key}"] = round(float(values["throttle"][index]), 1)
            row[f"brake_{key}"] = int(values["brake"][index])
            row[f"rpm_{key}"] = round(float(values["rpm"][index]))
            row[f"gear_{key}"] = round(float(values["gear"][index]))
        rows.append(row)
    return rows


def _serialize_telemetry_laps(
    available: list[_LapSamples],
    sampled: dict[str, dict[str, np.ndarray]],
) -> list[TelemetryLap]:
    """Serialize the shared lap identity and elapsed-time chart data."""
    return [
        {
            "key": lap.key,
            "driver": lap.driver,
            "number": lap.number,
            "seconds": lap.seconds,
            "elapsed": [
                round(float(value), 4) for value in sampled[lap.key]["elapsed"]
            ],
        }
        for lap in available
    ]


@lru_cache(maxsize=1)
def _cached_session(season: int, round_number: int, session_code: str) -> Session:
    """Keep the last telemetry-loaded FastF1 session in this process."""
    session: Session = fastf1.get_session(season, round_number, session_code)
    session.load(
        laps=True,
        telemetry=True,
        weather=False,
        messages=False,
    )
    return session


def _session(season: int, round_number: int, session_code: str) -> Session:
    """Serialize the first load so concurrent requests do not duplicate it."""
    with _SESSION_LOCK:
        return _cached_session(season, round_number, session_code)


@lru_cache(maxsize=32)
def _openf1_circuit_info(season: int, circuit_key: int) -> CircuitInfo | None:
    """Cache free circuit rotation and corner metadata from FastF1's MVAPI."""
    return get_mvapi_circuit_info(year=season, circuit_key=circuit_key)


def _numeric(values: pd.Series) -> np.ndarray:
    """Return a numeric NumPy channel, retaining missing values as NaN."""
    return pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)


def _lap_samples(lap: Lap, driver: str, number: int) -> _LapSamples:
    """Read one lap's car channels with exact start and finish samples."""
    lap_time = lap.get("LapTime")
    start_time = lap.get("LapStartTime")
    if pd.isna(lap_time) or pd.isna(start_time):
        raise ValueError("Lap boundaries are unavailable")
    seconds = float(lap_time.total_seconds())
    if seconds <= 0:
        raise ValueError("Lap time is unavailable")

    car = lap.get_car_data(interpolate_edges=True).add_distance()
    if len(car) < 2:
        raise ValueError("Car telemetry is unavailable")
    distance = _numeric(car["Distance"])
    session_time = car["SessionTime"].dt.total_seconds().to_numpy(dtype=float)
    elapsed = (car["SessionTime"] - start_time).dt.total_seconds().to_numpy(dtype=float)
    channels = [
        distance,
        session_time,
        elapsed,
        _numeric(car["Speed"]),
        _numeric(car["Throttle"]),
        _numeric(car["RPM"]),
        _numeric(car["nGear"]),
    ]
    valid = np.logical_and.reduce([np.isfinite(channel) for channel in channels])
    if valid.sum() < 2:
        raise ValueError("Car telemetry has too few valid samples")
    distance, session_time, elapsed, speed, throttle, rpm, gear = (
        channel[valid] for channel in channels
    )
    brake = car["Brake"].to_numpy()[valid].astype(bool).astype(float)
    distance = np.maximum.accumulate(distance - distance[0])
    if distance[-1] <= 0:
        raise ValueError("Lap distance is unavailable")

    # The timing feed supplies the official endpoints; correct any small
    # difference introduced by slicing or sampling across the lap boundary.
    elapsed = np.clip(elapsed - elapsed[0], 0, None)
    elapsed += (seconds - elapsed[-1]) * distance / distance[-1]
    elapsed[0], elapsed[-1] = 0.0, seconds
    # FastF1 reserves values above 100 for unavailable throttle readings.
    valid_throttle = (throttle >= 0) & (throttle <= 100)
    if not valid_throttle.any():
        raise ValueError("Throttle telemetry is unavailable")
    throttle = np.interp(distance, distance[valid_throttle], throttle[valid_throttle])
    return _LapSamples(
        lap=lap,
        openf1_lap=None,
        key=f"{driver}_{number}",
        driver=driver,
        number=number,
        seconds=seconds,
        distance=distance,
        elapsed=elapsed,
        speed=speed,
        throttle=throttle,
        brake=brake,
        rpm=rpm,
        gear=gear,
        session_time=session_time,
        sector_boundaries=(),
    )


def _openf1_lap_samples(
    lap: OpenF1Lap,
    car_samples: list[OpenF1CarSample],
    driver: str,
    number: int,
) -> _LapSamples:
    """Integrate OpenF1 speed samples into a distance-aligned timed lap."""
    if len(car_samples) < 2:
        raise ValueError("Car telemetry is unavailable")

    starts_at = lap["date_start"].timestamp()
    seconds = lap["lap_duration"]
    session_time = np.array(
        [sample["date"].timestamp() for sample in car_samples], dtype=float
    )
    speed = np.array([sample["speed"] for sample in car_samples], dtype=float)
    throttle = np.array([sample["throttle"] for sample in car_samples], dtype=float)
    brake = np.array([sample["brake"] for sample in car_samples], dtype=float)
    rpm = np.array([sample["rpm"] for sample in car_samples], dtype=float)
    gear = np.array([sample["gear"] for sample in car_samples], dtype=float)
    channels = [session_time, speed, throttle, brake, rpm, gear]
    valid = np.logical_and.reduce([np.isfinite(channel) for channel in channels])
    if valid.sum() < 2:
        raise ValueError("Car telemetry has too few valid samples")
    session_time, speed, throttle, brake, rpm, gear = (
        channel[valid] for channel in channels
    )

    order = np.argsort(session_time)
    session_time, speed, throttle, brake, rpm, gear = (
        channel[order] for channel in (session_time, speed, throttle, brake, rpm, gear)
    )
    session_time, unique_indices = np.unique(session_time, return_index=True)
    speed, throttle, brake, rpm, gear = (
        channel[unique_indices] for channel in (speed, throttle, brake, rpm, gear)
    )
    elapsed = session_time - starts_at
    within_lap = (elapsed >= 0) & (elapsed <= seconds)
    if within_lap.sum() < 2:
        raise ValueError("Car telemetry does not overlap the selected lap")
    elapsed, session_time, speed, throttle, brake, rpm, gear = (
        channel[within_lap]
        for channel in (elapsed, session_time, speed, throttle, brake, rpm, gear)
    )

    # OpenF1 samples at roughly 5 Hz and may start a few milliseconds after the
    # official boundary. Extend the edge values to exactly zero and lap time.
    if elapsed[0] > 0:
        elapsed = np.insert(elapsed, 0, 0.0)
        session_time = np.insert(session_time, 0, starts_at)
        speed, throttle, brake, rpm, gear = (
            np.insert(channel, 0, channel[0])
            for channel in (speed, throttle, brake, rpm, gear)
        )
    else:
        elapsed[0], session_time[0] = 0.0, starts_at
    if elapsed[-1] < seconds:
        elapsed = np.append(elapsed, seconds)
        session_time = np.append(session_time, starts_at + seconds)
        speed, throttle, brake, rpm, gear = (
            np.append(channel, channel[-1])
            for channel in (speed, throttle, brake, rpm, gear)
        )
    else:
        elapsed[-1], session_time[-1] = seconds, starts_at + seconds

    delta_time = np.diff(elapsed)
    interval_speed = (speed[:-1] + speed[1:]) / (2 * 3.6)
    distance = np.concatenate(([0.0], np.cumsum(interval_speed * delta_time)))
    if distance[-1] <= 0:
        raise ValueError("Lap distance is unavailable")

    sector_boundaries: list[float] = []
    first_sector = lap["sector_1_duration"]
    second_sector = lap["sector_2_duration"]
    if first_sector is not None and 0 < first_sector < seconds:
        sector_boundaries.append(first_sector)
        if second_sector is not None and first_sector + second_sector < seconds:
            sector_boundaries.append(first_sector + second_sector)

    return _LapSamples(
        lap=None,
        openf1_lap=lap,
        key=f"{driver}_{number}",
        driver=driver,
        number=number,
        seconds=seconds,
        distance=distance,
        elapsed=elapsed,
        speed=speed,
        throttle=np.clip(throttle, 0, 100),
        brake=(brake > 0).astype(float),
        rpm=rpm,
        gear=gear,
        session_time=session_time,
        sector_boundaries=tuple(sector_boundaries),
    )


def _resample(
    samples: _LapSamples, grid: np.ndarray, baseline_length: float
) -> dict[str, np.ndarray]:
    """Map one lap's channels to the baseline's start-to-finish distance."""
    scaled_distance = samples.distance * baseline_length / samples.distance[-1]
    # At a stationary sample, retain the latest value at that distance.
    unique_distance, reverse_indices = np.unique(
        scaled_distance[::-1], return_index=True
    )
    indices = len(scaled_distance) - 1 - reverse_indices

    def continuous(values: np.ndarray) -> np.ndarray:
        return np.interp(grid, unique_distance, values[indices])

    def discrete(values: np.ndarray) -> np.ndarray:
        previous = np.searchsorted(unique_distance, grid, side="right") - 1
        return values[indices[np.clip(previous, 0, len(indices) - 1)]]

    return {
        "elapsed": continuous(samples.elapsed),
        "speed": continuous(samples.speed),
        "throttle": continuous(samples.throttle),
        "brake": discrete(samples.brake),
        "rpm": continuous(samples.rpm),
        "gear": discrete(samples.gear),
    }


def _rotate_coordinates(
    x: np.ndarray, y: np.ndarray, degrees: float
) -> tuple[np.ndarray, np.ndarray]:
    """Rotate FastF1 coordinates clockwise using the official track-map matrix."""
    angle = degrees / 180 * pi
    return x * cos(angle) + y * sin(angle), -x * sin(angle) + y * cos(angle)


def _track_corner_labels(
    circuit_info: CircuitInfo | None, rotation: float
) -> list[TelemetryTrackCorner]:
    """Create the shared rotated corner and label coordinates."""
    if circuit_info is None or circuit_info.corners.empty:
        return []
    corners: list[TelemetryTrackCorner] = []
    for _, corner in circuit_info.corners.iterrows():
        try:
            corner_x = float(corner.get("X"))
            corner_y = float(corner.get("Y"))
            number = float(corner.get("Number"))
            angle = float(corner.get("Angle"))
        except TypeError, ValueError:
            continue
        if not all(isfinite(value) for value in (corner_x, corner_y, number, angle)):
            continue
        letter = corner.get("Letter")
        suffix = "" if pd.isna(letter) else str(letter).strip()
        offset_angle = angle / 180 * pi
        label_x = corner_x + cos(offset_angle) * 500
        label_y = corner_y + sin(offset_angle) * 500
        rotated_x, rotated_y = _rotate_coordinates(
            np.array([corner_x, label_x]), np.array([corner_y, label_y]), rotation
        )
        corners.append(
            {
                "label": f"{int(number)}{suffix}",
                "track_x": round(float(rotated_x[0]), 3),
                "track_y": round(float(rotated_y[0]), 3),
                "label_x": round(float(rotated_x[1]), 3),
                "label_y": round(float(rotated_y[1]), 3),
            }
        )
    return corners


def _mini_sector_segments(
    grid: np.ndarray,
    laps: list[_LapSamples],
    sampled: dict[str, dict[str, np.ndarray]],
) -> list[TelemetryTrackSegment]:
    """Compare local elapsed times across exactly 50 equal-distance bins."""
    boundaries = np.linspace(float(grid[0]), float(grid[-1]), MINI_SECTOR_COUNT + 1)
    boundary_indices = np.searchsorted(grid, boundaries, side="left")
    boundary_indices[0] = 0
    boundary_indices[-1] = len(grid) - 1
    elapsed_at_boundaries = {
        lap.key: np.interp(boundaries, grid, sampled[lap.key]["elapsed"])
        for lap in laps
    }
    segments: list[TelemetryTrackSegment] = []
    for index in range(MINI_SECTOR_COUNT):
        # Python's min keeps the first item on exact ties, matching lap selection order.
        winner = min(
            laps,
            key=lambda lap: float(
                elapsed_at_boundaries[lap.key][index + 1]
                - elapsed_at_boundaries[lap.key][index]
            ),
        )
        segments.append(
            {
                "start_index": int(boundary_indices[index]),
                "end_index": int(boundary_indices[index + 1]),
                "winner_key": winner.key,
            }
        )
    return segments


def _track_geometry(
    session: Session,
    baseline: _LapSamples,
    grid: np.ndarray,
    available: list[_LapSamples],
    sampled: dict[str, dict[str, np.ndarray]],
    circuit_name: str,
) -> tuple[
    list[TelemetryTrackPoint],
    list[TelemetryTrackSegment],
    list[TelemetryTrackCorner],
    bool,
]:
    """Build the reference trace, local-time winners, and optional corner labels."""
    if baseline.lap is None:
        return [], [], [], False
    try:
        position = baseline.lap.get_pos_data(interpolate_edges=True)
    except Exception:  # noqa: BLE001 - position geometry is optional to car channels.
        return [], [], [], False
    if position.empty:
        return [], [], [], False

    position_times = position["SessionTime"].dt.total_seconds().to_numpy(dtype=float)
    position_x, position_y = _numeric(position["X"]), _numeric(position["Y"])
    valid = (
        np.isfinite(position_times) & np.isfinite(position_x) & np.isfinite(position_y)
    )
    if valid.sum() < 2:
        return [], [], [], False
    position_times = position_times[valid]
    position_x = position_x[valid]
    position_y = position_y[valid]
    position_times, unique_indices = np.unique(position_times, return_index=True)
    position_x, position_y = position_x[unique_indices], position_y[unique_indices]

    grid_session_time = np.interp(grid, baseline.distance, baseline.session_time)
    trace_x = np.interp(grid_session_time, position_times, position_x)
    trace_y = np.interp(grid_session_time, position_times, position_y)

    circuit_info = None
    # Positive values are clockwise in FastF1's coordinate system.
    rotation = TRACK_ROTATION_ADJUSTMENTS.get(circuit_name, 0.0)
    preserve_orientation = circuit_name in TRACK_ROTATION_ADJUSTMENTS
    try:
        circuit_info = session.get_circuit_info()
        if circuit_info is not None and isfinite(float(circuit_info.rotation)):
            rotation += float(circuit_info.rotation)
            preserve_orientation = True
    except Exception:  # noqa: BLE001 - use the static rotation if optional MVAPI fails.
        # Position data is still useful when the optional circuit metadata fails.
        circuit_info = None
    trace_x, trace_y = _rotate_coordinates(trace_x, trace_y, rotation)
    points = [
        {"x": round(float(x), 3), "y": round(float(y), 3)}
        for x, y in zip(trace_x, trace_y, strict=True)
    ]

    corners = _track_corner_labels(circuit_info, rotation)

    return (
        points,
        _mini_sector_segments(grid, available, sampled),
        corners,
        preserve_orientation,
    )


def _corner_distances(session: Session, baseline: _LapSamples) -> list[TelemetryCorner]:
    """Project circuit corner coordinates onto the baseline lap's position trace."""
    if baseline.lap is None:
        return []
    try:
        info = session.get_circuit_info()
        position = baseline.lap.get_pos_data(interpolate_edges=True)
    except Exception:  # noqa: BLE001 - corner labels are optional to car channels.
        # Corner metadata is optional; keep the six car-data channels usable.
        return []
    if info is None or info.corners.empty or position.empty:
        return []

    position_times = position["SessionTime"].dt.total_seconds().to_numpy(dtype=float)
    x, y = _numeric(position["X"]), _numeric(position["Y"])
    valid = np.isfinite(position_times) & np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 2:
        return []
    position_times, x, y = position_times[valid], x[valid], y[valid]
    position_distances = np.interp(
        position_times, baseline.session_time, baseline.distance
    )
    corners: list[TelemetryCorner] = []
    for _, corner in info.corners.iterrows():
        corner_x, corner_y = corner.get("X"), corner.get("Y")
        number = corner.get("Number")
        try:
            valid_corner = all(
                isfinite(float(value)) for value in (corner_x, corner_y, number)
            )
        except TypeError, ValueError:
            continue
        if not valid_corner:
            continue
        nearest = int(
            np.argmin((x - float(corner_x)) ** 2 + (y - float(corner_y)) ** 2)
        )
        distance = round(position_distances[nearest])
        if not 0 <= distance <= baseline.distance[-1]:
            continue
        letter = corner.get("Letter")
        suffix = "" if pd.isna(letter) else str(letter).strip()
        corners.append({"label": f"{int(number)}{suffix}", "distance": distance})
    corners.sort(key=lambda corner: corner["distance"])
    return corners


def _sector_distances(baseline: _LapSamples) -> list[TelemetrySector]:
    """Project sector timing boundaries onto the baseline's distance trace."""
    if baseline.lap is None:
        return []
    sectors: list[TelemetrySector] = []
    for label, field in (("S2", "Sector1SessionTime"), ("S3", "Sector2SessionTime")):
        boundary = baseline.lap.get(field)
        if pd.isna(boundary):
            continue
        boundary_seconds = float(boundary.total_seconds())
        if not isfinite(boundary_seconds):
            continue
        if (
            not baseline.session_time[0]
            <= boundary_seconds
            <= baseline.session_time[-1]
        ):
            continue
        distance = round(
            float(np.interp(boundary_seconds, baseline.session_time, baseline.distance))
        )
        sectors.append({"label": label, "distance": distance})
    return sectors


def _get_fastf1_session_telemetry(
    season: int,
    round_number: int,
    session_code: str,
    selected_laps: tuple[tuple[str, int], ...],
    circuit_name: str,
) -> SessionTelemetry:
    """Load the legacy FastF1 telemetry fallback for one session."""
    session = _session(season, round_number, session_code)
    available: list[_LapSamples] = []
    unavailable: list[str] = []
    for driver, number in selected_laps:
        label = f"{driver} lap {number}"
        matching = session.laps[
            (session.laps["Driver"] == driver) & (session.laps["LapNumber"] == number)
        ]
        if matching.empty:
            unavailable.append(label)
            continue
        try:
            available.append(_lap_samples(matching.iloc[0], driver, number))
        except ValueError, KeyError, TypeError, IndexError, DataNotLoadedError:
            unavailable.append(label)

    if not available:
        return _empty_session_telemetry(unavailable)

    baseline = min(available, key=lambda lap: lap.seconds)
    length = float(baseline.distance[-1])
    grid = np.append(np.arange(0, length, SAMPLE_SPACING_METRES), length)
    sampled = {lap.key: _resample(lap, grid, length) for lap in available}
    (
        track_points,
        track_segments,
        track_corners,
        preserve_orientation,
    ) = _track_geometry(session, baseline, grid, available, sampled, circuit_name)
    rows = _telemetry_rows(grid, available, sampled, baseline)

    return {
        "rows": rows,
        "laps": _serialize_telemetry_laps(available, sampled),
        "corners": _corner_distances(session, baseline),
        "sectors": _sector_distances(baseline),
        "track_points": track_points,
        "track_segments": track_segments,
        "track_corners": track_corners,
        "preserve_orientation": preserve_orientation,
        "unavailable": unavailable,
        "baseline_key": baseline.key,
        "distance_metres": round(length, 2),
    }


def _openf1_track_geometry(
    baseline: _LapSamples,
    grid: np.ndarray,
    available: list[_LapSamples],
    sampled: dict[str, dict[str, np.ndarray]],
    locations: list[OpenF1LocationSample],
    circuit_info: CircuitInfo | None,
    circuit_name: str,
) -> tuple[
    list[TelemetryTrackPoint],
    list[TelemetryTrackSegment],
    list[TelemetryTrackCorner],
    bool,
]:
    """Align OpenF1 positions to the baseline lap's distance grid."""
    if len(locations) < 2:
        return [], [], [], False
    position_times = np.array(
        [sample["date"].timestamp() for sample in locations], dtype=float
    )
    position_x = np.array([sample["x"] for sample in locations], dtype=float)
    position_y = np.array([sample["y"] for sample in locations], dtype=float)
    valid = (
        np.isfinite(position_times) & np.isfinite(position_x) & np.isfinite(position_y)
    )
    if valid.sum() < 2:
        return [], [], [], False
    position_times, position_x, position_y = (
        channel[valid] for channel in (position_times, position_x, position_y)
    )
    order = np.argsort(position_times)
    position_times, position_x, position_y = (
        channel[order] for channel in (position_times, position_x, position_y)
    )
    position_times, unique_indices = np.unique(position_times, return_index=True)
    position_x, position_y = position_x[unique_indices], position_y[unique_indices]
    grid_session_time = np.interp(grid, baseline.distance, baseline.session_time)
    trace_x = np.interp(grid_session_time, position_times, position_x)
    trace_y = np.interp(grid_session_time, position_times, position_y)
    # Positive values are clockwise in FastF1's coordinate system.
    rotation = TRACK_ROTATION_ADJUSTMENTS.get(circuit_name, 0.0)
    preserve_orientation = circuit_name in TRACK_ROTATION_ADJUSTMENTS
    if circuit_info is not None and isfinite(float(circuit_info.rotation)):
        rotation += float(circuit_info.rotation)
        preserve_orientation = True
    trace_x, trace_y = _rotate_coordinates(trace_x, trace_y, rotation)

    corners = _track_corner_labels(circuit_info, rotation)
    return (
        [
            {"x": round(float(x), 3), "y": round(float(y), 3)}
            for x, y in zip(trace_x, trace_y, strict=True)
        ],
        _mini_sector_segments(grid, available, sampled),
        corners,
        preserve_orientation,
    )


def _openf1_corner_distances(
    baseline: _LapSamples,
    locations: list[OpenF1LocationSample],
    circuit_info: CircuitInfo | None,
) -> list[TelemetryCorner]:
    """Project free circuit corner coordinates onto integrated lap distance."""
    if circuit_info is None or circuit_info.corners.empty or len(locations) < 2:
        return []
    position_times = np.array(
        [sample["date"].timestamp() for sample in locations], dtype=float
    )
    x = np.array([sample["x"] for sample in locations], dtype=float)
    y = np.array([sample["y"] for sample in locations], dtype=float)
    valid = np.isfinite(position_times) & np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 2:
        return []
    position_times, x, y = (channel[valid] for channel in (position_times, x, y))
    order = np.argsort(position_times)
    position_times, x, y = (channel[order] for channel in (position_times, x, y))
    position_distances = np.interp(
        position_times, baseline.session_time, baseline.distance
    )
    corners: list[TelemetryCorner] = []
    for _, corner in circuit_info.corners.iterrows():
        try:
            corner_x = float(corner.get("X"))
            corner_y = float(corner.get("Y"))
            number = float(corner.get("Number"))
        except TypeError, ValueError:
            continue
        if not all(isfinite(value) for value in (corner_x, corner_y, number)):
            continue
        nearest = int(np.argmin((x - corner_x) ** 2 + (y - corner_y) ** 2))
        distance = round(float(position_distances[nearest]))
        if not 0 <= distance <= baseline.distance[-1]:
            continue
        letter = corner.get("Letter")
        suffix = "" if pd.isna(letter) else str(letter).strip()
        corners.append({"label": f"{int(number)}{suffix}", "distance": distance})
    corners.sort(key=lambda corner: corner["distance"])
    return corners


def _openf1_sector_distances(baseline: _LapSamples) -> list[TelemetrySector]:
    """Project OpenF1's two sector boundaries onto integrated distance."""
    return [
        {
            "label": label,
            "distance": round(
                float(np.interp(boundary, baseline.elapsed, baseline.distance))
            ),
        }
        for label, boundary in zip(
            ("S2", "S3"), baseline.sector_boundaries, strict=False
        )
    ]


def _get_openf1_session_telemetry(
    season: int,
    round_number: int,
    session_code: str,
    selected_laps: tuple[tuple[str, int], ...],
    circuit_name: str,
) -> SessionTelemetry:
    """Load free OpenF1 car and position data for selected historical laps."""
    available: list[_LapSamples] = []
    unavailable: list[str] = []
    for driver, number in selected_laps:
        label = f"{driver} lap {number}"
        try:
            session_key, lap = find_openf1_lap(
                season, round_number, session_code, driver, number
            )
            car_samples = get_openf1_car_data(session_key, lap["driver_number"], lap)
            available.append(_openf1_lap_samples(lap, car_samples, driver, number))
        except LookupError, ValueError, KeyError, TypeError, IndexError:
            unavailable.append(label)

    if not available:
        return _empty_session_telemetry(unavailable)

    baseline = min(available, key=lambda lap: lap.seconds)
    length = float(baseline.distance[-1])
    grid = np.append(np.arange(0, length, SAMPLE_SPACING_METRES), length)
    sampled = {lap.key: _resample(lap, grid, length) for lap in available}
    locations: list[OpenF1LocationSample] = []
    circuit_info: CircuitInfo | None = None
    if baseline.openf1_lap is not None:
        try:
            session_key = get_openf1_session_key(season, round_number, session_code)
            locations = get_openf1_location_data(
                session_key,
                baseline.openf1_lap["driver_number"],
                baseline.openf1_lap,
            )
        except LookupError, ValueError, KeyError, TypeError, RequestException:
            # The six charts remain useful if optional position samples fail.
            locations = []
    try:
        circuit_info = _openf1_circuit_info(
            season, get_openf1_circuit_key(season, round_number)
        )
    except LookupError, ValueError, KeyError, TypeError, RequestException:
        # Track geometry remains usable without optional corner labels.
        circuit_info = None
    (
        track_points,
        track_segments,
        track_corners,
        preserve_orientation,
    ) = _openf1_track_geometry(
        baseline, grid, available, sampled, locations, circuit_info, circuit_name
    )
    rows = _telemetry_rows(grid, available, sampled, baseline)

    return {
        "rows": rows,
        "laps": _serialize_telemetry_laps(available, sampled),
        "corners": _openf1_corner_distances(baseline, locations, circuit_info),
        "sectors": _openf1_sector_distances(baseline),
        "track_points": track_points,
        "track_segments": track_segments,
        "track_corners": track_corners,
        "preserve_orientation": preserve_orientation,
        "unavailable": unavailable,
        "baseline_key": baseline.key,
        "distance_metres": round(length, 2),
    }


def get_session_telemetry(
    season: int | str,
    round_number: int | str,
    session_code: str,
    selected_laps: list[tuple[str, int]],
    circuit_name: str = "",
) -> SessionTelemetry:
    """Load selected laps from OpenF1, with FastF1 as an archive fallback."""
    coordinates = parse_event_coordinates(season, round_number)
    if coordinates is None:
        raise ValueError("A supported numeric season and round are required")
    parsed_season, parsed_round = coordinates
    if session_code not in SUPPORTED_SESSION_CODES:
        raise ValueError("The requested session is not supported")
    unique_laps = tuple(dict.fromkeys(selected_laps))
    if len(unique_laps) > MAX_SELECTED_TELEMETRY_LAPS:
        raise ValueError(
            f"Select no more than {MAX_SELECTED_TELEMETRY_LAPS} laps at once"
        )

    if parsed_season >= OPENF1_FIRST_HISTORICAL_SEASON:
        try:
            openf1_telemetry = _get_openf1_session_telemetry(
                parsed_season,
                parsed_round,
                session_code,
                unique_laps,
                circuit_name,
            )
            if not unique_laps or openf1_telemetry["rows"]:
                return openf1_telemetry
            logger.warning(
                "OpenF1 returned no telemetry rows; trying the FastF1 fallback",
                extra={
                    "season": parsed_season,
                    "round": parsed_round,
                    "session": session_code,
                },
            )
        except Exception:
            logger.warning(
                "OpenF1 telemetry is unavailable; trying the FastF1 fallback",
                exc_info=True,
                extra={
                    "season": parsed_season,
                    "round": parsed_round,
                    "session": session_code,
                },
            )
    return _get_fastf1_session_telemetry(
        parsed_season,
        parsed_round,
        session_code,
        unique_laps,
        circuit_name,
    )
