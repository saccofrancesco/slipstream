# Importing libraries and components
import reflex as rx
from slipstream.components import content_container, navbar


# Defining the page to show drivers details such as standings and results
@rx.page("/drivers", "Drivers")
def drivers() -> rx.Component:
    return content_container(
        rx.vstack(
            navbar(),
            width="100%",
            spacing="0",
        ),
    )
