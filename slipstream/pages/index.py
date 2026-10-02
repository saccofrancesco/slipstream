"""Landing page for the Slipstream application."""

# Reflex provides the UI component and page registration APIs.
import reflex as rx

# Reuse the shared layout and site navigation.
from slipstream.components import container, navbar


@rx.page("/", "Home")
def index() -> rx.Component:
    """Render the landing page and its welcome heading."""
    return rx.vstack(
        navbar(),
        container(
            rx.center(
                rx.heading("WELCOME TO SLIPSTREAM", as_="h1", size="9"),
                width="100%",
                min_height="calc(100vh - 5rem)",
            ),
        ),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
