import reflex as rx
from slipstream.components import container, navbar


@rx.page("/results", "Results")
def results() -> rx.Component:
    return rx.vstack(
        navbar(),
        container(),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
