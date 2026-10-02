"""Expose standings service functions to the application."""

from .api import (
    get_available_seasons,
    get_completed_races,
    get_constructor_standings,
    get_driver_standings,
)

__all__: list[str] = [
    "get_available_seasons",
    "get_completed_races",
    "get_constructor_standings",
    "get_driver_standings",
]
