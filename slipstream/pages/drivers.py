# Importing libraries and components
import asyncio
import reflex as rx
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
    standings: list[dict[str, str]] = []
    loading: bool = False
    error: str = ""

    @rx.var
    def podium_standings(self) -> list[dict[str, str]]:
        return self.standings[:3]

    @rx.var
    def remaining_standings(self) -> list[dict[str, str]]:
        return self.standings[3:]

    @rx.var
    def has_remaining_standings(self) -> bool:
        return len(self.standings) > 3

    @rx.var
    def has_standings(self) -> bool:
        return bool(self.standings)

    @rx.event
    async def load_standings(self):
        self.loading = True
        self.error = ""
        yield
        try:
            self.standings = await asyncio.to_thread(get_driver_standings)
            if not self.standings:
                self.error = "No driver standings are available yet."
        except Exception:
            self.standings = []
            self.error = "Could not load driver standings. Please try again."
        finally:
            self.loading = False


# Defining the page to show drivers details such as standings and results
@rx.page("/drivers", "Drivers", on_load=DriversState.load_standings)
def drivers() -> rx.Component:
    standings_content = rx.vstack(
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
