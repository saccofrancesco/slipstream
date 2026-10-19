"""Typed, rate-limited access to OpenF1's free historical data API."""

import re
import unicodedata
from collections import deque
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from math import isfinite
from threading import Lock
from time import monotonic, sleep
from typing import Any, TypedDict

import requests

OPENF1_BASE_URL: str = "https://api.openf1.org/v1"
JOLPICA_BASE_URL: str = "https://api.jolpi.ca/ergast/f1"
OPENF1_FIRST_HISTORICAL_SEASON: int = 2023
_REQUEST_TIMEOUT_SECONDS: int = 30
_RATE_LIMIT_GRACE_SECONDS: float = 0.05
_HTTP_SESSION: requests.Session = requests.Session()
_HTTP_SESSION.headers.update(
    {
        "Accept": "application/json",
        "User-Agent": "Slipstream/1.0 (+https://github.com/saccofrancesco/slipstream)",
    }
)
_RATE_LIMIT_LOCK: Lock = Lock()
_HTTP_LOCK: Lock = Lock()
_REQUEST_TIMES: deque[float] = deque()


class OpenF1Driver(TypedDict):
    """Driver identity and team presentation fields for one session."""

    driver_number: int
    code: str
    full_name: str
    team_name: str
    team_color: str


class OpenF1Lap(TypedDict):
    """Official timing and sector boundaries for one completed lap."""

    driver_number: int
    lap_number: int
    date_start: datetime
    lap_duration: float
    sector_1_duration: float | None
    sector_2_duration: float | None
    is_pit_out_lap: bool


class OpenF1Stint(TypedDict):
    """Inclusive lap range covered by one tyre compound."""

    driver_number: int
    lap_start: int
    lap_end: int
    compound: str


class OpenF1SessionData(TypedDict):
    """Normalized OpenF1 rows needed by the Laps tab."""

    session_key: int
    drivers: list[OpenF1Driver]
    laps: list[OpenF1Lap]
    stints: list[OpenF1Stint]


class OpenF1Meeting(TypedDict):
    """OpenF1 event identity used to resolve a Jolpica championship round."""

    meeting_key: int
    circuit_key: int
    name: str
    starts_at: datetime


class OpenF1CarSample(TypedDict):
    """One timestamped OpenF1 car-data sample."""

    date: datetime
    speed: float
    throttle: float
    brake: int
    rpm: float
    gear: int


class OpenF1LocationSample(TypedDict):
    """One timestamped OpenF1 position sample."""

    date: datetime
    x: float
    y: float


_SESSION_NAMES: dict[str, tuple[str, ...]] = {
    "FP1": ("Practice 1",),
    "FP2": ("Practice 2",),
    "FP3": ("Practice 3",),
    "SQ": ("Sprint Qualifying", "Sprint Shootout"),
    "SS": ("Sprint Shootout", "Sprint Qualifying"),
    "S": ("Sprint",),
    "Q": ("Qualifying",),
    "R": ("Race",),
}


def _wait_for_rate_limit() -> None:
    """Reserve one request within OpenF1's 3/second and 30/minute limits."""
    with _RATE_LIMIT_LOCK:
        while True:
            now = monotonic()
            while _REQUEST_TIMES and now - _REQUEST_TIMES[0] >= 60:
                _REQUEST_TIMES.popleft()

            second_window = [stamp for stamp in _REQUEST_TIMES if now - stamp < 1]
            waits: list[float] = []
            if len(second_window) >= 3:
                waits.append(second_window[-3] + 1 - now)
            if len(_REQUEST_TIMES) >= 30:
                waits.append(_REQUEST_TIMES[0] + 60 - now)

            wait_seconds = max(waits, default=0)
            if wait_seconds <= 0:
                _REQUEST_TIMES.append(now)
                return
            sleep(wait_seconds + _RATE_LIMIT_GRACE_SECONDS)


def _request_rows(endpoint: str, params: dict[str, object]) -> list[dict[str, Any]]:
    """Return one OpenF1 collection after validating its JSON boundary."""
    for attempt in range(2):
        _wait_for_rate_limit()
        with _HTTP_LOCK:
            response = _HTTP_SESSION.get(
                f"{OPENF1_BASE_URL}/{endpoint}",
                params=params,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        if response.status_code != 429 or attempt == 1:
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError(f"OpenF1 {endpoint} returned an unexpected payload")
            return [row for row in payload if isinstance(row, dict)]

        retry_after = response.headers.get("Retry-After", "1")
        try:
            sleep(max(1.0, min(float(retry_after), 10.0)))
        except ValueError:
            sleep(1.0)
    return []


def _integer(value: object) -> int | None:
    """Normalize an integer-like JSON value without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _number(value: object) -> float | None:
    """Normalize a finite numeric JSON value."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _timestamp(value: object) -> datetime | None:
    """Parse an ISO timestamp and ensure it is timezone-aware."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@lru_cache(maxsize=8)
def _race_meetings(season: int) -> tuple[OpenF1Meeting, ...]:
    """Return chronological Grand Prix meetings for one season."""
    rows = _request_rows("meetings", {"year": season})
    meetings: list[OpenF1Meeting] = []
    for row in rows:
        name = str(row.get("meeting_name") or "")
        meeting_key = _integer(row.get("meeting_key"))
        circuit_key = _integer(row.get("circuit_key"))
        starts_at = _timestamp(row.get("date_start"))
        if (
            "grand prix" not in name.lower()
            or meeting_key is None
            or circuit_key is None
            or starts_at is None
        ):
            continue
        meetings.append(
            {
                "meeting_key": meeting_key,
                "circuit_key": circuit_key,
                "name": name,
                "starts_at": starts_at,
            }
        )
    meetings.sort(key=lambda item: item["starts_at"])
    return tuple(meetings)


def _normalized_event_name(value: str) -> str:
    """Return an accent- and punctuation-insensitive event name."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.decode().lower()).strip()


@lru_cache(maxsize=64)
def _jolpica_event_identity(season: int, round_number: int) -> tuple[str, date]:
    """Load the official race name/date used by Slipstream's archive route."""
    with _HTTP_LOCK:
        response = _HTTP_SESSION.get(
            f"{JOLPICA_BASE_URL}/{season}/{round_number}.json",
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    response.raise_for_status()
    payload = response.json()
    try:
        races = payload["MRData"]["RaceTable"]["Races"]
        race = races[0]
        name = str(race["raceName"])
        race_date = date.fromisoformat(str(race["date"]))
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise LookupError("The requested Jolpica event could not be found") from error
    return name, race_date


def _resolve_meeting(season: int, round_number: int) -> OpenF1Meeting:
    """Match a championship round without cancelled meetings shifting indexes."""
    event_name, race_date = _jolpica_event_identity(season, round_number)
    meetings = _race_meetings(season)
    normalized_name = _normalized_event_name(event_name)
    exact = next(
        (
            meeting
            for meeting in meetings
            if _normalized_event_name(meeting["name"]) == normalized_name
        ),
        None,
    )
    if exact is not None:
        return exact

    # Names occasionally differ between providers. A race normally starts two
    # or three days after the meeting's first session, making date proximity a
    # safe fallback while still rejecting an unrelated weekend.
    if meetings:
        nearest = min(
            meetings,
            key=lambda meeting: abs((race_date - meeting["starts_at"].date()).days),
        )
        if abs((race_date - nearest["starts_at"].date()).days) <= 7:
            return nearest
    raise LookupError("The requested OpenF1 meeting could not be found")


@lru_cache(maxsize=64)
def _meeting_sessions(meeting_key: int) -> tuple[tuple[str, int, bool], ...]:
    """Return stable session names, keys, and cancellation flags for a meeting."""
    sessions: list[tuple[str, int, bool]] = []
    for row in _request_rows("sessions", {"meeting_key": meeting_key}):
        name = str(row.get("session_name") or "")
        session_key = _integer(row.get("session_key"))
        if name and session_key is not None:
            sessions.append((name, session_key, row.get("is_cancelled") is True))
    return tuple(sessions)


@lru_cache(maxsize=64)
def get_openf1_session_key(season: int, round_number: int, session_code: str) -> int:
    """Resolve Slipstream's season/round/session coordinates to OpenF1."""
    if season < OPENF1_FIRST_HISTORICAL_SEASON:
        raise LookupError("OpenF1 historical data starts with the 2023 season")
    expected_names = _SESSION_NAMES.get(session_code)
    if expected_names is None:
        raise ValueError("The requested session is not supported")

    meeting_key = _resolve_meeting(season, round_number)["meeting_key"]
    sessions = _meeting_sessions(meeting_key)
    for expected_name in expected_names:
        for name, session_key, cancelled in sessions:
            if cancelled:
                continue
            if name == expected_name:
                return session_key
    raise LookupError("The requested OpenF1 session could not be found")


def get_openf1_circuit_key(season: int, round_number: int) -> int:
    """Return the F1 timing circuit key shared with FastF1's map metadata."""
    return _resolve_meeting(season, round_number)["circuit_key"]


@lru_cache(maxsize=64)
def _session_drivers(session_key: int) -> tuple[OpenF1Driver, ...]:
    """Load and normalize stable driver metadata for one session."""
    drivers: list[OpenF1Driver] = []
    seen_numbers: set[int] = set()
    for row in _request_rows("drivers", {"session_key": session_key}):
        number = _integer(row.get("driver_number"))
        code = str(row.get("name_acronym") or "").strip().upper()
        if number is None or number in seen_numbers or not code:
            continue
        color = str(row.get("team_colour") or "").strip().removeprefix("#")
        if len(color) != 6 or any(
            character not in "0123456789abcdefABCDEF" for character in color
        ):
            color = "808080"
        drivers.append(
            {
                "driver_number": number,
                "code": code,
                "full_name": str(row.get("full_name") or code).strip(),
                "team_name": str(row.get("team_name") or "").strip(),
                "team_color": f"#{color}",
            }
        )
        seen_numbers.add(number)
    return tuple(drivers)


@lru_cache(maxsize=32)
def _session_laps(session_key: int) -> tuple[OpenF1Lap, ...]:
    """Load completed timed laps for one historical session."""
    laps: list[OpenF1Lap] = []
    for row in _request_rows("laps", {"session_key": session_key}):
        driver_number = _integer(row.get("driver_number"))
        lap_number = _integer(row.get("lap_number"))
        starts_at = _timestamp(row.get("date_start"))
        duration = _number(row.get("lap_duration"))
        if (
            driver_number is None
            or lap_number is None
            or lap_number < 1
            or starts_at is None
            or duration is None
            or duration <= 0
        ):
            continue
        laps.append(
            {
                "driver_number": driver_number,
                "lap_number": lap_number,
                "date_start": starts_at,
                "lap_duration": duration,
                "sector_1_duration": _number(row.get("duration_sector_1")),
                "sector_2_duration": _number(row.get("duration_sector_2")),
                "is_pit_out_lap": bool(row.get("is_pit_out_lap")),
            }
        )
    return tuple(laps)


@lru_cache(maxsize=32)
def _session_stints(session_key: int) -> tuple[OpenF1Stint, ...]:
    """Load tyre stints for one historical session."""
    stints: list[OpenF1Stint] = []
    for row in _request_rows("stints", {"session_key": session_key}):
        driver_number = _integer(row.get("driver_number"))
        lap_start = _integer(row.get("lap_start"))
        lap_end = _integer(row.get("lap_end"))
        if driver_number is None or lap_start is None or lap_end is None:
            continue
        compound = str(row.get("compound") or "UNKNOWN").strip().upper()
        stints.append(
            {
                "driver_number": driver_number,
                "lap_start": lap_start,
                "lap_end": lap_end,
                "compound": (
                    compound if compound and compound != "NONE" else "UNKNOWN"
                ),
            }
        )
    return tuple(stints)


def get_openf1_session_data(
    season: int, round_number: int, session_code: str
) -> OpenF1SessionData:
    """Return drivers, timed laps, and tyre stints for one session."""
    session_key = get_openf1_session_key(season, round_number, session_code)
    return {
        "session_key": session_key,
        "drivers": list(_session_drivers(session_key)),
        "laps": list(_session_laps(session_key)),
        "stints": list(_session_stints(session_key)),
    }


def find_openf1_lap(
    season: int,
    round_number: int,
    session_code: str,
    driver_code: str,
    lap_number: int,
) -> tuple[int, OpenF1Lap]:
    """Resolve a selected display driver and lap to its OpenF1 record."""
    session_key = get_openf1_session_key(season, round_number, session_code)
    normalized_code = driver_code.strip().upper()
    driver_number = next(
        (
            driver["driver_number"]
            for driver in _session_drivers(session_key)
            if driver["code"] == normalized_code
        ),
        None,
    )
    if driver_number is None:
        raise LookupError("The selected OpenF1 driver could not be found")
    lap = next(
        (
            item
            for item in _session_laps(session_key)
            if item["driver_number"] == driver_number
            and item["lap_number"] == lap_number
        ),
        None,
    )
    if lap is None:
        raise LookupError("The selected OpenF1 lap could not be found")
    return session_key, lap


def get_openf1_car_data(
    session_key: int, driver_number: int, lap: OpenF1Lap
) -> list[OpenF1CarSample]:
    """Load normalized car channels within one lap's official boundaries."""
    start = lap["date_start"]
    end = start + timedelta(seconds=lap["lap_duration"])
    rows = _request_rows(
        "car_data",
        {
            "session_key": session_key,
            "driver_number": driver_number,
            # OpenF1's comparison syntax is expressed as ``date>=value``.
            # The equals sign is the query separator, so the parameter names
            # passed to Requests are ``date>`` and ``date<``.
            "date>": start.isoformat(),
            "date<": end.isoformat(),
        },
    )
    samples: list[OpenF1CarSample] = []
    for row in rows:
        sampled_at = _timestamp(row.get("date"))
        speed = _number(row.get("speed"))
        throttle = _number(row.get("throttle"))
        brake = _integer(row.get("brake"))
        rpm = _number(row.get("rpm"))
        gear = _integer(row.get("n_gear"))
        if (
            sampled_at is None
            or speed is None
            or throttle is None
            or brake is None
            or rpm is None
            or gear is None
        ):
            continue
        samples.append(
            {
                "date": sampled_at,
                "speed": speed,
                "throttle": throttle,
                "brake": int(bool(brake)),
                "rpm": rpm,
                "gear": gear,
            }
        )
    return samples


def get_openf1_location_data(
    session_key: int, driver_number: int, lap: OpenF1Lap
) -> list[OpenF1LocationSample]:
    """Load normalized x/y samples within one lap's official boundaries."""
    start = lap["date_start"]
    end = start + timedelta(seconds=lap["lap_duration"])
    rows = _request_rows(
        "location",
        {
            "session_key": session_key,
            "driver_number": driver_number,
            "date>": start.isoformat(),
            "date<": end.isoformat(),
        },
    )
    samples: list[OpenF1LocationSample] = []
    for row in rows:
        sampled_at = _timestamp(row.get("date"))
        x = _number(row.get("x"))
        y = _number(row.get("y"))
        if sampled_at is None or x is None or y is None:
            continue
        samples.append({"date": sampled_at, "x": x, "y": y})
    return samples
