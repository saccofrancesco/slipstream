"""Distance-aligned OpenF1 telemetry for selected session laps."""

import logging
from dataclasses import dataclass
from math import cos, isfinite, pi, sin
from typing import TypedDict

import numpy as np
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
logger: logging.Logger = logging.getLogger(__name__)


class TelemetryLap(TypedDict):
    """Identity, official timing, and distance-aligned elapsed samples."""

    key: str
    driver: str
    number: int
    seconds: float
    start_index: int
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
            elapsed = values["elapsed"][index]
            if not isfinite(float(elapsed)):
                continue
            key = lap.key
            row[f"speed_{key}"] = round(float(values["speed"][index]), 1)
            if isfinite(float(baseline_elapsed[index])):
                row[f"delta_{key}"] = round(float(elapsed - baseline_elapsed[index]), 3)
            row[f"throttle_{key}"] = round(float(values["throttle"][index]), 1)
            row[f"brake_{key}"] = int(values["brake"][index])
            row[f"rpm_{key}"] = round(float(values["rpm"][index]))
            row[f"gear_{key}"] = round(float(values["gear"][index]))
        rows.append(row)
    return rows


def _serialize_telemetry_laps(
    available: list[_LapSamples],
    sampled: dict[str, dict[str, np.ndarray]],
    start_indices: dict[str, int],
) -> list[TelemetryLap]:
    """Serialize the shared lap identity and elapsed-time chart data."""
    return [
        {
            "key": lap.key,
            "driver": lap.driver,
            "number": lap.number,
            "seconds": lap.seconds,
            "start_index": start_indices[lap.key],
            "elapsed": [
                round(float(value), 4)
                for value in sampled[lap.key]["elapsed"][start_indices[lap.key] :]
            ],
        }
        for lap in available
    ]


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


def _aligned_start_distance(samples: _LapSamples, reference_length: float) -> float:
    """Return a lap's recorded start position when its finish is aligned."""
    return max(0.0, reference_length - float(samples.distance[-1]))


def _distance_grid(
    available: list[_LapSamples], reference_length: float
) -> tuple[np.ndarray, dict[str, int]]:
    """Build the shared grid with an exact sample at every lap start."""
    starts = {
        lap.key: _aligned_start_distance(lap, reference_length) for lap in available
    }
    grid = np.unique(
        np.concatenate(
            (
                np.arange(0, reference_length, SAMPLE_SPACING_METRES),
                np.array([reference_length, *starts.values()], dtype=float),
            )
        )
    )
    return grid, {
        key: int(np.searchsorted(grid, start)) for key, start in starts.items()
    }


def _resample(
    samples: _LapSamples, grid: np.ndarray, reference_length: float
) -> dict[str, np.ndarray]:
    """Map one lap's samples without stretching its recorded distance."""
    start_distance = _aligned_start_distance(samples, reference_length)
    aligned_distance = samples.distance + start_distance
    # At a stationary sample, retain the latest value at that distance.
    unique_distance, reverse_indices = np.unique(
        aligned_distance[::-1], return_index=True
    )
    indices = len(aligned_distance) - 1 - reverse_indices
    covered = (grid >= start_distance) & (grid <= reference_length)
    covered_grid = grid[covered]

    def continuous(values: np.ndarray) -> np.ndarray:
        result = np.full(len(grid), np.nan, dtype=float)
        result[covered] = np.interp(covered_grid, unique_distance, values[indices])
        return result

    def discrete(values: np.ndarray) -> np.ndarray:
        result = np.full(len(grid), np.nan, dtype=float)
        previous = np.searchsorted(unique_distance, covered_grid, side="right") - 1
        result[covered] = values[indices[np.clip(previous, 0, len(indices) - 1)]]
        return result

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
    """Rotate track coordinates clockwise using the shared map transform."""
    angle = degrees / 180 * pi
    return x * cos(angle) + y * sin(angle), -x * sin(angle) + y * cos(angle)


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
    segments: list[TelemetryTrackSegment] = []
    for index in range(MINI_SECTOR_COUNT):
        candidates = [
            lap
            for lap in laps
            if _aligned_start_distance(lap, float(grid[-1])) <= boundaries[index]
        ]
        if not candidates:
            continue
        elapsed_at_boundaries = {
            lap.key: np.interp(
                boundaries[index : index + 2],
                grid,
                sampled[lap.key]["elapsed"],
            )
            for lap in candidates
        }
        # Python's min keeps the first item on exact ties, matching lap selection order.
        winner = min(
            candidates,
            key=lambda lap: float(
                elapsed_at_boundaries[lap.key][1] - elapsed_at_boundaries[lap.key][0]
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


def _openf1_track_geometry(
    baseline: _LapSamples,
    grid: np.ndarray,
    available: list[_LapSamples],
    sampled: dict[str, dict[str, np.ndarray]],
    locations: list[OpenF1LocationSample],
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
    rotation = TRACK_ROTATION_ADJUSTMENTS.get(circuit_name, 0.0)
    preserve_orientation = circuit_name in TRACK_ROTATION_ADJUSTMENTS
    trace_x, trace_y = _rotate_coordinates(trace_x, trace_y, rotation)

    return (
        [
            {"x": round(float(x), 3), "y": round(float(y), 3)}
            for x, y in zip(trace_x, trace_y, strict=True)
        ],
        _mini_sector_segments(grid, available, sampled),
        [],
        preserve_orientation,
    )


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
    reference = max(available, key=lambda lap: float(lap.distance[-1]))
    length = float(reference.distance[-1])
    grid, start_indices = _distance_grid(available, length)
    sampled = {lap.key: _resample(lap, grid, length) for lap in available}
    locations: list[OpenF1LocationSample] = []
    if reference.openf1_lap is not None:
        try:
            session_key = get_openf1_session_key(season, round_number, session_code)
            locations = get_openf1_location_data(
                session_key,
                reference.openf1_lap["driver_number"],
                reference.openf1_lap,
            )
        except LookupError, ValueError, KeyError, TypeError, RequestException:
            # Car channels remain useful when optional position samples fail.
            locations = []
    (
        track_points,
        track_segments,
        track_corners,
        preserve_orientation,
    ) = _openf1_track_geometry(
        reference, grid, available, sampled, locations, circuit_name
    )
    rows = _telemetry_rows(grid, available, sampled, baseline)

    return {
        "rows": rows,
        "laps": _serialize_telemetry_laps(available, sampled, start_indices),
        "corners": [],
        "sectors": _openf1_sector_distances(reference),
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
    """Load selected laps from OpenF1's historical timing and telemetry data."""
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

    unavailable = [f"{driver} lap {number}" for driver, number in unique_laps]
    if parsed_season < OPENF1_FIRST_HISTORICAL_SEASON:
        return _empty_session_telemetry(unavailable)
    try:
        return _get_openf1_session_telemetry(
            parsed_season,
            parsed_round,
            session_code,
            unique_laps,
            circuit_name,
        )
    except Exception:
        logger.warning(
            "OpenF1 telemetry is unavailable for the selected laps",
            exc_info=True,
            extra={
                "season": parsed_season,
                "round": parsed_round,
                "session": session_code,
            },
        )
        return _empty_session_telemetry(unavailable)
