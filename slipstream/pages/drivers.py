# Importing libraries and components
import asyncio
import reflex as rx
from slipstream.components import container, navbar, standing
from slipstream.services import get_driver_standings


class DriversState(rx.State):
    standings: list[dict[str, str]] = []
    loading: bool = False
    error: str = ""

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
    return rx.vstack(
        navbar(),
        container(
            rx.vstack(
                rx.heading("DRIVERS STANDINGS", as_="h1", size="7"),
                rx.cond(
                    DriversState.loading,
                    rx.center(rx.spinner(), width="100%", padding_y="4em"),
                    rx.cond(
                        DriversState.error != "",
                        rx.text(DriversState.error, color="tomato"),
                        rx.vstack(
                            rx.foreach(DriversState.standings, standing),
                            width="100%",
                            align="stretch",
                            spacing="3",
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
