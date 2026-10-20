"""Shared state and page shell for driver and constructor championships."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import ClassVar, Literal

import reflex as rx

from slipstream.services.cached import (
    get_cached_available_seasons,
    get_cached_completed_races,
    get_cached_constructor_standings,
    get_cached_driver_standings,
)

logger: logging.Logger = logging.getLogger(__name__)


class ChampionshipState(rx.State):
    """Hold the latest standings and loading feedback for one championship."""

    championship_kind: ClassVar[Literal["driver", "constructor"]] = "driver"
    minimum_season: ClassVar[int] = 1950

    standings: list[dict[str, str]] = []
    loading: bool = False
    error: str = ""

    @rx.var
    def podium_standings(self) -> list[dict[str, str]]:
        """Return the first three entries for the podium cards."""
        return self.standings[:3]

    @rx.var
    def remaining_standings(self) -> list[dict[str, str]]:
        """Return all standings after the podium entries."""
        return self.standings[3:]

    @rx.var
    def has_remaining_standings(self) -> bool:
        """Report whether standings remain after the podium."""
        return len(self.standings) > 3

    @rx.var
    def has_standings(self) -> bool:
        """Report whether any standings were loaded."""
        return bool(self.standings)

    @rx.event
    async def load_standings(self) -> AsyncGenerator[None]:
        """Load the newest completed race's standings for this page.

        Yields:
            A state update after loading begins so the page can show its spinner.
        """
        kind = self.championship_kind
        self.loading = True
        self.error = ""
        self.standings = []
        yield
        try:
            seasons = await asyncio.to_thread(
                get_cached_available_seasons, self.minimum_season
            )
            if not seasons:
                self.error = "Championship data is not available yet."
                return
            races = await asyncio.to_thread(get_cached_completed_races, seasons[0])
            if not races:
                self.error = "No completed races are available yet."
                return

            standings_loader = (
                get_cached_driver_standings
                if kind == "driver"
                else get_cached_constructor_standings
            )
            self.standings = await asyncio.to_thread(
                standings_loader,
                int(seasons[0]),
                int(races[-1]["round"]),
            )
            if not self.standings:
                self.error = f"No {kind} standings are available for this race."
        except Exception:
            logger.exception("Could not load %s championship data", kind)
            self.standings = []
            self.error = f"Could not load {kind} championship data. Please try again."
        finally:
            self.loading = False
