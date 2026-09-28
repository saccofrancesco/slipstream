# Importing libraries
from typing import Any
import fastf1
from fastf1.ergast import Ergast

# Disabling the cache for the queries
fastf1.Cache.set_disabled()

# Creating the Ergast instance for common API fetches
ergast: Ergast = Ergast()

# FastF1's 2026 official team palette, keyed by constructor IDs from the
# standings response. The standings endpoint itself does not include colors.
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


# Retrieve driver standings for a season and round, then flatten FastF1's raw
# response into values that can be stored directly in Reflex state.
def get_driver_standings(
    season: int | str = "current", round: int | str = "last"
) -> list[dict[str, str]]:
    response = ergast.get_driver_standings(
        season=season, round=round, result_type="raw"
    )
    if not response:
        return []
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


# Retrieve team standings for a season and round, then flatten FastF1's raw
# response into values that can be stored directly in Reflex state.
def get_constructor_standings(
    season: int | str = "current", round: int | str = "last"
) -> list[dict[str, str]]:
    response = ergast.get_constructor_standings(
        season=season, round=round, result_type="raw"
    )
    if not response:
        return []
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


# Extract the color based on the driver team name from the above official mapping
def get_team_color(constructors: list[dict[str, Any]], api_color: object = None) -> str:
    api_colors: list[dict[str, Any]] | Any = [api_color]
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
            formatted_color = format_value(color)
            return (
                formatted_color
                if formatted_color.startswith("#")
                else f"#{formatted_color}"
            )
    for constructor in constructors:
        constructor_id = format_value(constructor.get("constructorId")).lower()
        if constructor_id in TEAM_COLORS:
            return TEAM_COLORS[constructor_id]

    return "#808080"


# Format values before storing them in Reflex state.
def format_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).removesuffix(".0")
