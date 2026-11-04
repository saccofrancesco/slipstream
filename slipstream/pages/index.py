"""Landing page for the Slipstream application."""

import reflex as rx

from slipstream.components import container, home_destinations, navbar, page_header


@rx.page("/", "Slipstream — Formula 1 race intelligence")
def index() -> rx.Component:
    """Render the home page and links to the main sections."""
    return rx.vstack(
        navbar(),
        container(
            rx.vstack(
                page_header(
                    "Formula 1 results",
                    "Explore the season with Slipstream.",
                    "Race weekends, championship standings, lap times, and telemetry in one place.",
                ),
                home_destinations(),
                align="stretch",
                spacing="6",
                width="100%",
                padding_bottom="8",
            ),
        ),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
