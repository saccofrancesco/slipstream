"""Fetch and normalize Formula 1 schedules and championship standings."""

import re
from datetime import date, datetime, time, timezone
from functools import lru_cache
from math import isfinite
from typing import Any, TypedDict

# FastF1 provides the Ergast client used to retrieve calendars and standings.
import fastf1
import fastf1.plotting
import pandas as pd
from fastf1.core import Session
from fastf1.ergast import Ergast

from .flags import (
    flag_for_circuit_country,
    flag_for_driver_country_code,
    flag_for_nationality,
)

# Avoid reusing cached results when schedule or standings data is requested.
fastf1.Cache.set_disabled()

# Reuse one Ergast client for schedule and standings requests.
ergast: Ergast = Ergast()


class ScheduledSession(TypedDict):
    """One session and its published UTC start time."""

    name: str
    time: str


class ScheduleDay(TypedDict):
    """Sessions grouped under one UTC calendar date."""

    day: str
    date: str
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
    race_date: str
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
    country_code: str
    nationality: str
    country_flag: str
    team: str
    team_color: str
    time: str
    time_label: str


# Keep the calendar's public session names and FastF1 identifiers together.
EVENT_SESSION_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("FirstPractice", "FP1", "Practice 1"),
    ("SecondPractice", "FP2", "Practice 2"),
    ("ThirdPractice", "FP3", "Practice 3"),
    ("SprintQualifying", "SQ", "Sprint Qualifying"),
    ("SprintShootout", "SS", "Sprint Shootout"),
    ("Sprint", "S", "Sprint"),
    ("Qualifying", "Q", "Qualifying"),
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
    response: list[dict[str, Any]] = ergast.get_seasons(
        result_type="raw", limit=1000
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
    response: list[dict[str, Any]] = ergast.get_race_schedule(
        season=int(season), result_type="raw", limit=1000
    )
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


def get_past_events(
    season: int | str, today: date | None = None
) -> list[PastEvent]:
    """Return races before today, newest first, for one season.

    Args:
        season: Calendar season to show in the archive.
        today: Date used to classify past races, defaulting to the server date.

    Returns:
        Compact race records ordered from the latest race to the opener.
    """
    current_date: date = today or date.today()
    response: list[dict[str, Any]] = ergast.get_race_schedule(
        season=int(season), result_type="raw", limit=1000
    )
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
        for _, event in sorted(
            dated_events, key=lambda item: item[0], reverse=True
        )
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
    parsed_season: int | None = parse_integer(season)
    parsed_round: int | None = parse_integer(round_number)
    if (
        parsed_season is None
        or parsed_round is None
        or parsed_season < 1950
        or parsed_round < 1
    ):
        return None

    response: list[dict[str, Any]] = ergast.get_race_schedule(
        season=parsed_season,
        round=parsed_round,
        result_type="raw",
        limit=1,
    )
    race: dict[str, Any] | None = next(
        (
            row
            for row in response
            if parse_integer(row.get("round")) == parsed_round
        ),
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
        option
        for _, _, _, _, option in sorted(
            scheduled, key=lambda item: item[:4]
        )
    ]

    start_date = min(session_dates, default=race_date)
    return {
        "season": str(parsed_season),
        "round": str(parsed_round),
        "race_name": race_name,
        "race_date": race_date.strftime("%d %b %Y"),
        "circuit_name": format_value(circuit.get("circuitName")),
        "locality": format_value(location.get("locality")),
        "country": country,
        "country_flag": flag_for_circuit_country(country),
        "date_range": (
            f"{start_date.strftime('%d %b')} – "
            f"{race_date.strftime('%d %b %Y')}"
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
    parsed_season: int | None = parse_integer(season)
    parsed_round: int | None = parse_integer(round_number)
    allowed_codes: set[str] = {
        "FP1",
        "FP2",
        "FP3",
        "SQ",
        "SS",
        "S",
        "Q",
        "R",
    }
    if parsed_season is None or parsed_round is None:
        raise ValueError("A numeric season and round are required.")
    if session_code not in allowed_codes:
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

    # F1's timing feed can leave CountryCode blank. Jolpica has the matching
    # event driver nationalities; flags fall back to the timing code if needed.
    try:
        driver_nationalities = get_driver_nationalities(
            parsed_season, parsed_round
        )
    except Exception:
        driver_nationalities = {}

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
            row
            for _, row in sorted(
                enumerate(result_rows), key=classified_sort_key
            )
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
        country_code = format_value(row.get("CountryCode"))
        nationality = driver_nationalities.get(
            format_value(row.get("DriverId")), country_code
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
            position = _format_position(
                _first_present(row.get("Position"), row.get("ClassifiedPosition"))
            ) or "—"
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
                "country_code": country_code,
                "nationality": nationality,
                "country_flag": flag_for_nationality(nationality)
                or flag_for_driver_country_code(country_code),
                "team": team,
                "team_color": team_color,
                "time": result_time or "—",
                "time_label": time_label,
            }
        )

    return classification


def _is_missing(value: object) -> bool:
    """Report missing pandas and Python scalar values consistently."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _classification_driver_code(row: dict[str, Any]) -> str:
    """Return FastF1's short driver code, falling back to the car number."""
    return format_value(row.get("Abbreviation")) or format_value(
        row.get("DriverNumber")
    )


@lru_cache(maxsize=128)
def get_driver_nationalities(season: int, round_number: int) -> dict[str, str]:
    """Return driver nationalities for one event, keyed by driver identifier."""
    response: list[dict[str, Any]] = ergast.get_driver_info(
        season=season,
        round=round_number,
        result_type="raw",
        limit=1000,
    )
    return {
        format_value(driver.get("driverId")): format_value(
            driver.get("nationality")
        )
        for driver in response
        if format_value(driver.get("driverId"))
    }


def _first_present(*values: object) -> object | None:
    """Return the first non-missing scalar from an API result row."""
    return next((value for value in values if not _is_missing(value)), None)


def _position_number(value: object) -> float | None:
    """Parse a positive numeric classification position when one is present."""
    if _is_missing(value):
        return None
    try:
        position = float(value)
    except (TypeError, ValueError):
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
        except (TypeError, ValueError, OverflowError):
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
    except (TypeError, ValueError):
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
    if status in {"finished", "lapped"} or re.fullmatch(
        r"\+\s*\d+\s*laps?", status
    ):
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
    session_fields: tuple[tuple[str, str], ...] = tuple(
        (field, "Sprint Qualifying" if field == "SprintShootout" else label)
        for field, _, label in EVENT_SESSION_FIELDS
    )
    selected: tuple[date, date, dict[str, Any]] | None = None
    selected_season: int = current_date.year
    status = ""
    for season in (current_date.year, current_date.year + 1):
        response: list[dict[str, Any]] = ergast.get_race_schedule(
            season=season, result_type="raw", limit=1000
        )
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
            for field, _ in session_fields:
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
    for field, session_name in session_fields:
        session: object = race.get(field)
        session_date_value: object = (
            session.get("date") if isinstance(session, dict) else session
        )
        session_date: date | None = parse_race_date(session_date_value)
        if session_date is None or not start_date <= session_date <= race_date:
            continue

        day_sessions = sessions_by_date.setdefault(session_date, {})
        session_time = format_session_time(
            session.get("time") if isinstance(session, dict) else None
        )
        # Sprint qualifying may be present under both API field names.
        # Prefer the entry with a known time if only one provides it.
        if session_name not in day_sessions or (
            day_sessions[session_name]["time"] == "TBD"
            and session_time != "TBD"
        ):
            day_sessions[session_name] = {
                "name": session_name,
                "time": session_time,
            }

    # The race's date and time are stored at the top level of the record.
    sessions_by_date.setdefault(race_date, {})["Race"] = {
        "name": "Race",
        "time": format_session_time(race.get("time")),
    }
    schedule_days: list[ScheduleDay] = [
        {
            "day": session_date.strftime("%A").upper(),
            "date": f"{session_date.day} {session_date.strftime('%b')}",
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
            f"{start_date.strftime('%d %b')} – "
            f"{race_date.strftime('%d %b %Y')}"
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
        return (
            value.astimezone(timezone.utc) if value.tzinfo is not None else value
        ).strftime("%H:%M")
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
        parsed_time = datetime.combine(date(2000, 1, 1), parsed_time).astimezone(
            timezone.utc
        ).time()
    return parsed_time.strftime("%H:%M")


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
        nationality = format_value(driver.get("nationality"))
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
                "nationality": nationality,
                "country_flag": flag_for_nationality(nationality),
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
        if formatted_color:
            return (
                formatted_color
                if formatted_color.startswith("#")
                else f"#{formatted_color}"
            )

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
        constructor_id: str = (
            format_value(constructor.get("constructorId")).lower()
        )
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
    except Exception:
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
    except Exception:
        # Unknown names and missing timing data fall through to the palette.
        return ""
    return color if color.startswith("#") else ""


def parse_integer(value: object) -> int | None:
    """Parse a season or round only when it contains a numeric value.

    Args:
        value: A season or round selector, including ``"current"`` or ``"last"``.

    Returns:
        The parsed integer, or ``None`` for a nonnumeric selector.
    """
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
