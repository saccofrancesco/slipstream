# Importing libraries and components
import reflex as rx
from slipstream.components import content_container, navbar


# Defining the index default page
@rx.page("/", "Home")
def index() -> rx.Component:
    return content_container(
        rx.vstack(
            navbar(),
            rx.center(
                rx.heading("Welcome to Slipstream", as_="h1", size="9"),
                width="100%",
                flex_grow="1",
            ),
            width="100%",
            min_height="100vh",
            spacing="0",
        ),
    )
