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
from slipstream.services import get_constructor_standings


class ConstructorsState(rx.State):
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
            self.standings = await asyncio.to_thread(get_constructor_standings)
            if not self.standings:
                self.error = "No constructor standings are available yet."
        except Exception:
            self.standings = []
            self.error = "Could not load constructor standings. Please try again."
        finally:
            self.loading = False


# Defining the page to show constructor championship standings.
@rx.page("/constructors", "Teams", on_load=ConstructorsState.load_standings)
def constructors() -> rx.Component:
    standings_content = rx.vstack(
        podium_section(ConstructorsState.podium_standings, is_driver=False),
        rx.cond(
            ConstructorsState.has_remaining_standings,
            leaderboard_section(
                ConstructorsState.remaining_standings, is_driver=False
            ),
            rx.fragment(),
        ),
        align="stretch",
        spacing="7",
        width="100%",
        padding_bottom="8",
    )

    return rx.vstack(
        navbar(active_section="teams"),
        container(
            rx.vstack(
                page_header(
                    "Team championship",
                    "Teams’ Championship",
                    "See how each team is shaping the constructors’ championship.",
                ),
                rx.cond(
                    ConstructorsState.loading,
                    loading_panel(),
                    rx.cond(
                        ConstructorsState.error != "",
                        message_panel(ConstructorsState.error),
                        rx.cond(
                            ConstructorsState.has_standings,
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
