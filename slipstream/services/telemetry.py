"""Distance-aligned FastF1 telemetry for selected session laps."""

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from threading import Lock
from typing import TypedDict

import fastf1
import numpy as np
import pandas as pd
from fastf1.core import Lap, Session
from fastf1.exceptions import DataNotLoadedError

SAMPLE_SPACING_METRES: int = 5
_SESSION_LOCK: Lock = Lock()


class TelemetryLap(TypedDict):
    """Identity and official timing for one plotted lap."""

    key: str
    driver: str
    number: int
    seconds: float


class TelemetryCorner(TypedDict):
    """One circuit corner on the selected baseline lap's distance axis."""

    label: str
    distance: int
    lane: int


class TelemetrySector(TypedDict):
    """One sector boundary projected onto the selected baseline lap."""

    label: str
    distance: int


class SessionTelemetry(TypedDict):
    """Six channel series sharing one distance grid."""

    rows: list[dict[str, float | int]]
    laps: list[TelemetryLap]
    corners: list[TelemetryCorner]
    sectors: list[TelemetrySector]
    unavailable: list[str]
    baseline_key: str
    distance_metres: int


@dataclass
class _LapSamples:
    """Original car samples for one timed lap."""

    lap: Lap
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


@lru_cache(maxsize=1)
def _cached_session(season: int, round_number: int, session_code: str) -> Session:
    """Keep the last telemetry-loaded FastF1 session in this process."""
    session: Session = fastf1.get_session(season, round_number, session_code)
    session.load(laps=True, telemetry=True, weather=False, messages=False)
    return session


def _session(season: int, round_number: int, session_code: str) -> Session:
    """Serialize the first load so concurrent requests do not duplicate it."""
    with _SESSION_LOCK:
        return _cached_session(season, round_number, session_code)


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
    elapsed = (car["SessionTime"] - start_time).dt.total_seconds().to_numpy(
        dtype=float
    )
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


def _corner_distances(session: Session, baseline: _LapSamples) -> list[TelemetryCorner]:
    """Project circuit corner coordinates onto the baseline lap's position trace."""
    try:
        info = session.get_circuit_info()
        position = baseline.lap.get_pos_data(interpolate_edges=True)
    except Exception:
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
        except (TypeError, ValueError):
            continue
        if not valid_corner:
            continue
        nearest = int(np.argmin((x - float(corner_x)) ** 2 + (y - float(corner_y)) ** 2))
        distance = int(round(position_distances[nearest]))
        if not 0 <= distance <= baseline.distance[-1]:
            continue
        letter = corner.get("Letter")
        suffix = "" if pd.isna(letter) else str(letter).strip()
        corners.append(
            {"label": f"{int(number)}{suffix}", "distance": distance, "lane": 0}
        )
    corners.sort(key=lambda corner: corner["distance"])
    last_by_lane = [-1_000, -1_000, -1_000]
    for corner in corners:
        lane = next(
            (
                index
                for index, last in enumerate(last_by_lane)
                if corner["distance"] - last >= 140
            ),
            min(range(3), key=lambda index: last_by_lane[index]),
        )
        corner["lane"] = lane
        last_by_lane[lane] = corner["distance"]
    return corners


def _sector_distances(baseline: _LapSamples) -> list[TelemetrySector]:
    """Project sector timing boundaries onto the baseline's distance trace."""
    sectors: list[TelemetrySector] = []
    for label, field in (("S2", "Sector1SessionTime"), ("S3", "Sector2SessionTime")):
        boundary = baseline.lap.get(field)
        if pd.isna(boundary):
            continue
        boundary_seconds = float(boundary.total_seconds())
        if not isfinite(boundary_seconds):
            continue
        if not baseline.session_time[0] <= boundary_seconds <= baseline.session_time[-1]:
            continue
        distance = int(round(float(np.interp(
            boundary_seconds, baseline.session_time, baseline.distance
        ))))
        sectors.append({"label": label, "distance": distance})
    return sectors


def get_session_telemetry(
    season: int | str,
    round_number: int | str,
    session_code: str,
    selected_laps: list[tuple[str, int]],
) -> SessionTelemetry:
    """Load and align the selected timed laps for all six telemetry charts.

    Args:
        season: Championship year.
        round_number: Event round within the season.
        session_code: FastF1 session identifier.
        selected_laps: Ordered driver-code and lap-number pairs.

    Returns:
        Shared distance rows, plotted lap metadata, baseline, and corners.
    """
    if session_code not in {"FP1", "FP2", "FP3", "SQ", "SS", "S", "Q", "R"}:
        raise ValueError("The requested session is not supported")
    session = _session(int(season), int(round_number), session_code)
    available: list[_LapSamples] = []
    unavailable: list[str] = []
    for driver, number in dict.fromkeys(selected_laps):
        label = f"{driver} lap {number}"
        matching = session.laps[
            (session.laps["Driver"] == driver) & (session.laps["LapNumber"] == number)
        ]
        if matching.empty:
            unavailable.append(label)
            continue
        try:
            available.append(_lap_samples(matching.iloc[0], driver, number))
        except (ValueError, KeyError, TypeError, IndexError, DataNotLoadedError):
            unavailable.append(label)

    if not available:
        return {
            "rows": [],
            "laps": [],
            "corners": [],
            "sectors": [],
            "unavailable": unavailable,
            "baseline_key": "",
            "distance_metres": 0,
        }

    baseline = min(available, key=lambda lap: lap.seconds)
    length = float(baseline.distance[-1])
    grid = np.append(np.arange(0, length, SAMPLE_SPACING_METRES), length)
    sampled = {lap.key: _resample(lap, grid, length) for lap in available}
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
            row[f"rpm_{key}"] = int(round(float(values["rpm"][index])))
            row[f"gear_{key}"] = int(round(float(values["gear"][index])))
        rows.append(row)

    return {
        "rows": rows,
        "laps": [
            {
                "key": lap.key,
                "driver": lap.driver,
                "number": lap.number,
                "seconds": lap.seconds,
            }
            for lap in available
        ],
        "corners": _corner_distances(session, baseline),
        "sectors": _sector_distances(baseline),
        "unavailable": unavailable,
        "baseline_key": baseline.key,
        "distance_metres": int(round(length)),
    }
