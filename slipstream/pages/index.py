# Importing libraries and components
import reflex as rx
from slipstream.components import navbar
from slipstream.components.layout import content_container


# Defining the index default page
@rx.page("/", "Home")
def index() -> rx.Component:
    return content_container(
        rx.vstack(
            navbar(),
            # Add page main content here so it shares the same width boundary.
            width="100%",
            spacing="0",
        ),
    )
