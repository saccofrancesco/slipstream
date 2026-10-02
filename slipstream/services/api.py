"""Fetch and normalize Formula 1 championship standings."""

# Use Any for the raw response shape supplied by the external client.
from datetime import date, datetime
from typing import Any

# FastF1 provides the Ergast client used to retrieve standings.
import fastf1
from fastf1.ergast import Ergast

# Avoid reusing cached results when standings are requested.
fastf1.Cache.set_disabled()

# Reuse one Ergast client for both driver and constructor requests.
ergast: Ergast = Ergast()


def get_available_seasons(start_year: int = 1950) -> list[str]:
    """Return the available championship seasons, newest first.

    Args:
        start_year: Earliest season to include.

    Returns:
        Season years formatted as strings for the season selector.
    """
    response: Any = ergast.get_seasons(result_type="raw", limit=1000)
    if not response:
        return []

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
    response: Any = ergast.get_race_schedule(
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

        # Do not offer a future race as a standings snapshot.
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
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None

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
    response: Any = ergast.get_driver_standings(
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
    response: Any = ergast.get_constructor_standings(
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
                "team_color": get_team_color([constructor]),
            }
        )
    return standings


def get_team_color(
    constructors: list[dict[str, Any]],
    api_color: object = None,
) -> str:
    """Choose an API-provided team color or its configured fallback.

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
        if color:
            formatted_color: str = format_value(color)
            return (
                formatted_color
                if formatted_color.startswith("#")
                else f"#{formatted_color}"
            )
    # Fall back to the local palette when the API has no usable color.
    for constructor in constructors:
        constructor_id: str = (
            format_value(constructor.get("constructorId")).lower()
        )
        if constructor_id in TEAM_COLORS:
            return TEAM_COLORS[constructor_id]

    return "#808080"


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
