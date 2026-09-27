# Importing libraries and components
import reflex as rx
from slipstream.components import container, navbar


# Defining the index default page
@rx.page("/", "Home")
def index() -> rx.Component:
    return rx.vstack(
        navbar(),
        container(
            rx.center(
                rx.heading("Welcome to Slipstream", as_="h1", size="9"),
                width="100%",
                min_height="calc(100vh - 5rem)",
            ),
        ),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
