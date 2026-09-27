# Importing libraries
import reflex as rx


# Card for one driver's championship standing.
def standing(driver) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.center(
                rx.text(driver["position"], size="4", weight="bold"),
                width="3em",
                height="3em",
                border="1px solid var(--gray-6)",
                border_radius="9999px",
            ),
            rx.vstack(
                rx.heading(
                    driver["given_name"],
                    " ",
                    driver["family_name"],
                    size="4",
                ),
                rx.text(driver["nationality"], size="2", color="gray"),
                rx.text(driver["team"], size="2", weight="medium"),
                align="start",
                spacing="1",
                flex_grow="1",
            ),
            rx.vstack(
                rx.text("POINTS", size="1", weight="bold", color="gray"),
                rx.heading(driver["points"], size="5"),
                align="end",
                spacing="0",
            ),
            align="center",
            justify="between",
            spacing="4",
            width="100%",
        ),
        width="100%",
    )
