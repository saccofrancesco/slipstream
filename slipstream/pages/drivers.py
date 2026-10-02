"""Driver championship page and its loading state."""

import asyncio
from collections.abc import AsyncGenerator

# Reflex provides state, event, and component primitives for this page.
import reflex as rx

# Reuse shared presentation components and the driver standings service.
from slipstream.components import container, navbar
from slipstream.components.championship import (
    leaderboard_section,
    loading_panel,
    message_panel,
    page_header,
    podium_section,
)
from slipstream.services import get_driver_standings


class DriversState(rx.State):
    """Hold and derive the data shown on the driver championship page."""

    standings: list[dict[str, str]] = []
    loading: bool = False
    error: str = ""

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
        """Load driver standings and update the page's loading state.

        Yields:
            A state update after loading begins so the page can show its spinner.
        """
        # Set the loading state before starting the network request.
        self.loading = True
        self.error = ""
        yield
        try:
            # Run the blocking API client call outside the event loop.
            self.standings = await asyncio.to_thread(get_driver_standings)
            if not self.standings:
                self.error = "No driver standings are available yet."
        except Exception:
            # Keep the UI usable and show a short message if loading fails.
            self.standings = []
            self.error = "Could not load driver standings. Please try again."
        finally:
            # Clear the loading indicator on both success and failure.
            self.loading = False


@rx.page("/drivers", "Drivers", on_load=DriversState.load_standings)
def drivers() -> rx.Component:
    """Render the driver championship page."""
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
                    "Follow the drivers setting the pace across this season’s championship.",
                ),
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
