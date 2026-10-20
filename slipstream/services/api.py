"""Fetch and normalize Formula 1 schedules and championship standings."""

import json
import logging
import re
from datetime import UTC, date, datetime, time, timedelta, timezone
from functools import lru_cache
from math import ceil, isfinite
from statistics import median
from typing import Any, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# FastF1 provides the Ergast client used to retrieve calendars and standings.
import fastf1
import fastf1.plotting
import pandas as pd
import requests
from fastf1.core import Session
from fastf1.ergast import Ergast
from fastf1.exceptions import DataNotLoadedError

from .cache import TTLCache
from .catalog import COMPOUND_COLORS, EVENT_SESSION_FIELDS, SUPPORTED_SESSION_CODES
from .flags import flag_for_circuit_country
from .openf1 import (
    OPENF1_FIRST_HISTORICAL_SEASON,
    OpenF1SessionData,
    get_openf1_session_data,
)

# Keep FastF1's unbounded parsed cache disabled. The application-level cache in
# cached.py applies explicit freshness windows to normalized provider results.
fastf1.Cache.set_disabled()

# Reuse one Ergast client for schedule and standings requests.
ergast: Ergast = Ergast()
logger: logging.Logger = logging.getLogger(__name__)
_RACE_SCHEDULE_CACHE: TTLCache = TTLCache(maxsize=8)


class ScheduledSession(TypedDict):
    """One session with its UTC start and optional circuit time offset."""

    code: str
    name: str
    time: str
    end_time: str
    starts_at: str
    ends_at: str
    track_offset_minutes: int | None
    results_available: bool


class TrackSessionDetails(TypedDict):
    """Circuit offset and optional scheduled UTC end for one session."""

    offset_minutes: int
    ends_at: str


class ScheduleDay(TypedDict):
    """Sessions grouped under one UTC calendar date."""

    day: str
    date: str
    date_iso: str
    sessions: list[ScheduledSession]


class RaceWeekend(TypedDict):
    """Normalized event details and schedule rows consumed by ResultsState."""

    season: str
    status: str
    round: str
    race_name: str
    circuit_name: str
    locality: str
    country: str
    country_flag: str
    date_range: str
    schedule_days: list[ScheduleDay]


class PastEvent(TypedDict):
    """Compact display fields for a completed race in the season archive."""

    round: str
    race_name: str
    race_date: str
    circuit_name: str
    country: str
    country_flag: str


class SessionOption(TypedDict):
    """One session in an event's published weekend schedule."""

    code: str
    name: str


class EventDetails(TypedDict):
    """Display-ready details and available sessions for one event."""

    season: str
    round: str
    race_name: str
    circuit_name: str
    locality: str
    country: str
    country_flag: str
    date_range: str
    sessions: list[SessionOption]


class DriverClassification(TypedDict):
    """One driver's result with a display value and its timing label."""

    position: str
    given_name: str
    family_name: str
    team: str
    team_color: str
    time: str
    time_label: str


class LapDriver(TypedDict):
    """A driver available for selection in a session's lap chart."""

    code: str
    name: str
    team: str
    team_color: str


class LapPoint(TypedDict):
    """One timed lap with the compound and outlier classification."""

    driver: str
    number: int
    seconds: float
    time: str
    compound: str
    compound_color: str
    outlier: bool


class SessionLaps(TypedDict):
    """Display-ready drivers and laps from one archive session."""

    drivers: list[LapDriver]
    laps: list[LapPoint]


def _race_schedule(season: int) -> list[dict[str, Any]]:
    """Return one cached raw race calendar for all schedule views."""
    ttl_seconds: int = 5 * 60 if season >= date.today().year else 24 * 60 * 60
    return _RACE_SCHEDULE_CACHE.get_or_load(
        ("race_schedule", season),
        ttl_seconds,
        lambda: ergast.get_race_schedule(season=season, result_type="raw", limit=1000),
    )


def get_available_seasons(start_year: int = 1950) -> list[str]:
    """Return the available championship seasons, newest first.

    Args:
        start_year: Earliest season to include.

    Returns:
        Season years formatted as strings for championship requests.
    """
    # The raw Ergast response is a list of records; keep that boundary typed
    # before extracting the small string-only shape used by page state.
    response: list[dict[str, Any]] = ergast.get_seasons(result_type="raw", limit=1000)
    if not response:
        return []

    # Deduplicate season values before presenting them newest first.
    seasons: set[str] = {
        format_value(row.get("season"))
        for row in response
        if row.get("season") is not None and int(row["season"]) >= start_year
    }
    return sorted(seasons, key=int, reverse=True)


def get_completed_races(season: int | str) -> list[dict[str, str]]:
    """Return completed races for a season in calendar order.

    Args:
        season: Season year selected by the user.

    Returns:
        Race records with round numbers and display labels.
    """
    response: list[dict[str, Any]] = _race_schedule(int(season))
    if not response:
        return []

    today: date = date.today()
    races: list[dict[str, str]] = []
    for race in response:
        round_number: str = format_value(race.get("round"))
        race_name: str = format_value(race.get("raceName"))
        race_date: date | None = parse_race_date(race.get("date"))

        # A standings snapshot is only selectable after race day. Leave races
        # without a parseable date available, as the API cannot classify them.
        if not round_number or not race_name:
            continue
        if race_date is not None and race_date >= today:
            continue

        races.append(
            {
                "round": round_number,
                "label": f"Round {round_number} · {race_name}",
            }
        )

    return sorted(races, key=lambda race: int(race["round"]))


def get_past_events(season: int | str, today: date | None = None) -> list[PastEvent]:
    """Return races before today, newest first, for one season.

    Args:
        season: Calendar season to show in the archive.
        today: Date used to classify past races, defaulting to the server date.

    Returns:
        Compact race records ordered from the latest race to the opener.
    """
    current_date: date = today or date.today()
    response: list[dict[str, Any]] = _race_schedule(int(season))
    dated_events: list[tuple[date, PastEvent]] = []
    for race in response:
        race_date = parse_race_date(race.get("date"))
        round_number = format_value(race.get("round"))
        race_name = format_value(race.get("raceName"))
        if (
            race_date is None
            or race_date >= current_date
            or not round_number
            or not race_name
        ):
            continue

        circuit: dict[str, Any] = race.get("Circuit") or {}
        location: dict[str, Any] = circuit.get("Location") or {}
        country = format_value(location.get("country"))
        dated_events.append(
            (
                race_date,
                {
                    "round": round_number,
                    "race_name": race_name,
                    "race_date": race_date.strftime("%d %b %Y"),
                    "circuit_name": format_value(circuit.get("circuitName")),
                    "country": country,
                    "country_flag": flag_for_circuit_country(country),
                },
            )
        )

    return [
        event
        for _, event in sorted(dated_events, key=lambda item: item[0], reverse=True)
    ]


def get_event_details(
    season: int | str, round_number: int | str
) -> EventDetails | None:
    """Return one event's display fields and its scheduled sessions.

    Args:
        season: Championship season containing the event.
        round_number: Event round in that season.

    Returns:
        Normalized event details, or ``None`` when the route does not match an
        event in the published schedule.
    """
    coordinates: tuple[int, int] | None = parse_event_coordinates(season, round_number)
    if coordinates is None:
        return None
    parsed_season, parsed_round = coordinates

    response: list[dict[str, Any]] = _race_schedule(parsed_season)
    race: dict[str, Any] | None = next(
        (row for row in response if parse_integer(row.get("round")) == parsed_round),
        None,
    )
    if race is None:
        return None

    race_name = format_value(race.get("raceName"))
    race_date = parse_race_date(race.get("date"))
    if not race_name or race_date is None:
        return None

    circuit: dict[str, Any] = race.get("Circuit") or {}
    location: dict[str, Any] = circuit.get("Location") or {}
    country = format_value(location.get("country"))

    scheduled: list[tuple[date, bool, str, int, SessionOption]] = []
    session_dates: list[date] = []
    sprint_qualifying_added = False
    for order, (field, code, label) in enumerate(EVENT_SESSION_FIELDS):
        raw_session: object = race.get(field)
        if _is_missing(raw_session) or (
            isinstance(raw_session, (dict, str)) and not raw_session
        ):
            continue

        # Some older schedule responses contain dates as strings rather than
        # session dictionaries; include the published option in either form.
        session_data: dict[str, Any] = (
            raw_session if isinstance(raw_session, dict) else {}
        )
        session_date = parse_race_date(
            session_data.get("date") if session_data else raw_session
        )
        session_date = session_date or race_date
        if session_date > race_date:
            continue

        if field in ("SprintQualifying", "SprintShootout"):
            if sprint_qualifying_added:
                continue
            sprint_qualifying_added = True

        session_time = format_session_time(session_data.get("time"))
        scheduled.append(
            (
                session_date,
                session_time == "TBD",
                session_time,
                order,
                {"code": code, "name": label},
            )
        )
        session_dates.append(session_date)

    # Race is a guaranteed selector option, even when the schedule only has a
    # date and omits the optional session start time.
    race_time = format_session_time(race.get("time"))
    scheduled.append(
        (
            race_date,
            race_time == "TBD",
            race_time,
            len(EVENT_SESSION_FIELDS),
            {"code": "R", "name": "Race"},
        )
    )
    session_dates.append(race_date)
    session_options: list[SessionOption] = [
        option for _, _, _, _, option in sorted(scheduled, key=lambda item: item[:4])
    ]

    start_date = min(session_dates, default=race_date)
    return {
        "season": str(parsed_season),
        "round": str(parsed_round),
        "race_name": race_name,
        "circuit_name": format_value(circuit.get("circuitName")),
        "locality": format_value(location.get("locality")),
        "country": country,
        "country_flag": flag_for_circuit_country(country),
        "date_range": (
            f"{start_date.strftime('%d %b')} – {race_date.strftime('%d %b %Y')}"  # noqa: RUF001 - rendered date-range punctuation.
        ),
        "sessions": session_options,
    }


def get_session_classification(
    season: int | str,
    round_number: int | str,
    session_code: str,
) -> list[DriverClassification]:
    """Load and normalize the selected session's driver classification.

    Practice sessions are ordered by each driver's fastest valid lap. Other
    sessions retain FastF1's classified position order. Timings are normalized
    against the first classified driver where comparable data exists.

    Args:
        season: Championship season containing the event.
        round_number: Event round in that season.
        session_code: FastF1 session identifier, such as ``"FP1"`` or ``"R"``.

    Returns:
        Driver classification rows ordered for display. An empty list means
        the session loaded but did not publish result rows.

    Raises:
        ValueError: If a route value or session identifier is invalid.
        Exception: Propagates FastF1 loading errors for the page to report.
    """
    coordinates: tuple[int, int] | None = parse_event_coordinates(season, round_number)
    if coordinates is None:
        raise ValueError("A supported numeric season and round are required.")
    parsed_season, parsed_round = coordinates
    if session_code not in SUPPORTED_SESSION_CODES:
        raise ValueError("The requested session is not supported.")

    practice_session: bool = session_code in {"FP1", "FP2", "FP3"}
    # FastF1 needs lap data for practice classification. Other sessions only
    # need their result table, so skip the larger lap and telemetry payloads.
    session: Session = fastf1.get_session(parsed_season, parsed_round, session_code)
    session.load(
        laps=practice_session,
        telemetry=False,
        weather=False,
        messages=False,
    )
    result_rows: list[dict[str, Any]] = session.results.to_dict(orient="records")
    if not result_rows:
        return []

    fastest_laps: dict[str, Any] = {}
    if practice_session:
        lap_results = session.laps
        if "Deleted" in lap_results.columns:
            deleted_laps = lap_results["Deleted"].map(
                lambda value: not _is_missing(value) and bool(value)
            )
            lap_results = lap_results[~deleted_laps]
        if not lap_results.empty:
            for lap in lap_results[["Driver", "LapTime"]].to_dict(orient="records"):
                driver_code = format_value(lap.get("Driver"))
                lap_time = lap.get("LapTime")
                if not driver_code or _is_missing(lap_time):
                    continue
                current_best = fastest_laps.get(driver_code)
                if current_best is None or lap_time < current_best:
                    fastest_laps[driver_code] = lap_time

    def fastest_lap_sort_key(row: dict[str, Any]) -> tuple[bool, float, str]:
        """Place timed practice results first, fastest lap before slower laps."""
        lap_time = fastest_laps.get(_classification_driver_code(row))
        seconds = _time_seconds(lap_time)
        return (
            seconds is None,
            seconds if seconds is not None else 0.0,
            _classification_driver_code(row),
        )

    def classified_sort_key(
        row_and_index: tuple[int, dict[str, Any]],
    ) -> tuple[bool, float, int]:
        """Keep the published numeric result order, with unclassified rows last."""
        index, row = row_and_index
        position = _position_number(
            _first_present(row.get("Position"), row.get("ClassifiedPosition"))
        )
        return position is None, position if position is not None else 0.0, index

    if practice_session:
        ordered_rows = sorted(result_rows, key=fastest_lap_sort_key)
    else:
        ordered_rows = [
            row for _, row in sorted(enumerate(result_rows), key=classified_sort_key)
        ]

    # Before 2023, Sprint Qualifying was a race-like session. Its result rows
    # contain total race times instead of Q1/Q2/Q3 lap times.
    qualifying_session: bool = session_code in {"Q", "SS"} or (
        session_code == "SQ"
        and any(
            not _is_missing(row.get(segment))
            for row in ordered_rows
            for segment in ("Q1", "Q2", "Q3")
        )
    )
    leader_row = ordered_rows[0]
    leader_lap_seconds: float | None = None
    leader_race_seconds: float | None = None
    leader_laps: int | None = None
    if practice_session:
        leader_lap_seconds = _time_seconds(
            fastest_laps.get(_classification_driver_code(leader_row))
        )
    elif qualifying_session:
        leader_lap_seconds = _time_seconds(leader_row.get("Q3"))
    else:
        leader_race_seconds = _time_seconds(leader_row.get("Time"))
        leader_laps = _lap_count(leader_row.get("Laps"))

    classification: list[DriverClassification] = []
    for index, row in enumerate(ordered_rows, start=1):
        driver_code = _classification_driver_code(row)
        team = format_value(row.get("TeamName"))
        team_id = format_value(row.get("TeamId"))
        team_color = get_team_color(
            [{"constructorId": team_id, "name": team}],
            row.get("TeamColor"),
            season=parsed_season,
            round_number=parsed_round,
        )
        given_name = format_value(row.get("FirstName"))
        family_name = format_value(row.get("LastName"))
        if not given_name and not family_name:
            given_name, _, family_name = format_value(row.get("FullName")).partition(
                " "
            )

        if practice_session:
            fastest_lap = fastest_laps.get(driver_code)
            position = str(index) if fastest_lap is not None else "—"
            time_label, result_time = _lap_timing(
                fastest_lap, leader_lap_seconds, index == 1
            )
        else:
            position = (
                _format_position(
                    _first_present(row.get("Position"), row.get("ClassifiedPosition"))
                )
                or "—"
            )
            if qualifying_session:
                time_label, result_time = _qualifying_timing(
                    row, position, leader_lap_seconds
                )
            else:
                time_label, result_time = _race_timing(
                    row, index == 1, leader_race_seconds, leader_laps
                )

        classification.append(
            {
                "position": position,
                "given_name": given_name,
                "family_name": family_name,
                "team": team,
                "team_color": team_color,
                "time": result_time or "—",
                "time_label": time_label,
            }
        )

    return classification


def has_session_results(
    season: int | str, round_number: int | str, session_code: str
) -> bool:
    """Report whether FastF1 has published driver result rows for a session.

    Args:
        season: Championship season containing the event.
        round_number: Event round in that season.
        session_code: FastF1 session identifier from the weekend schedule.

    Returns:
        Whether at least one driver result row is available.
    """
    coordinates: tuple[int, int] | None = parse_event_coordinates(season, round_number)
    if coordinates is None or session_code not in SUPPORTED_SESSION_CODES:
        return False
    parsed_season, parsed_round = coordinates

    session: Session = fastf1.get_session(parsed_season, parsed_round, session_code)
    session.load(
        laps=False,
        telemetry=False,
        weather=False,
        messages=False,
    )
    return not session.results.empty


def _quick_lap_threshold(lap_times: list[float]) -> float | None:
    """Return a 107% pace limit based on the quickest clean laps.

    The median of the quickest tenth avoids letting one unusually fast lap
    determine the limit. In a wholly wet session, its wet pace remains the
    baseline; in mixed conditions, a few very slow laps cannot raise it.

    Args:
        lap_times: Clean timed laps for one driver, in seconds.

    Returns:
        The slow-lap cutoff, or ``None`` when no clean laps are available.
    """
    if not lap_times:
        return None
    quick_count = max(3, ceil(len(lap_times) * 0.1))
    return median(sorted(lap_times)[:quick_count]) * 1.07


def _flag_slow_laps(drivers: list[LapDriver], laps: list[LapPoint]) -> None:
    """Add the per-driver 107% outlier flag to normalized lap rows."""
    for driver in drivers:
        driver_laps = [lap for lap in laps if lap["driver"] == driver["code"]]
        baseline = [lap["seconds"] for lap in driver_laps if not lap["outlier"]]
        threshold = _quick_lap_threshold(baseline)
        if threshold is not None:
            for lap in driver_laps:
                lap["outlier"] = lap["outlier"] or lap["seconds"] > threshold


def _normalize_openf1_laps(data: OpenF1SessionData) -> SessionLaps:
    """Convert OpenF1 timing and stint rows to the existing Laps-tab contract."""
    drivers: list[LapDriver] = [
        {
            "code": driver["code"],
            "name": driver["full_name"],
            "team": driver["team_name"],
            "team_color": driver["team_color"],
        }
        for driver in data["drivers"]
    ]
    codes_by_number = {
        driver["driver_number"]: driver["code"] for driver in data["drivers"]
    }
    stints_by_driver: dict[int, list[tuple[int, int, str]]] = {}
    for stint in data["stints"]:
        stints_by_driver.setdefault(stint["driver_number"], []).append(
            (stint["lap_start"], stint["lap_end"], stint["compound"])
        )

    laps: list[LapPoint] = []
    for row in data["laps"]:
        code = codes_by_number.get(row["driver_number"], "")
        if not code:
            continue
        compound = next(
            (
                name
                for start, end, name in stints_by_driver.get(row["driver_number"], [])
                if start <= row["lap_number"] <= end
            ),
            "UNKNOWN",
        )
        seconds = row["lap_duration"]
        laps.append(
            {
                "driver": code,
                "number": row["lap_number"],
                "seconds": seconds,
                "time": _format_classification_time(timedelta(seconds=seconds)),
                "compound": compound,
                "compound_color": COMPOUND_COLORS.get(
                    compound, COMPOUND_COLORS["UNKNOWN"]
                ),
                "outlier": row["is_pit_out_lap"],
            }
        )

    _flag_slow_laps(drivers, laps)
    timed_codes = {lap["driver"] for lap in laps}
    return {
        "drivers": [driver for driver in drivers if driver["code"] in timed_codes],
        "laps": laps,
    }


def get_session_laps(
    season: int | str, round_number: int | str, session_code: str
) -> SessionLaps:
    """Load timed laps and team metadata for an archive session.

    Outliers include laps flagged inaccurate or deleted by FastF1, pit laps,
    and laps slower than 107% of each driver's quickest clean-lap pace. They
    remain available when the chart's outlier switch is enabled.

    Args:
        season: Championship season containing the event.
        round_number: Event round in that season.
        session_code: FastF1 session identifier.

    Returns:
        Selectable drivers and timed laps, including outlier flags.
    """
    coordinates: tuple[int, int] | None = parse_event_coordinates(season, round_number)
    if coordinates is None:
        raise ValueError("A supported numeric season and round are required.")
    parsed_season, parsed_round = coordinates
    if session_code not in SUPPORTED_SESSION_CODES:
        raise ValueError("The requested session is not supported.")

    if parsed_season >= OPENF1_FIRST_HISTORICAL_SEASON:
        try:
            openf1_laps = _normalize_openf1_laps(
                get_openf1_session_data(
                    parsed_season,
                    parsed_round,
                    session_code,
                )
            )
            if openf1_laps["laps"]:
                return openf1_laps
        except Exception:
            # Keep cached/local FastF1 data and the Ergast race feed as
            # resilience paths when OpenF1 is temporarily unavailable.
            logger.warning(
                "OpenF1 lap data is unavailable; trying archive fallbacks",
                exc_info=True,
                extra={
                    "season": parsed_season,
                    "round": parsed_round,
                    "session": session_code,
                },
            )

    session: Session = fastf1.get_session(parsed_season, parsed_round, session_code)
    session.load(
        laps=True,
        telemetry=False,
        weather=False,
        messages=False,
    )
    result_rows = session.results.to_dict(orient="records")
    try:
        fastf1_laps = session.laps
    except DataNotLoadedError:
        if session_code != "R":
            raise
        fastf1_laps = None

    if fastf1_laps is None or fastf1_laps.empty:
        if session_code != "R":
            return {"drivers": [], "laps": []}
        raw_laps = _get_ergast_race_laps(
            parsed_season,
            parsed_round,
            result_rows,
        )
        if not raw_laps:
            return {"drivers": [], "laps": []}
        logger.warning(
            "FastF1 race timing data is unavailable; using Ergast lap times",
            extra={
                "season": parsed_season,
                "round": parsed_round,
                "lap_count": len(raw_laps),
            },
        )
        compound_colors = {"UNKNOWN": "#969BA5"}
    else:
        raw_laps = fastf1_laps.to_dict(orient="records")
        try:
            compound_colors = fastf1.plotting.get_compound_mapping(session)
        except Exception:  # noqa: BLE001 - compounds are optional metadata.
            # Some older or incomplete timing feeds do not identify the event year.
            compound_colors = COMPOUND_COLORS
    if not raw_laps:
        return {"drivers": [], "laps": []}

    drivers: list[LapDriver] = []
    known_codes: set[str] = set()
    for row in result_rows:
        code = _classification_driver_code(row)
        if not code or code in known_codes:
            continue
        team = format_value(row.get("TeamName"))
        team_id = format_value(row.get("TeamId"))
        full_name = format_value(row.get("FullName")) or code
        drivers.append(
            {
                "code": code,
                "name": full_name,
                "team": team,
                "team_color": get_team_color(
                    [{"constructorId": team_id, "name": team}],
                    row.get("TeamColor"),
                    season=parsed_season,
                    round_number=parsed_round,
                ),
            }
        )
        known_codes.add(code)

    laps: list[LapPoint] = []
    for row in raw_laps:
        code = format_value(row.get("Driver"))
        seconds = _time_seconds(row.get("LapTime"))
        number = _lap_count(row.get("LapNumber"))
        if not code or seconds is None or seconds <= 0 or number is None:
            continue
        if code not in known_codes:
            team = format_value(row.get("Team"))
            drivers.append(
                {
                    "code": code,
                    "name": code,
                    "team": team,
                    "team_color": get_team_color(
                        [{"name": team}],
                        season=parsed_season,
                        round_number=parsed_round,
                    ),
                }
            )
            known_codes.add(code)
        accuracy = row.get("IsAccurate")
        inaccurate = not _is_missing(accuracy) and not bool(accuracy)
        deleted = not _is_missing(row.get("Deleted")) and bool(row.get("Deleted"))
        pit_lap = not _is_missing(row.get("PitInTime")) or not _is_missing(
            row.get("PitOutTime")
        )
        compound = format_value(row.get("Compound")).upper()
        if compound in {"", "NONE"}:
            compound = "UNKNOWN"
        laps.append(
            {
                "driver": code,
                "number": number,
                "seconds": seconds,
                "time": _format_classification_time(row["LapTime"]),
                "compound": compound,
                "compound_color": compound_colors.get(compound, "#969BA5"),
                "outlier": inaccurate or deleted or pit_lap,
            }
        )

    # Use clean quick laps as the pace reference so prolonged rain or other
    # slow periods cannot stretch the chart's default time range.
    _flag_slow_laps(drivers, laps)

    timed_codes = {lap["driver"] for lap in laps}
    return {
        "drivers": [driver for driver in drivers if driver["code"] in timed_codes],
        "laps": laps,
    }


def _is_missing(value: object) -> bool:
    """Report missing pandas and Python scalar values consistently."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except TypeError, ValueError:
        return False


def _classification_driver_code(row: dict[str, Any]) -> str:
    """Return FastF1's short driver code, falling back to the car number."""
    return format_value(row.get("Abbreviation")) or format_value(
        row.get("DriverNumber")
    )


def _get_ergast_race_laps(
    season: int,
    round_number: int,
    result_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return race laps from Ergast when FastF1 timing data did not load.

    Ergast provides race lap times but not tyre compounds or pit-lap flags, so
    the returned records use unknown compounds and let the normal per-driver
    pace check classify slow laps.

    Args:
        season: Championship season containing the event.
        round_number: Event round in that season.
        result_rows: FastF1 classification rows used to map driver IDs and teams.

    Returns:
        Ergast lap records in the field format expected by ``get_session_laps``.
    """
    driver_codes: dict[str, str] = {}
    team_names: dict[str, str] = {}
    for row in result_rows:
        driver_id = format_value(row.get("DriverId"))
        code = _classification_driver_code(row)
        if not driver_id or not code:
            continue
        driver_codes[driver_id] = code
        team_names[code] = format_value(row.get("TeamName"))

    response = ergast.get_lap_times(
        season,
        round_number,
        result_type="pandas",
        limit=100,
    )
    lap_rows: list[dict[str, Any]] = []
    while True:
        for table in response.content:
            for row in table.to_dict(orient="records"):
                driver_id = format_value(row.get("driverId"))
                code = driver_codes.get(driver_id, "")
                lap_number = _lap_count(row.get("number"))
                seconds = _time_seconds(row.get("time"))
                if not code or lap_number is None or seconds is None or seconds <= 0:
                    continue
                lap_rows.append(
                    {
                        "Driver": code,
                        "LapNumber": lap_number,
                        "LapTime": row.get("time"),
                        "Compound": "UNKNOWN",
                        "IsAccurate": True,
                        "Deleted": False,
                        "PitInTime": None,
                        "PitOutTime": None,
                        "Team": team_names.get(code, ""),
                    }
                )
        try:
            response = response.get_next_result_page()
        except ValueError:
            break
    return lap_rows


def _first_present(*values: object) -> object | None:
    """Return the first non-missing scalar from an API result row."""
    return next((value for value in values if not _is_missing(value)), None)


def _position_number(value: object) -> float | None:
    """Parse a positive numeric classification position when one is present."""
    if _is_missing(value):
        return None
    try:
        position = float(value)
    except TypeError, ValueError:
        return None
    return position if isfinite(position) and position > 0 else None


def _format_position(value: object) -> str:
    """Remove floating point formatting from whole-number result positions."""
    position = _position_number(value)
    if position is not None:
        return str(int(position)) if position.is_integer() else str(position)
    if _is_missing(value):
        return ""
    return format_value(value)


def _time_seconds(value: object) -> float | None:
    """Convert a time-like value to seconds for sorting practice laps."""
    if _is_missing(value):
        return None
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        try:
            seconds = float(total_seconds())
            return seconds if isfinite(seconds) else None
        except TypeError, ValueError, OverflowError:
            return None
    return None


def _format_classification_time(value: object) -> str:
    """Format a time duration as minutes and seconds with milliseconds."""
    seconds = _time_seconds(value)
    if seconds is None:
        return "" if _is_missing(value) else format_value(value)

    sign = "-" if seconds < 0 else ""
    whole_seconds = abs(seconds)
    minutes = int(whole_seconds // 60)
    remainder = whole_seconds - (minutes * 60)
    if whole_seconds >= 3600:
        hours = int(whole_seconds // 3600)
        minutes = int((whole_seconds - (hours * 3600)) // 60)
        return f"{sign}{hours}:{minutes:02d}:{whole_seconds % 60:06.3f}"
    return f"{sign}{minutes}:{remainder:06.3f}"


def _format_gap(seconds: float) -> str:
    """Format a nonnegative leader gap to the nearest millisecond."""
    milliseconds = round(seconds * 1000)
    if milliseconds < 0:
        return ""
    minutes, remainder = divmod(milliseconds, 60_000)
    whole_seconds, fractional = divmod(remainder, 1000)
    return (
        f"+{minutes}:{whole_seconds:02d}.{fractional:03d}"
        if minutes
        else f"+{whole_seconds}.{fractional:03d}"
    )


def _lap_timing(
    lap: object, leader_seconds: float | None, is_first: bool
) -> tuple[str, str]:
    """Show a practice lap or its gap from the first driver's fastest lap."""
    lap_seconds = _time_seconds(lap)
    if lap_seconds is None:
        return "LAP TIME", ""
    if not is_first and leader_seconds is not None:
        gap = _format_gap(lap_seconds - leader_seconds)
        if gap:
            return "GAP TO P1", gap
    return "LAP TIME", _format_classification_time(lap)


def _best_qualifying_lap(row: dict[str, Any]) -> object | None:
    """Use the latest qualifying segment in which this driver set a time."""
    return _first_present(row.get("Q3"), row.get("Q2"), row.get("Q1"))


def _qualifying_timing(
    row: dict[str, Any], position: str, leader_q3_seconds: float | None
) -> tuple[str, str]:
    """Compare top-ten Q3 laps and retain actual laps below tenth place."""
    position_number = _position_number(position)
    q3_lap = row.get("Q3")
    if (
        position_number is not None
        and 1 < position_number <= 10
        and leader_q3_seconds is not None
    ):
        q3_seconds = _time_seconds(q3_lap)
        if q3_seconds is not None:
            gap = _format_gap(q3_seconds - leader_q3_seconds)
            if gap:
                return "GAP TO P1", gap

    lap = _best_qualifying_lap(row)
    return "LAP TIME", _format_classification_time(lap)


def _lap_count(value: object) -> int | None:
    """Read a valid whole number of completed race laps."""
    if _is_missing(value):
        return None
    try:
        laps = float(value)
    except TypeError, ValueError:
        return None
    if not isfinite(laps) or laps < 0 or not laps.is_integer():
        return None
    return int(laps)


def _race_outcome(row: dict[str, Any]) -> str:
    """Map a non-finisher's FastF1 status to a short result label."""
    status = format_value(row.get("Status")).strip().lower()
    classified = format_value(row.get("ClassifiedPosition")).strip().upper()
    if "did not start" in status or "not started" in status or status == "dns":
        return "DNS"
    if classified == "D" or "disqualif" in status:
        return "DSQ"
    if classified == "W" or "withdraw" in status:
        return "WD"
    if classified == "E" or "excluded" in status:
        return "EXC"
    if classified == "F" or "failed to qualify" in status:
        return "DNQ"
    if status in {"finished", "lapped"} or re.fullmatch(r"\+\s*\d+\s*laps?", status):
        return ""
    if classified == "R" or status:
        return "DNF"
    if classified == "N":
        return "NC"
    return ""


def _race_timing(
    row: dict[str, Any],
    is_first: bool,
    leader_seconds: float | None,
    leader_laps: int | None,
) -> tuple[str, str]:
    """Show the winner's total time, elapsed gaps, lap gaps, or outcomes."""
    outcome = _race_outcome(row)
    if outcome:
        return "RESULT", outcome

    row_time_seconds = _time_seconds(row.get("Time"))
    if is_first:
        return "TOTAL TIME", _format_classification_time(row.get("Time"))

    laps = _lap_count(row.get("Laps"))
    if leader_laps is not None and laps is not None and laps < leader_laps:
        difference = leader_laps - laps
        return "GAP TO P1", f"+{difference} {'Lap' if difference == 1 else 'Laps'}"

    # Older feeds may only publish the lapped status and omit completed laps.
    status = format_value(row.get("Status")).strip()
    lap_status = re.fullmatch(r"\+\s*(\d+)\s*laps?", status, re.IGNORECASE)
    if lap_status:
        difference = int(lap_status.group(1))
        return "GAP TO P1", f"+{difference} {'Lap' if difference == 1 else 'Laps'}"

    if status.lower() == "lapped":
        return "GAP TO P1", ""

    if row_time_seconds is not None and leader_seconds is not None:
        # Live timing supplies the winner's total time but already gives the
        # remaining finishers' gaps; older result tables can hold totals for
        # everyone. The smaller value is therefore already a leader gap.
        elapsed_gap = (
            row_time_seconds
            if row_time_seconds < leader_seconds
            else row_time_seconds - leader_seconds
        )
        gap = _format_gap(elapsed_gap)
        if gap:
            return "GAP TO P1", gap
    return "GAP TO P1", ""


def get_race_weekend(
    today: date | None = None,
) -> RaceWeekend | None:
    """Return the current race weekend, or the next scheduled one.

    The weekend begins on the date of its first scheduled session and ends on
    race day. When no weekend is underway, use the earliest future event in
    this season or the next published season. Events without session dates use
    race day as their start date.

    Args:
        today: Date to check, defaulting to the server's local date.

    Returns:
        A display-ready event record, or ``None`` when no event is scheduled.
    """
    current_date: date = today or date.today()
    # Sprint qualifying appears under two Ergast field names. Both map to one
    # display label and are deduplicated when sessions are grouped by date.
    session_fields: tuple[tuple[str, str, str], ...] = EVENT_SESSION_FIELDS
    selected: tuple[date, date, dict[str, Any]] | None = None
    selected_season: int = current_date.year
    status = ""
    for season in (current_date.year, current_date.year + 1):
        response: list[dict[str, Any]] = _race_schedule(season)
        current_events: list[tuple[date, date, dict[str, Any]]] = []
        future_events: list[tuple[date, date, dict[str, Any]]] = []
        for race in response:
            race_date = parse_race_date(race.get("date"))
            if race_date is None or race_date < current_date:
                continue

            if not format_value(race.get("round")) or not format_value(
                race.get("raceName")
            ):
                continue

            session_dates: list[date] = []
            for field, _, _ in session_fields:
                session: object = race.get(field)
                session_date_value: object = (
                    session.get("date") if isinstance(session, dict) else session
                )
                session_date = parse_race_date(session_date_value)
                if session_date is not None and session_date <= race_date:
                    session_dates.append(session_date)
            start_date = min(session_dates, default=race_date)
            event = (start_date, race_date, race)
            if start_date <= current_date <= race_date:
                current_events.append(event)
            elif start_date > current_date:
                future_events.append(event)

        if current_events:
            selected = min(current_events, key=lambda event: event[1])
            selected_season = season
            status = "current"
            break
        if future_events:
            selected = min(future_events, key=lambda event: event[0])
            selected_season = season
            status = "upcoming"
            break

    if selected is None:
        return None

    start_date, race_date, race = selected
    round_number = format_value(race.get("round"))
    race_name = format_value(race.get("raceName"))
    circuit: dict[str, Any] = race.get("Circuit") or {}
    location: dict[str, Any] = circuit.get("Location") or {}
    country = format_value(location.get("country"))
    # Build the display schedule only for the selected weekend. Keep each
    # session's start time with its name so the card can align them.
    sessions_by_date: dict[date, dict[str, ScheduledSession]] = {}
    sprint_qualifying_added = False
    for field, session_code, session_name in session_fields:
        session: object = race.get(field)
        session_date_value: object = (
            session.get("date") if isinstance(session, dict) else session
        )
        session_date: date | None = parse_race_date(session_date_value)
        if session_date is None or not start_date <= session_date <= race_date:
            continue

        # The event selector uses the first published Sprint Qualifying field.
        # Keep the schedule's link code in step with that selector.
        if field in ("SprintQualifying", "SprintShootout"):
            if sprint_qualifying_added:
                continue
            sprint_qualifying_added = True

        session_start = parse_session_start(
            session_date, session.get("time") if isinstance(session, dict) else None
        )
        day_sessions = sessions_by_date.setdefault(
            session_start.date() if session_start is not None else session_date, {}
        )
        day_sessions[session_name] = {
            "code": session_code,
            "name": session_name,
            "time": session_start.strftime("%H:%M") if session_start else "TBD",
            "end_time": "",
            "starts_at": session_start.isoformat() if session_start else "",
            "ends_at": "",
            "track_offset_minutes": None,
            "results_available": False,
        }

    # The race's date and time are stored at the top level of the record.
    race_start = parse_session_start(race_date, race.get("time"))
    sessions_by_date.setdefault(
        race_start.date() if race_start is not None else race_date, {}
    )["Race"] = {
        "code": "R",
        "name": "Race",
        "time": race_start.strftime("%H:%M") if race_start else "TBD",
        "end_time": "",
        "starts_at": race_start.isoformat() if race_start else "",
        "ends_at": "",
        "track_offset_minutes": None,
        "results_available": False,
    }
    schedule_days: list[ScheduleDay] = [
        {
            "day": session_date.strftime("%A").upper(),
            "date": f"{session_date.day} {session_date.strftime('%b')}",
            "date_iso": session_date.isoformat(),
            "sessions": sorted(
                day_sessions.values(),
                key=lambda session: (session["time"] == "TBD", session["time"]),
            ),
        }
        for session_date, day_sessions in sorted(sessions_by_date.items())
    ]
    return {
        "season": str(selected_season),
        "status": status,
        "round": round_number,
        "race_name": race_name,
        "circuit_name": format_value(circuit.get("circuitName")),
        "locality": format_value(location.get("locality")),
        "country": country,
        "country_flag": flag_for_circuit_country(country),
        "schedule_days": schedule_days,
        "date_range": (
            f"{start_date.strftime('%d %b')} – {race_date.strftime('%d %b %Y')}"  # noqa: RUF001 - rendered date-range punctuation.
        ),
    }


def parse_race_date(value: object) -> date | None:
    """Normalize a schedule date from FastF1's raw response.

    Args:
        value: Date value from the race schedule response.

    Returns:
        The calendar date when the value is parseable, otherwise ``None``.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            # Ergast may provide a full timestamp; only the ISO date matters.
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def format_session_time(value: object) -> str:
    """Format a published Ergast start time as HH:MM UTC, or TBD."""
    if isinstance(value, datetime):
        return (value.astimezone(UTC) if value.tzinfo is not None else value).strftime(
            "%H:%M"
        )
    if isinstance(value, time):
        parsed_time = value
    elif isinstance(value, str):
        try:
            parsed_time = time.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return "TBD"
    else:
        return "TBD"

    if parsed_time.tzinfo is not None:
        parsed_time = (
            datetime.combine(date(2000, 1, 1), parsed_time).astimezone(UTC).time()
        )
    return parsed_time.strftime("%H:%M")


def parse_session_start(session_date: date, value: object) -> datetime | None:
    """Combine a published date and time into a UTC session instant.

    Args:
        session_date: Date attached to the published session time.
        value: A datetime, time, or ISO time string from the schedule.

    Returns:
        The UTC start, or ``None`` when the time is not published.
    """
    if isinstance(value, datetime):
        start = value
    else:
        if isinstance(value, time):
            parsed_time = value
        elif isinstance(value, str):
            try:
                parsed_time = time.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        start = datetime.combine(session_date, parsed_time)

    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return start.astimezone(UTC)


def get_track_time_offsets(season: str, round_number: str) -> dict[str, int]:
    """Read each session's circuit UTC offset from FastF1's local schedule.

    Args:
        season: Championship year.
        round_number: Race round in that championship.

    Returns:
        UTC offsets in minutes, keyed by the displayed session name.
    """
    try:
        event = fastf1.get_event(int(season), int(round_number), backend="fastf1")
    except Exception:  # noqa: BLE001 - event metadata is optional for UI fallbacks.
        return {}

    offsets: dict[str, int] = {}
    for number in range(1, 6):
        name = event.get(f"Session{number}")
        local_start = event.get(f"Session{number}Date")
        if (
            not isinstance(name, str)
            or not isinstance(local_start, datetime)
            or pd.isna(local_start)
        ):
            continue
        offset: timedelta | None = local_start.utcoffset()
        if offset is None:
            continue
        display_name = "Sprint Qualifying" if name == "Sprint Shootout" else name
        offsets[display_name] = int(offset.total_seconds() // 60)
    return offsets


def get_track_session_details(
    season: str, round_number: str
) -> dict[str, TrackSessionDetails]:
    """Read circuit offsets and published session ends from F1's schedule.

    Args:
        season: Championship year.
        round_number: Race round in that championship.

    Returns:
        Session details keyed by displayed name. Missing ends stay empty.
    """
    try:
        response = requests.get(
            f"https://livetiming.formula1.com/static/{int(season)}/Index.json",
            timeout=10,
        )
        response.raise_for_status()
        # The live timing index includes a UTF-8 BOM, which response.json()
        # does not accept with the requests default decoder.
        payload: dict[str, Any] = json.loads(response.content.decode("utf-8-sig"))
        meetings: list[dict[str, Any]] = payload.get("Meetings", [])
        meeting = next(
            event for event in meetings if event.get("Number") == int(round_number)
        )
        details: dict[str, TrackSessionDetails] = {}
        for session in meeting.get("Sessions", []):
            name = session.get("Name")
            if not isinstance(name, str) or not session.get("GmtOffset"):
                continue
            offset = timedelta(
                seconds=pd.Timedelta(session["GmtOffset"]).total_seconds()
            )
            circuit_zone = timezone(offset)
            if name == "Sprint Shootout":
                name = "Sprint Qualifying"
            elif name == "Sprint Qualifying" and int(season) <= 2022:
                name = "Sprint"

            ends_at = ""
            raw_end = session.get("EndDate")
            raw_start = session.get("StartDate")
            if isinstance(raw_end, str) and isinstance(raw_start, str):
                try:
                    end = datetime.fromisoformat(raw_end)
                    start = datetime.fromisoformat(raw_start)
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=circuit_zone)
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=circuit_zone)
                    if end > start:
                        ends_at = end.astimezone(UTC).isoformat()
                except ValueError:
                    pass
            details[name] = {
                "offset_minutes": int(offset.total_seconds() // 60),
                "ends_at": ends_at,
            }
        if details:
            return details
    except requests.RequestException, ValueError, KeyError, StopIteration:
        pass

    # FastF1's public schedule still provides circuit offsets when the raw
    # live timing index or its EndDate fields are unavailable.
    return {
        name: {"offset_minutes": offset, "ends_at": ""}
        for name, offset in get_track_time_offsets(season, round_number).items()
    }


def format_weekend_schedule(
    schedule_days: list[ScheduleDay], viewer_timezone: str, time_mode: str
) -> tuple[list[ScheduleDay], str]:
    """Group session starts by the selected timezone and format their dates.

    Args:
        schedule_days: Sessions carrying their original UTC instants.
        viewer_timezone: Browser IANA timezone for ``my`` mode.
        time_mode: ``my`` for the visitor or ``track`` for circuit time.

    Returns:
        Display days and the matching weekend date range.
    """
    try:
        viewer_zone = ZoneInfo(viewer_timezone)
    except ValueError, ZoneInfoNotFoundError:
        viewer_zone = UTC

    # A missing session-specific offset uses another published offset from
    # the same event. This keeps a partially published schedule usable.
    known_offsets = [
        session["track_offset_minutes"]
        for day in schedule_days
        for session in day["sessions"]
        if session["track_offset_minutes"] is not None
    ]
    fallback_offset = known_offsets[0] if known_offsets else 0
    grouped: dict[date, list[ScheduledSession]] = {}
    last_end_date: date | None = None
    for day in schedule_days:
        original_date = date.fromisoformat(day["date_iso"])
        for session in day["sessions"]:
            start = session["starts_at"]
            display_end_time = ""
            if start:
                utc_start = datetime.fromisoformat(start)
                if time_mode == "track":
                    offset = session["track_offset_minutes"]
                    target_zone = timezone(
                        timedelta(
                            minutes=offset if offset is not None else fallback_offset
                        )
                    )
                else:
                    target_zone = viewer_zone
                local_start = utc_start.astimezone(target_zone)
                display_date = local_start.date()
                display_time = local_start.strftime("%H:%M")
                if session["ends_at"]:
                    utc_end = datetime.fromisoformat(session["ends_at"])
                    if utc_end > utc_start:
                        local_end = utc_end.astimezone(target_zone)
                        day_offset = (local_end.date() - display_date).days
                        display_end_time = local_end.strftime("%H:%M")
                        if day_offset > 0:
                            display_end_time += f" (+{day_offset}d)"
                        if last_end_date is None or local_end.date() > last_end_date:
                            last_end_date = local_end.date()
            else:
                display_date = original_date
                display_time = "TBD"
            grouped.setdefault(display_date, []).append(
                {**session, "time": display_time, "end_time": display_end_time}
            )

    display_days: list[ScheduleDay] = [
        {
            "day": day_date.strftime("%A").upper(),
            "date": f"{day_date.day} {day_date.strftime('%b')}",
            "date_iso": day_date.isoformat(),
            "sessions": sorted(
                sessions, key=lambda session: session["starts_at"] or "9999"
            ),
        }
        for day_date, sessions in sorted(grouped.items())
    ]
    if not display_days:
        return [], ""
    first_day = date.fromisoformat(display_days[0]["date_iso"])
    last_day = date.fromisoformat(display_days[-1]["date_iso"])
    if last_end_date is not None:
        last_day = max(last_day, last_end_date)
    date_range = (
        f"{first_day.strftime('%d %b')} – {last_day.strftime('%d %b %Y')}"  # noqa: RUF001 - rendered date-range punctuation.
        if first_day != last_day
        else first_day.strftime("%d %b %Y")
    )
    return display_days, date_range


# Fallback colors keyed by constructor IDs in the standings response. The
# endpoint does not consistently provide team colors.
TEAM_COLORS: dict[str, str] = {
    "alpine": "#0093cc",
    "aston_martin": "#229971",
    "audi": "#ff2d00",
    "cadillac": "#444444",
    "ferrari": "#e80020",
    "haas": "#b6babd",
    "mclaren": "#ff8000",
    "mercedes": "#27f4d2",
    "rb": "#6692ff",
    "red_bull": "#3671c6",
    "williams": "#64c4ff",
}


def get_driver_standings(
    season: int | str = "current", round: int | str = "last"
) -> list[dict[str, str]]:
    """Fetch driver standings and convert them to Reflex-friendly values.

    Args:
        season: Season year or FastF1's ``"current"`` selector.
        round: Round number or FastF1's ``"last"`` selector.

    Returns:
        Driver standing records with all values normalized to strings.
    """
    # Request the raw response so each returned row can be normalized here.
    response: list[dict[str, Any]] = ergast.get_driver_standings(
        season=season, round=round, result_type="raw"
    )
    if not response:
        return []

    # Extract the raw rows and build the smaller shape consumed by the UI.
    rows: list[dict[str, Any]] = response[0].get("DriverStandings", [])
    standings: list[dict[str, str]] = []
    parsed_season: int | None = parse_integer(season)
    parsed_round: int | None = parse_integer(round)
    for row in rows:
        driver: dict[str, Any] = row.get("Driver", {})
        constructors: list[dict[str, Any]] = row.get("Constructors", [])
        team_names: list[str] = [
            constructor["name"]
            for constructor in constructors
            if constructor.get("name")
        ]
        team_color: str = get_team_color(
            constructors,
            row.get("teamColor") or row.get("TeamColor"),
            season=parsed_season,
            round_number=parsed_round,
        )
        standings.append(
            {
                "position": format_value(row.get("position")),
                "given_name": format_value(driver.get("givenName")),
                "family_name": format_value(driver.get("familyName")),
                "team": ", ".join(team_names),
                "points": format_value(row.get("points")),
                "team_color": team_color,
            }
        )
    return standings


def get_constructor_standings(
    season: int | str = "current", round: int | str = "last"
) -> list[dict[str, str]]:
    """Fetch constructor standings and normalize them for the UI.

    Args:
        season: Season year or FastF1's ``"current"`` selector.
        round: Round number or FastF1's ``"last"`` selector.

    Returns:
        Constructor standing records with all values normalized to strings.
    """
    # Request raw constructor rows and handle an empty response consistently.
    response: list[dict[str, Any]] = ergast.get_constructor_standings(
        season=season, round=round, result_type="raw"
    )
    if not response:
        return []

    # Flatten each response row and attach the matching team color.
    rows: list[dict[str, Any]] = response[0].get("ConstructorStandings", [])
    standings: list[dict[str, str]] = []
    parsed_season: int | None = parse_integer(season)
    parsed_round: int | None = parse_integer(round)
    for row in rows:
        constructor: dict[str, Any] = row.get("Constructor") or {}
        standings.append(
            {
                "position": format_value(row.get("position")),
                "constructor": format_value(constructor.get("name")),
                "points": format_value(row.get("points")),
                "team_color": get_team_color(
                    [constructor],
                    season=parsed_season,
                    round_number=parsed_round,
                ),
            }
        )
    return standings


def get_team_color(
    constructors: list[dict[str, Any]],
    api_color: object = None,
    season: int | None = None,
    round_number: int | None = None,
) -> str:
    """Choose an API-provided, session-derived, or fallback team color.

    Args:
        constructors: Constructor records that may include a color or ID.
        api_color: Optional color supplied alongside the standings row.
        season: Season for looking up the matching FastF1 race session.
        round_number: Race round for looking up the matching session.

    Returns:
        A CSS hex color string.
    """
    # Prefer colors supplied by the API, checking both known field spellings.
    api_colors: list[object] = [api_color]
    for constructor in constructors:
        api_colors.extend(
            [
                constructor.get("teamColor"),
                constructor.get("TeamColor"),
                constructor.get("color"),
            ]
        )
    for color in api_colors:
        if _is_missing(color):
            continue
        formatted_color: str = format_value(color)
        hex_value: str = formatted_color.removeprefix("#")
        if re.fullmatch(r"[0-9A-Fa-f]{6}", hex_value):
            return f"#{hex_value}"

    # Use the season and round's official F1 timing feed when Ergast has no
    # team color. FastF1's plotting helper reads the session's driver/team data.
    if season is not None and round_number is not None:
        for constructor in constructors:
            for team_name in (
                constructor.get("name"),
                constructor.get("constructorId"),
            ):
                if _is_missing(team_name) or not format_value(team_name):
                    continue
                dynamic_color: str = get_session_team_color(
                    format_value(team_name), season, round_number
                )
                if dynamic_color:
                    return dynamic_color

    # Keep a local fallback for seasons without F1 timing data and API outages.
    for constructor in constructors:
        constructor_id: str = format_value(constructor.get("constructorId")).lower()
        if constructor_id in TEAM_COLORS:
            return TEAM_COLORS[constructor_id]

    return "#808080"


@lru_cache(maxsize=32)
def get_f1_session(season: int, round_number: int) -> Session | None:
    """Return the cached FastF1 race session for dynamic team colors.

    Timing data is available from 2018 onwards. Older seasons and unavailable
    sessions use the local palette fallback instead.

    Args:
        season: Championship season to look up.
        round_number: Race round in that season.

    Returns:
        The race session, or ``None`` if timing data cannot be used.
    """
    if season < 2018:
        return None
    try:
        return fastf1.get_session(
            season,
            round_number,
            "R",
            backend="f1timing",
        )
    except Exception:  # noqa: BLE001 - missing timing sessions use local colors.
        # Color lookup must not make standings unavailable.
        return None


@lru_cache(maxsize=128)
def get_session_team_color(
    team_name: str,
    season: int,
    round_number: int,
) -> str:
    """Read a team's official color from the matching race's timing feed.

    Args:
        team_name: Constructor name or ID to match in the session.
        season: Championship season to look up.
        round_number: Race round in that season.

    Returns:
        A CSS hex color, or an empty string when the lookup fails.
    """
    session: Session | None = get_f1_session(season, round_number)
    if session is None:
        return ""
    try:
        color: str = fastf1.plotting.get_team_color(
            team_name,
            session,
            colormap="official",
        )
    except Exception:  # noqa: BLE001 - unknown team names use the fallback palette.
        # Unknown names and missing timing data fall through to the palette.
        return ""
    return color if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) else ""


def parse_integer(value: object) -> int | None:
    """Parse a season or round only when it contains a numeric value.

    Args:
        value: A season or round selector, including ``"current"`` or ``"last"``.

    Returns:
        The parsed integer, or ``None`` for a nonnumeric selector.
    """
    try:
        return int(value) if value is not None else None
    except TypeError, ValueError:
        return None


def parse_event_coordinates(
    season: object, round_number: object
) -> tuple[int, int] | None:
    """Parse an event route only within the supported calendar bounds.

    Args:
        season: Requested championship year.
        round_number: Requested race round.

    Returns:
        Parsed season and round, or ``None`` when either value is invalid or
        outside the supported range.
    """
    parsed_season: int | None = parse_integer(season)
    parsed_round: int | None = parse_integer(round_number)
    if (
        parsed_season is None
        or parsed_round is None
        or not 1950 <= parsed_season <= date.today().year + 1
        or not 1 <= parsed_round <= 30
    ):
        return None
    return parsed_season, parsed_round


def format_value(value: object) -> str:
    """Convert an API value to a display string without a trailing decimal.

    Args:
        value: Value returned by the standings API.

    Returns:
        An empty string for missing data, otherwise a normalized string.
    """
    # Keep absent values empty and remove the decimal from whole-number floats.
    if _is_missing(value):
        return ""
    return str(value).removesuffix(".0")
