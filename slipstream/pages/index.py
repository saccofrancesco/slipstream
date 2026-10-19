"""Landing page for the Slipstream application."""

# Reflex provides the UI component and page registration APIs.
import reflex as rx

# Reuse the shared layout, site navigation, and landing-page presentation.
from slipstream.components import container, home_destinations, home_hero, navbar


@rx.page("/", "Slipstream — Formula 1 race intelligence")
def index() -> rx.Component:
    """Render the Slipstream landing page.

    Returns:
        The home page with its hero and primary section links.
    """
    return rx.vstack(
        navbar(),
        container(
            rx.vstack(
                home_hero(),
                home_destinations(),
                align="stretch",
                spacing="8",
                width="100%",
            ),
        ),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
