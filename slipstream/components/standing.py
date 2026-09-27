# Importing libraries
import reflex as rx


# Card for one driver's championship standing.
def standing(driver) -> rx.Component:
    return rx.card(
        rx.box(
            rx.grid(
                rx.text(
                    driver["position"],
                    size="4",
                    weight="bold",
                    text_align="center",
                ),
                rx.text(
                    driver["given_name"],
                    size="3",
                    white_space="nowrap",
                    overflow="hidden",
                    text_overflow="ellipsis",
                ),
                rx.text(
                    driver["family_name"],
                    size="3",
                    weight="medium",
                    white_space="nowrap",
                    overflow="hidden",
                    text_overflow="ellipsis",
                ),
                rx.text(
                    driver["nationality"],
                    size="2",
                    color="gray",
                    white_space="nowrap",
                    overflow="hidden",
                    text_overflow="ellipsis",
                ),
                rx.text(
                    driver["team"],
                    size="2",
                    weight="medium",
                    white_space="nowrap",
                    overflow="hidden",
                    text_overflow="ellipsis",
                ),
                rx.hstack(
                    rx.text("PTS", size="1", weight="bold", color="gray"),
                    rx.heading(driver["points"], size="4"),
                    align="center",
                    justify="end",
                    spacing="2",
                ),
                grid_template_columns=(
                    "minmax(2.5rem, 0.55fr) minmax(6rem, 1fr) "
                    "minmax(6rem, 1.2fr) minmax(7rem, 1fr) "
                    "minmax(9rem, 1.6fr) minmax(5rem, 0.75fr)"
                ),
                align_items="center",
                gap="4",
                min_width="42rem",
                width="100%",
            ),
            overflow_x="auto",
            width="100%",
        ),
        width="100%",
    )
