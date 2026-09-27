# Importing libraries
import fastf1
from fastf1.ergast import Ergast
from typing import Any

# Disabling the cache for the queries
fastf1.Cache.set_disabled()

# Creating the Ergast instance for common API fetches
ergast: Ergast = Ergast()


# Retrieve driver standings for a season and round, then flatten FastF1's raw
# response into values that can be stored directly in Reflex state.
def get_driver_standings(
    season: int | str = "current", round: int | str = "last"
) -> list[dict[str, str]]:
    response = ergast.get_driver_standings(
        season=season,
        round=round,
        result_type="raw",
    )
    if not response:
        return []
    rows: list[dict[str, Any]] = response[0].get("DriverStandings", [])
    standings: list[dict[str, str]] = []
    for row in rows:
        driver: str = row.get("Driver", {})
        constructors: str = row.get("Constructors", [])
        team_names: list[str] = [
            constructor["name"]
            for constructor in constructors
            if constructor.get("name")
        ]
        standings.append(
            {
                "position": format(row.get("position")),
                "given_name": format(driver.get("givenName")),
                "family_name": format(driver.get("familyName")),
                "nationality": format(driver.get("nationality")),
                "team": ", ".join(team_names),
                "points": format(row.get("points")),
            }
        )

    return standings


# Format the values before creating objects that will be stored in the app's state
def format(value: object) -> str:
    if value is None:
        return ""
    return str(value).removesuffix(".0")
