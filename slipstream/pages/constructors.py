"""Team championship page and its loading state."""

import asyncio
import logging

# Reflex provides state, event, and component primitives for this page.
import reflex as rx

# Reuse shared presentation components and the constructor standings service.
from slipstream.components import container, navbar, page_header
from slipstream.components.championship import championship_section
from slipstream.services import (
    call_data_source,
    get_available_seasons,
    get_completed_races,
    get_constructor_standings,
    UpstreamDataError,
)

logger = logging.getLogger(__name__)


class ConstructorsState(rx.State):
    """Hold the latest team standings and page feedback."""

    standings: list[dict[str, str]] = []
    loading: bool = False
    error: str = ""
    load_id: int = 0

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

    @rx.event(background=True)
    async def load_standings(self) -> None:
        """Load current constructor standings outside the Reflex state lock."""
        async with self:
            self.load_id += 1
            load_id = self.load_id
            self.loading = True
            self.error = ""
            self.standings = []
        try:
            seasons = await asyncio.to_thread(
                call_data_source, get_available_seasons, 1958, fresh=True
            )
            if not seasons:
                rows, error = [], "Championship data is not available yet."
            else:
                races = await asyncio.to_thread(
                    call_data_source, get_completed_races, seasons[0], fresh=True
                )
                if not races:
                    rows, error = [], "No completed races are available yet."
                else:
                    rows = await asyncio.to_thread(
                        call_data_source,
                        get_constructor_standings,
                        int(seasons[0]),
                        int(races[-1]["round"]),
                        fresh=True,
                    )
                    if not rows:
                        raise UpstreamDataError("Completed-race constructor standings were empty.")
                    error = ""
        except Exception:
            logger.exception("Could not load constructor standings")
            rows, error = [], "Could not load constructor championship data. Please try again."
        async with self:
            if self.load_id == load_id:
                self.standings = rows
                self.error = error
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
