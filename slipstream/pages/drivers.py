"""Driver championship page and its loading state."""

import asyncio
from collections.abc import AsyncGenerator

# Reflex provides state, event, and component primitives for this page.
import reflex as rx

# Reuse shared presentation components and the driver standings service.
from slipstream.components import container, navbar, page_header
from slipstream.components.championship import (
    championship_filters,
    leaderboard_section,
    loading_panel,
    message_panel,
    podium_section,
)
from slipstream.services import (
    get_available_seasons,
    get_completed_races,
    get_driver_standings,
)


class DriversState(rx.State):
    """Hold driver standings and the season and round used to fetch them.

    Selection events refresh the dependent options and standings; computed
    vars provide the labels and subsets consumed by the page components.
    """

    standings: list[dict[str, str]] = []
    seasons: list[str] = []
    selected_season: str = ""
    races: list[dict[str, str]] = []
    selected_round: str = ""
    loading: bool = False
    error: str = ""

    @rx.var
    def selected_round_label(self) -> str:
        """Return the display label for the selected round."""
        for race in self.races:
            if race["round"] == self.selected_round:
                return race["label"]
        return "Choose a completed race"

    @rx.var
    def season_selector_disabled(self) -> bool:
        """Disable season selection while loading or without season data."""
        return self.loading or not self.seasons

    @rx.var
    def round_selector_disabled(self) -> bool:
        """Disable race selection while loading or without race options."""
        return self.loading or not self.races

    @rx.var
    def podium_standings(self) -> list[dict[str, str]]:
        """Return the first three driver standings for the podium."""
        return self.standings[:3]

    @rx.var
    def remaining_standings(self) -> list[dict[str, str]]:
        """Return driver standings after the first three entries."""
        return self.standings[3:]

    @rx.var
    def has_remaining_standings(self) -> bool:
        """Report whether rows remain after the podium."""
        return len(self.standings) > 3

    @rx.var
    def has_standings(self) -> bool:
        """Report whether any driver standings were loaded."""
        return bool(self.standings)

    @rx.event
    async def load_standings(self) -> AsyncGenerator[None, None]:
        """Load seasons, race options, and the latest driver standings.

        Yields:
            A state update after loading begins so the page can show its spinner.
        """
        # Set the loading state before starting the network request.
        self.loading = True
        self.error = ""
        yield
        try:
            # Run the blocking API client call outside the event loop.
            self.seasons = await asyncio.to_thread(get_available_seasons)
            if not self.seasons:
                self.error = "No championship seasons are available yet."
                return
            self.selected_season = self.seasons[0]
            # The newest completed round is the initial standings snapshot.
            self.races = await asyncio.to_thread(
                get_completed_races, self.selected_season
            )
            if not self.races:
                self.error = (
                    f"No completed races are available for {self.selected_season}."
                )
                return
            self.selected_round = self.races[-1]["round"]
            self.standings = await asyncio.to_thread(
                get_driver_standings,
                int(self.selected_season),
                int(self.selected_round),
            )
            if not self.standings:
                self.error = "No driver standings are available for this race."
        except Exception:
            # Keep the UI usable and show a short message if loading fails.
            self.standings = []
            self.error = "Could not load driver championship data. Please try again."
        finally:
            # Clear the loading indicator on both success and failure.
            self.loading = False

    @rx.event
    async def select_season(self, season: str) -> AsyncGenerator[None, None]:
        """Load the latest completed race standings for a selected season.

        Args:
            season: Season selected in the page filter.

        Yields:
            A state update that clears the previous season's race options.
        """
        # A season change invalidates both the selected round and standings.
        self.selected_season = season
        self.races = []
        self.selected_round = ""
        self.standings = []
        self.loading = True
        self.error = ""
        yield
        try:
            self.races = await asyncio.to_thread(get_completed_races, season)
            if not self.races:
                self.error = f"No completed races are available for {season}."
                return
            self.selected_round = self.races[-1]["round"]
            self.standings = await asyncio.to_thread(
                get_driver_standings, int(season), int(self.selected_round)
            )
            if not self.standings:
                self.error = "No driver standings are available for this race."
        except Exception:
            self.standings = []
            self.error = "Could not load driver championship data. Please try again."
        finally:
            self.loading = False

    @rx.event
    async def select_round(self, round_number: str) -> AsyncGenerator[None, None]:
        """Load driver standings through the selected race round.

        Args:
            round_number: Completed race round selected in the page filter.

        Yields:
            A state update that shows the loading panel for this round.
        """
        self.selected_round = round_number
        self.loading = True
        self.error = ""
        yield
        try:
            self.standings = await asyncio.to_thread(
                get_driver_standings,
                int(self.selected_season),
                int(round_number),
            )
            if not self.standings:
                self.error = "No driver standings are available for this race."
        except Exception:
            self.standings = []
            self.error = "Could not load driver championship data. Please try again."
        finally:
            self.loading = False


@rx.page("/drivers", "Drivers", on_load=DriversState.load_standings)
def drivers() -> rx.Component:
    """Render the driver championship page.

    Returns:
        A page with filters and the selected driver standings snapshot.
    """
    # Combine the podium and remaining rows into one content column.
    standings_content: rx.Component = rx.vstack(
        podium_section(DriversState.podium_standings, is_driver=True),
        rx.cond(
            DriversState.has_remaining_standings,
            leaderboard_section(DriversState.remaining_standings, is_driver=True),
            rx.fragment(),
        ),
        align="stretch",
        spacing="7",
        width="100%",
        padding_bottom="8",
    )

    return rx.vstack(
        navbar(active_section="drivers"),
        container(
            rx.vstack(
                page_header(
                    "Driver championship",
                    "Drivers’ Championship",
                    "Review driver standings for any season through a selected Grand Prix.",
                ),
                championship_filters(
                    DriversState.seasons,
                    DriversState.selected_season,
                    DriversState.select_season,
                    DriversState.races,
                    DriversState.selected_round,
                    DriversState.selected_round_label,
                    DriversState.select_round,
                    DriversState.season_selector_disabled,
                    DriversState.round_selector_disabled,
                ),
                # Show loading and errors before deciding whether standings
                # are available for the currently selected race.
                rx.cond(
                    DriversState.loading,
                    loading_panel(),
                    rx.cond(
                        DriversState.error != "",
                        message_panel(DriversState.error),
                        rx.cond(
                            DriversState.has_standings,
                            standings_content,
                            message_panel("No standings are available yet."),
                        ),
                    ),
                ),
                align="stretch",
                spacing="6",
                width="100%",
            ),
        ),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
