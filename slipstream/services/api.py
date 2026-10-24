"""Fetch and normalize Formula 1 schedules and championship standings."""

import logging
import re
import unicodedata
from datetime import UTC, date, datetime, time, timedelta, timezone
from math import ceil, isfinite
from statistics import median
from typing import Any, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .cache import TTLCache
from .catalog import COMPOUND_COLORS, EVENT_SESSION_FIELDS, SUPPORTED_SESSION_CODES
from .flags import flag_for_circuit_country
from .jolpica import get_jolpica_rows
from .openf1 import (
    OPENF1_FIRST_HISTORICAL_SEASON,
    OpenF1Driver,
    OpenF1Meeting,
    OpenF1MeetingSession,
    OpenF1SessionResult,
    OpenF1SessionData,
    get_openf1_event_sessions,
    get_openf1_meeting_sessions,
    get_openf1_meetings,
    get_openf1_session_data,
    get_openf1_session_drivers,
    get_openf1_session_key,
    get_openf1_session_results,
)

logger: logging.Logger = logging.getLogger(__name__)
_RACE_SCHEDULE_CACHE: TTLCache = TTLCache(maxsize=8)
_OPENF1_SESSION_OPTIONS: dict[str, tuple[str, str]] = {
    "Practice 1": ("FP1", "Practice 1"),
    "Practice 2": ("FP2", "Practice 2"),
    "Practice 3": ("FP3", "Practice 3"),
    "Sprint Qualifying": ("SQ", "Sprint Qualifying"),
    "Sprint Shootout": ("SS", "Sprint Qualifying"),
    "Sprint": ("S", "Sprint"),
    "Qualifying": ("Q", "Qualifying"),
    "Race": ("R", "Race"),
}


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
        lambda: get_jolpica_rows(
            f"{season}.json", "RaceTable", "Races"
        ),
    )


def get_available_seasons(start_year: int = 1950) -> list[str]:
    """Return the available championship seasons, newest first.

    Args:
        start_year: Earliest season to include.

    Returns:
        Season years formatted as strings for championship requests.
    """
    # Keep the raw response typed at the provider boundary before extracting
    # the smaller string-only shape used by page state.
    response: list[dict[str, Any]] = get_jolpica_rows(
        "seasons.json", "SeasonTable", "Seasons"
    )
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

    if parsed_season >= OPENF1_FIRST_HISTORICAL_SEASON:
        try:
            openf1_sessions = get_openf1_event_sessions(
                parsed_season, parsed_round
            )
        except Exception:
            logger.warning(
                "OpenF1 session schedule is unavailable for the archive event",
                exc_info=True,
                extra={"season": parsed_season, "round": parsed_round},
            )
        else:
            scheduled_codes = {item[4]["code"] for item in scheduled}
            for index, session in enumerate(openf1_sessions):
                option = _OPENF1_SESSION_OPTIONS.get(session["name"])
                if option is None or session["is_cancelled"]:
                    continue
                code, _ = option
                if code in scheduled_codes or (
                    code in {"SQ", "SS"} and sprint_qualifying_added
                ):
                    continue
                starts_at = session["starts_at"]
                session_date = starts_at.date() if starts_at is not None else race_date
                if session_date > race_date:
                    continue
                session_time = starts_at.strftime("%H:%M") if starts_at else "TBD"
                scheduled.append(
                    (
                        session_date,
                        session_time == "TBD",
                        session_time,
                        len(EVENT_SESSION_FIELDS) + index,
                        {"code": code, "name": option[1]},
                    )
                )
                scheduled_codes.add(code)
                if code in {"SQ", "SS"}:
                    sprint_qualifying_added = True
                session_dates.append(session_date)

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
            f"{start_date.strftime('%d %b')} – {race_date.strftime('%d %b %Y')}"
        ),
        "sessions": session_options,
    }


def _normalize_jolpica_result(row: dict[str, Any]) -> dict[str, Any]:
    """Convert one compatible API result row to the shared classification shape."""
    driver: dict[str, Any] = row.get("Driver") or {}
    constructor: dict[str, Any] = row.get("Constructor") or {}
    race_time: object = row.get("Time")
    if isinstance(race_time, dict):
        race_time = race_time.get("time")
    return {
        "Position": row.get("position"),
        "ClassifiedPosition": row.get("positionText"),
        "Abbreviation": driver.get("code"),
        "DriverNumber": driver.get("permanentNumber"),
        "DriverId": driver.get("driverId"),
        "FirstName": driver.get("givenName"),
        "LastName": driver.get("familyName"),
        "FullName": " ".join(
            value
            for value in (driver.get("givenName"), driver.get("familyName"))
            if value
        ),
        "TeamName": constructor.get("name"),
        "TeamId": constructor.get("constructorId"),
        "TeamColor": constructor.get("color"),
        "Time": race_time,
        "Laps": row.get("laps"),
        "Status": row.get("status"),
        "Q1": row.get("Q1"),
        "Q2": row.get("Q2"),
        "Q3": row.get("Q3"),
    }


def _jolpica_session_rows(
    season: int,
    round_number: int,
    session_code: str,
) -> list[dict[str, Any]]:
    """Return supported legacy classifications from Jolpica's API."""
    if session_code == "R":
        endpoint, result_key = "results", "Results"
    elif session_code == "Q":
        endpoint, result_key = "qualifying", "QualifyingResults"
    elif session_code in {"S", "SQ"} and season >= 2021:
        # The older sprint format used a race-like Saturday classification.
        if session_code == "SQ" and season >= OPENF1_FIRST_HISTORICAL_SEASON:
            return []
        endpoint, result_key = "sprint", "SprintResults"
    else:
        return []

    rows = get_jolpica_rows(
        f"{season}/{round_number}/{endpoint}.json",
        "RaceTable",
        "Races",
    )
    if not rows:
        return []
    result_rows = rows[0].get(result_key)
    if not isinstance(result_rows, list):
        return []
    return [
        _normalize_jolpica_result(row)
        for row in result_rows
        if isinstance(row, dict)
    ]


def _openf1_classification_rows(
    season: int,
    round_number: int,
    session_code: str,
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    """Join published OpenF1 results with driver and team metadata."""
    session_key = get_openf1_session_key(season, round_number, session_code)
    drivers: dict[int, OpenF1Driver] = {
        driver["driver_number"]: driver
        for driver in get_openf1_session_drivers(session_key)
    }
    results: tuple[OpenF1SessionResult, ...] = get_openf1_session_results(
        season, round_number, session_code
    )
    rows: list[dict[str, Any]] = []
    fastest_laps: dict[str, object] = {}
    practice_session = session_code in {"FP1", "FP2", "FP3"}
    for result in results:
        driver = drivers.get(result["driver_number"])
        if driver is None:
            continue
        duration = result["duration"]
        duration_parts = duration if isinstance(duration, list) else [duration]
        gap = result["gap_to_leader"]
        gap_parts = gap if isinstance(gap, list) else [gap]
        best_lap = duration_parts[0] if duration_parts else None
        if practice_session:
            fastest_laps[driver["code"]] = best_lap

        status = (
            "Did not start"
            if result["dns"]
            else "Disqualified"
            if result["dsq"]
            else "Retired"
            if result["dnf"]
            else "Finished"
        )
        row_time = best_lap
        if session_code in {"Q", "SQ", "SS"}:
            row_time = gap_parts[0] if gap_parts else None
        elif not practice_session and result["position"] != 1:
            row_time = gap_parts[0] if gap_parts else best_lap
            if isinstance(row_time, str):
                status = row_time

        rows.append(
            {
                "Position": result["position"],
                "ClassifiedPosition": (
                    "D" if result["dsq"] else "N" if result["dns"] else result["position"]
                ),
                "Abbreviation": driver["code"],
                "DriverNumber": str(driver["driver_number"]),
                "FirstName": driver["first_name"],
                "LastName": driver["last_name"],
                "FullName": driver["full_name"],
                "TeamName": driver["team_name"],
                "TeamId": driver["team_name"],
                "TeamColor": driver["team_color"],
                "Time": row_time,
                "Laps": result["number_of_laps"],
                "Status": status,
                "Q1": duration_parts[0] if len(duration_parts) > 0 else None,
                "Q2": duration_parts[1] if len(duration_parts) > 1 else None,
                "Q3": duration_parts[2] if len(duration_parts) > 2 else None,
            }
        )
    return rows, fastest_laps


def _classification_rows(
    season: int,
    round_number: int,
    session_code: str,
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    """Prefer OpenF1's session feed, then use published archive results."""
    if season >= OPENF1_FIRST_HISTORICAL_SEASON:
        try:
            rows, fastest_laps = _openf1_classification_rows(
                season, round_number, session_code
            )
            if rows:
                return rows, fastest_laps
        except Exception:
            logger.warning(
                "OpenF1 classification is unavailable; checking the race archive",
                exc_info=True,
                extra={"season": season, "round": round_number, "session": session_code},
            )
    return _jolpica_session_rows(season, round_number, session_code), {}


def get_session_classification(
    season: int | str,
    round_number: int | str,
    session_code: str,
) -> list[DriverClassification]:
    """Load and normalize the selected session's driver classification.

    Practice sessions use each driver's fastest published lap. Other sessions
    retain the provider's classified position order and show comparable timing.

    Args:
        season: Championship season containing the event.
        round_number: Event round in that season.
        session_code: Session identifier from the published weekend schedule.

    Returns:
        Driver classification rows ordered for display, or an empty list when
        the available data source has not published that session.

    Raises:
        ValueError: If a route value or session identifier is invalid.
    """
    coordinates: tuple[int, int] | None = parse_event_coordinates(season, round_number)
    if coordinates is None:
        raise ValueError("A supported numeric season and round are required.")
    parsed_season, parsed_round = coordinates
    if session_code not in SUPPORTED_SESSION_CODES:
        raise ValueError("The requested session is not supported.")

    practice_session: bool = session_code in {"FP1", "FP2", "FP3"}
    result_rows, fastest_laps = _classification_rows(
        parsed_season, parsed_round, session_code
    )
    if not result_rows:
        return []

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
        """Keep published numeric result order, with unclassified rows last."""
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
        team_color = get_team_color(
            [{"name": team}],
            row.get("TeamColor"),
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
    """Report whether either available data source published session rows."""
    coordinates: tuple[int, int] | None = parse_event_coordinates(season, round_number)
    if coordinates is None or session_code not in SUPPORTED_SESSION_CODES:
        return False
    parsed_season, parsed_round = coordinates

    if parsed_season >= OPENF1_FIRST_HISTORICAL_SEASON:
        try:
            if get_openf1_session_results(parsed_season, parsed_round, session_code):
                return True
        except Exception:
            logger.warning(
                "OpenF1 result availability is unavailable; checking the race archive",
                exc_info=True,
                extra={"season": parsed_season, "round": parsed_round, "session": session_code},
            )
    try:
        return bool(_jolpica_session_rows(parsed_season, parsed_round, session_code))
    except Exception:
        logger.warning(
            "Could not check published archive results",
            exc_info=True,
            extra={"season": parsed_season, "round": parsed_round, "session": session_code},
        )
        return False


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

    OpenF1 supplies historical lap and tyre data from 2023 onward. The race
    archive provides older race lap times without compounds or pit-lap flags.
    Outliers include pit-out laps and laps slower than 107% of each driver's
    quickest clean-lap pace.

    Args:
        season: Championship season containing the event.
        round_number: Event round in that season.
        session_code: Session identifier from the published weekend schedule.

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
            logger.warning(
                "OpenF1 lap data is unavailable; checking the race archive",
                exc_info=True,
                extra={
                    "season": parsed_season,
                    "round": parsed_round,
                    "session": session_code,
                },
            )

    if session_code != "R":
        return {"drivers": [], "laps": []}

    result_rows = _jolpica_session_rows(parsed_season, parsed_round, "R")
    raw_laps = _get_jolpica_race_laps(parsed_season, parsed_round, result_rows)
    if not raw_laps:
        return {"drivers": [], "laps": []}

    drivers: list[LapDriver] = []
    known_codes: set[str] = set()
    for row in result_rows:
        code = _classification_driver_code(row)
        if not code or code in known_codes:
            continue
        team = format_value(row.get("TeamName"))
        full_name = format_value(row.get("FullName")) or code
        drivers.append(
            {
                "code": code,
                "name": full_name,
                "team": team,
                "team_color": get_team_color(
                    [{"name": team}],
                    row.get("TeamColor"),
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
                "compound_color": COMPOUND_COLORS.get(
                    compound, COMPOUND_COLORS["UNKNOWN"]
                ),
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
    """Report missing Python scalar values consistently."""
    if value is None:
        return True
    try:
        comparison = value != value
        return comparison if isinstance(comparison, bool) else False
    except TypeError, ValueError:
        return False


def _classification_driver_code(row: dict[str, Any]) -> str:
    """Return a driver's short code, falling back to the car number."""
    return format_value(row.get("Abbreviation")) or format_value(
        row.get("DriverNumber")
    )


def _get_jolpica_race_laps(
    season: int,
    round_number: int,
    result_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return archived race lap timings with unknown tyre compounds.

    Jolpica's compatible race lap endpoint provides lap times, but not tyre
    compounds or pit-lap flags. The normal pace check still classifies slow laps.

    Args:
        season: Championship season containing the event.
        round_number: Event round in that season.
        result_rows: Race classification rows used to map driver IDs and teams.

    Returns:
        Lap records in the field format expected by ``get_session_laps``.
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

    response = get_jolpica_rows(
        f"{season}/{round_number}/laps.json",
        "RaceTable",
        "Laps",
    )
    lap_rows: list[dict[str, Any]] = []
    for lap in response:
        lap_number = _lap_count(lap.get("number"))
        timings = lap.get("Timings")
        if lap_number is None or not isinstance(timings, list):
            continue
        for row in timings:
            if not isinstance(row, dict):
                continue
            driver_id = format_value(row.get("driverId"))
            code = driver_codes.get(driver_id, "")
            lap_time = row.get("time")
            seconds = _time_seconds(lap_time)
            if not code or seconds is None or seconds <= 0:
                continue
            lap_rows.append(
                {
                    "Driver": code,
                    "LapNumber": lap_number,
                    "LapTime": lap_time,
                    "Compound": "UNKNOWN",
                    "IsAccurate": True,
                    "Deleted": False,
                    "PitInTime": None,
                    "PitOutTime": None,
                    "Team": team_names.get(code, ""),
                }
            )
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
    """Convert numeric or clock-formatted durations to seconds."""
    if _is_missing(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        return seconds if isfinite(seconds) else None
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        try:
            seconds = float(total_seconds())
            return seconds if isfinite(seconds) else None
        except TypeError, ValueError, OverflowError:
            return None
    if isinstance(value, str):
        text_value = value.strip()
        try:
            numeric_seconds = float(text_value)
            return numeric_seconds if isfinite(numeric_seconds) else None
        except ValueError:
            pass
        parts = text_value.split(":")
        if len(parts) not in {2, 3}:
            return None
        try:
            seconds = float(parts[-1])
            minutes = int(parts[-2])
            hours = int(parts[-3]) if len(parts) == 3 else 0
        except ValueError:
            return None
        if min(hours, minutes, seconds) < 0 or minutes >= 60 or seconds >= 60:
            return None
        duration = hours * 3600 + minutes * 60 + seconds
        return duration if isfinite(duration) else None
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
    """Map a non-finisher's published status to a short result label."""
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
    """Return the current or next OpenF1 Grand Prix meeting.

    OpenF1 supplies the event identity and scheduled session windows. The
    existing season calendar supplies the championship round and canonical
    circuit name used by result links and archive pages.

    Args:
        today: Date to check, defaulting to the server's local date.

    Returns:
        A display-ready event record, or ``None`` when no event is scheduled.
    """
    current_date: date = today or date.today()
    selected: tuple[int, str, OpenF1Meeting, date, date] | None = None

    for season in (current_date.year, current_date.year + 1):
        meetings: tuple[OpenF1Meeting, ...] = get_openf1_meetings(season)
        current_events: list[tuple[OpenF1Meeting, date, date]] = []
        future_events: list[tuple[OpenF1Meeting, date, date]] = []
        for meeting in meetings:
            if meeting["is_cancelled"]:
                continue
            track_zone = timezone(
                timedelta(minutes=meeting["track_offset_minutes"] or 0)
            )
            start_date = meeting["starts_at"].astimezone(track_zone).date()
            meeting_end = meeting["ends_at"] or meeting["starts_at"]
            end_date = meeting_end.astimezone(track_zone).date()
            if start_date <= current_date <= end_date:
                current_events.append((meeting, start_date, end_date))
            elif start_date > current_date:
                future_events.append((meeting, start_date, end_date))

        if current_events:
            meeting, start_date, end_date = min(
                current_events, key=lambda event: event[2]
            )
            selected = (season, "current", meeting, start_date, end_date)
            break
        if future_events:
            meeting, start_date, end_date = min(
                future_events, key=lambda event: event[1]
            )
            selected = (season, "upcoming", meeting, start_date, end_date)
            break

    if selected is None:
        return None

    selected_season, status, meeting, start_date, end_date = selected
    legacy_races: list[dict[str, Any]] = _race_schedule(selected_season)
    race = _match_openf1_meeting_to_race(meeting, legacy_races)
    if race is None:
        logger.warning(
            "Could not map OpenF1 meeting to its championship round",
            extra={"season": selected_season, "meeting": meeting["name"]},
        )
        return None

    sessions_by_date: dict[date, dict[str, ScheduledSession]] = {}
    added_names: set[str] = set()
    openf1_sessions: tuple[OpenF1MeetingSession, ...] = (
        get_openf1_meeting_sessions(meeting["meeting_key"])
    )
    for session in openf1_sessions:
        if session["is_cancelled"] or session["name"] not in _OPENF1_SESSION_OPTIONS:
            continue
        session_start = session["starts_at"]
        if session_start is None:
            continue
        session_code, display_name = _OPENF1_SESSION_OPTIONS[session["name"]]
        if display_name in added_names:
            continue
        track_offset = (
            session["track_offset_minutes"]
            if session["track_offset_minutes"] is not None
            else meeting["track_offset_minutes"]
        )
        track_zone = timezone(timedelta(minutes=track_offset or 0))
        session_date = session_start.astimezone(track_zone).date()
        if not start_date <= session_date <= end_date:
            continue

        start_utc = session_start.astimezone(UTC)
        session_end = session["ends_at"]
        # Race finishes vary in practice; keep its row start-only as requested.
        end_utc = (
            session_end.astimezone(UTC)
            if session_end is not None and session_code != "R"
            else None
        )
        sessions_by_date.setdefault(session_date, {})[display_name] = {
            "code": session_code,
            "name": display_name,
            "time": start_utc.strftime("%H:%M"),
            "end_time": "",
            "starts_at": start_utc.isoformat(),
            "ends_at": end_utc.isoformat() if end_utc is not None else "",
            "track_offset_minutes": track_offset,
            "results_available": False,
        }
        added_names.add(display_name)

    schedule_days: list[ScheduleDay] = [
        {
            "day": session_date.strftime("%A").upper(),
            "date": f"{session_date.day} {session_date.strftime('%b')}",
            "date_iso": session_date.isoformat(),
            "sessions": sorted(
                day_sessions.values(), key=lambda session: session["starts_at"]
            ),
        }
        for session_date, day_sessions in sorted(sessions_by_date.items())
    ]
    circuit: dict[str, Any] = race.get("Circuit") or {}
    location: dict[str, Any] = circuit.get("Location") or {}
    country = format_value(location.get("country")) or meeting["country_name"]
    return {
        "season": str(selected_season),
        "status": status,
        "round": format_value(race.get("round")),
        "race_name": meeting["name"],
        "circuit_name": format_value(circuit.get("circuitName"))
        or meeting["circuit_short_name"],
        "locality": meeting["location"] or format_value(location.get("locality")),
        "country": country,
        "country_flag": flag_for_circuit_country(country),
        "schedule_days": schedule_days,
        "date_range": (
        f"{start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')}"
        ),
    }


def _normalize_event_name(value: str) -> str:
    """Return an accent- and punctuation-insensitive Grand Prix name."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.decode().lower()).strip()


def _match_openf1_meeting_to_race(
    meeting: OpenF1Meeting, races: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Find the legacy round and canonical circuit name for an OpenF1 meeting."""
    meeting_name = _normalize_event_name(meeting["name"])
    valid_races = [
        race
        for race in races
        if format_value(race.get("round"))
        and format_value(race.get("raceName"))
    ]
    exact_match = next(
        (
            race
            for race in valid_races
            if _normalize_event_name(format_value(race.get("raceName")))
            == meeting_name
        ),
        None,
    )
    if exact_match is not None:
        return exact_match

    target_timestamp = meeting["ends_at"] or meeting["starts_at"]
    target_zone = timezone(
        timedelta(minutes=meeting["track_offset_minutes"] or 0)
    )
    target_date = target_timestamp.astimezone(target_zone).date()
    dated_races: list[tuple[int, dict[str, Any]]] = []
    for race in valid_races:
        race_date = parse_race_date(race.get("date"))
        if race_date is not None:
            dated_races.append((abs((race_date - target_date).days), race))
    if not dated_races:
        return None
    distance, nearest_race = min(dated_races, key=lambda item: item[0])
    return nearest_race if distance <= 3 else None


def parse_race_date(value: object) -> date | None:
    """Normalize a race date from Jolpica's compatible API response.

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
            # The API may provide a full timestamp; only the ISO date matters.
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def format_session_time(value: object) -> str:
    """Format a published session start time as HH:MM UTC, or TBD."""
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
        f"{first_day.strftime('%d %b')} – {last_day.strftime('%d %b %Y')}"
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
        season: Season year or Jolpica's ``"current"`` selector.
        round: Round number or Jolpica's ``"last"`` selector.

    Returns:
        Driver standing records with all values normalized to strings.
    """
    response = get_jolpica_rows(
        f"{season}/{round}/driverStandings.json",
        "StandingsTable",
        "StandingsLists",
    )
    if not response:
        return []

    rows = response[0].get("DriverStandings", [])
    standings: list[dict[str, str]] = []
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
        season: Season year or Jolpica's ``"current"`` selector.
        round: Round number or Jolpica's ``"last"`` selector.

    Returns:
        Constructor standing records with all values normalized to strings.
    """
    response = get_jolpica_rows(
        f"{season}/{round}/constructorStandings.json",
        "StandingsTable",
        "StandingsLists",
    )
    if not response:
        return []

    rows = response[0].get("ConstructorStandings", [])
    standings: list[dict[str, str]] = []
    for row in rows:
        constructor: dict[str, Any] = row.get("Constructor") or {}
        standings.append(
            {
                "position": format_value(row.get("position")),
                "constructor": format_value(constructor.get("name")),
                "points": format_value(row.get("points")),
                "team_color": get_team_color(
                    [constructor],
                ),
            }
        )
    return standings


def get_team_color(
    constructors: list[dict[str, Any]],
    api_color: object = None,
) -> str:
    """Choose an API-provided or fallback team color.

    Args:
        constructors: Constructor records that may include a color or ID.
        api_color: Optional color supplied alongside the standings row.

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

    # Keep a local fallback for seasons without provider colors and API outages.
    for constructor in constructors:
        constructor_id: str = format_value(constructor.get("constructorId")).lower()
        if constructor_id in TEAM_COLORS:
            return TEAM_COLORS[constructor_id]

    return "#808080"


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
