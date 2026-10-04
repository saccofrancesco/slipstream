"""Fetch and normalize Formula 1 schedules and championship standings."""

from datetime import date, datetime, time, timezone
from functools import lru_cache
from typing import Any, TypedDict

# FastF1 provides the Ergast client used to retrieve calendars and standings.
import fastf1
import fastf1.plotting
from fastf1.core import Session
from fastf1.ergast import Ergast

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

    status: str
    round: str
    race_name: str
    circuit_name: str
    locality: str
    country: str
    date_range: str
    schedule_days: list[ScheduleDay]


def get_available_seasons(start_year: int = 1950) -> list[str]:
    """Return the available championship seasons, newest first.

    Args:
        start_year: Earliest season to include.

    Returns:
        Season years formatted as strings for the season selector.
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
    """Return completed races for a season as round selector options.

    Args:
        season: Season year selected by the user.

    Returns:
        Race options with round numbers and display labels, in calendar order.
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
    session_fields: tuple[tuple[str, str], ...] = (
        ("FirstPractice", "Practice 1"),
        ("SecondPractice", "Practice 2"),
        ("ThirdPractice", "Practice 3"),
        ("SprintQualifying", "Sprint Qualifying"),
        ("SprintShootout", "Sprint Qualifying"),
        ("Sprint", "Sprint"),
        ("Qualifying", "Qualifying"),
    )
    selected: tuple[date, date, dict[str, Any]] | None = None
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
            status = "current"
            break
        if future_events:
            selected = min(future_events, key=lambda event: event[0])
            status = "upcoming"
            break

    if selected is None:
        return None

    start_date, race_date, race = selected
    round_number = format_value(race.get("round"))
    race_name = format_value(race.get("raceName"))
    circuit: dict[str, Any] = race.get("Circuit") or {}
    location: dict[str, Any] = circuit.get("Location") or {}
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
        "status": status,
        "round": round_number,
        "race_name": race_name,
        "circuit_name": format_value(circuit.get("circuitName")),
        "locality": format_value(location.get("locality")),
        "country": format_value(location.get("country")),
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
            season=parse_integer(season),
            round_number=parse_integer(round),
        )
        standings.append(
            {
                "position": format_value(row.get("position")),
                "given_name": format_value(driver.get("givenName")),
                "family_name": format_value(driver.get("familyName")),
                "nationality": format_value(driver.get("nationality")),
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
    for row in rows:
        constructor: dict[str, Any] = row.get("Constructor") or {}
        standings.append(
            {
                "position": format_value(row.get("position")),
                "constructor": format_value(constructor.get("name")),
                "points": format_value(row.get("points")),
                "team_color": get_team_color(
                    [constructor],
                    season=parse_integer(season),
                    round_number=parse_integer(round),
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
        if color:
            formatted_color: str = format_value(color)
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
                if not team_name:
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
    if value is None:
        return ""
    return str(value).removesuffix(".0")
