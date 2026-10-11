"""Team championship page and its loading state."""

import asyncio
from collections.abc import AsyncGenerator

# Reflex provides state, event, and component primitives for this page.
import reflex as rx

# Reuse shared presentation components and the constructor standings service.
from slipstream.components import container, navbar, page_header
from slipstream.components.championship import championship_section
from slipstream.services import (
    get_available_seasons,
    get_completed_races,
    get_constructor_standings,
)


class ConstructorsState(rx.State):
    """Hold the latest team standings and page feedback."""

    standings: list[dict[str, str]] = []
    loading: bool = False
    error: str = ""

    @rx.var
    def podium_standings(self) -> list[dict[str, str]]:
        """Return the first three constructor standings for the podium."""
        return self.standings[:3]

    @rx.var
    def remaining_standings(self) -> list[dict[str, str]]:
        """Return constructor standings after the first three entries."""
        return self.standings[3:]

    @rx.var
    def has_remaining_standings(self) -> bool:
        """Report whether rows remain after the podium."""
        return len(self.standings) > 3

    @rx.var
    def has_standings(self) -> bool:
        """Report whether any constructor standings were loaded."""
        return bool(self.standings)

    @rx.event
    async def load_standings(self) -> AsyncGenerator[None, None]:
        """Load the newest completed race's constructor standings.

        Yields:
            A state update after loading begins so the page can show its spinner.
        """
        # Set the loading state before starting the network request.
        self.loading = True
        self.error = ""
        self.standings = []
        yield
        try:
            # Run the blocking API client call outside the event loop.
            seasons = await asyncio.to_thread(get_available_seasons, 1958)
            if not seasons:
                self.error = "Championship data is not available yet."
                return
            season = seasons[0]
            races = await asyncio.to_thread(get_completed_races, season)
            if not races:
                self.error = "No completed races are available yet."
                return
            latest_race = races[-1]
            self.standings = await asyncio.to_thread(
                get_constructor_standings,
                int(season),
                int(latest_race["round"]),
            )
            if not self.standings:
                self.error = "No constructor standings are available for this race."
        except Exception:
            # Keep the UI usable and show a short message if loading fails.
            self.standings = []
            self.error = (
                "Could not load constructor championship data. Please try again."
            )
        finally:
            # Clear the loading indicator on both success and failure.
            self.loading = False


@rx.page("/constructors", "Teams", on_load=ConstructorsState.load_standings)
def constructors() -> rx.Component:
    """Render the team championship page.

    Returns:
        A page with the latest team standings snapshot.
    """
    return rx.vstack(
        navbar(active_section="teams"),
        container(
            rx.vstack(
                page_header(
                    "Team championship",
                    "Teams’ Championship",
                    "Latest team championship standings.",
                ),
                championship_section(
                    ConstructorsState.podium_standings,
                    ConstructorsState.remaining_standings,
                    ConstructorsState.has_remaining_standings,
                    ConstructorsState.has_standings,
                    ConstructorsState.loading,
                    ConstructorsState.error,
                    is_driver=False,
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
