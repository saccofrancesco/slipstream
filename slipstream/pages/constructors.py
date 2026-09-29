# Importing libraries and components
import asyncio
import reflex as rx
from slipstream.components import container, navbar, standing
from slipstream.services import get_constructor_standings


class ConstructorsState(rx.State):
    standings: list[dict[str, str]] = []
    loading: bool = False
    error: str = ""

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
@rx.page("/constructors", "Constructors", on_load=ConstructorsState.load_standings)
def constructors() -> rx.Component:
    return rx.vstack(
        navbar(),
        container(
            rx.vstack(
                rx.heading("CONSTRUCTOR STANDINGS", as_="h1", size="7"),
                rx.cond(
                    ConstructorsState.loading,
                    rx.center(rx.spinner(), width="100%", padding_y="4em"),
                    rx.cond(
                        ConstructorsState.error != "",
                        rx.text(ConstructorsState.error, color="tomato"),
                        rx.vstack(
                            rx.foreach(
                                ConstructorsState.standings,
                                lambda constructor: standing(
                                    constructor, is_driver=False
                                ),
                            ),
                            width="100%",
                            align="stretch",
                            spacing="2",
                        ),
                    ),
                ),
                width="100%",
                align="stretch",
                spacing="4",
            ),
        ),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
