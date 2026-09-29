# Importing libraries
import reflex as rx


# Card for one driver's championship standing.
def driver_standing(driver) -> rx.Component:
    number_color, podium_outline = podium_styles(driver["position"])
    return rx.card(
        rx.hstack(
            rx.box(
                width="0.5em",
                min_width="0.5px",
                min_height="2em",
                align_self="stretch",
                background_color=driver["team_color"],
                border_radius="1em",
            ),
            rx.box(
                rx.grid(
                    rx.text(
                        driver["position"],
                        size="5",
                        weight="bold",
                        text_align="center",
                        color=number_color,
                    ),
                    rx.text(
                        driver["given_name"],
                        size="4",
                        text_transform="uppercase",
                        white_space="nowrap",
                        overflow="hidden",
                        text_overflow="ellipsis",
                    ),
                    rx.text(
                        driver["family_name"],
                        size="4",
                        weight="bold",
                        text_transform="uppercase",
                        white_space="nowrap",
                        overflow="hidden",
                        text_overflow="ellipsis",
                    ),
                    rx.text(
                        driver["nationality"],
                        size="3",
                        color="gray",
                        text_transform="uppercase",
                        white_space="nowrap",
                        overflow="hidden",
                        text_overflow="ellipsis",
                    ),
                    rx.text(
                        driver["team"],
                        size="3",
                        weight="medium",
                        text_transform="uppercase",
                        white_space="nowrap",
                        overflow="hidden",
                        text_overflow="ellipsis",
                    ),
                    rx.hstack(
                        rx.text("PTS", size="3", weight="bold", color="gray"),
                        rx.heading(driver["points"], size="5"),
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
            align="center",
            spacing="3",
            width="100%",
        ),
        size="1",
        outline=podium_outline,
        outline_offset="-1px",
        width="100%",
    )


# Card for one constructor's championship standing.
def constructor_standing(constructor) -> rx.Component:
    number_color, podium_outline = podium_styles(constructor["position"])
    return rx.card(
        rx.hstack(
            rx.box(
                width="0.5em",
                min_width="0.5px",
                min_height="2em",
                align_self="stretch",
                background_color=constructor["team_color"],
                border_radius="1em",
            ),
            rx.box(
                rx.grid(
                    rx.text(
                        constructor["position"],
                        size="5",
                        weight="bold",
                        text_align="center",
                        color=number_color,
                    ),
                    rx.box(),
                    rx.text(
                        constructor["constructor"],
                        size="4",
                        weight="bold",
                        text_transform="uppercase",
                        white_space="nowrap",
                        overflow="hidden",
                        text_overflow="ellipsis",
                    ),
                    rx.box(),
                    rx.box(),
                    rx.hstack(
                        rx.text("PTS", size="3", weight="bold", color="gray"),
                        rx.heading(constructor["points"], size="5"),
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
            align="center",
            spacing="3",
            width="100%",
        ),
        size="1",
        outline=podium_outline,
        outline_offset="-1px",
        width="100%",
    )


# Helper function to compute if the standing need a custom podium outline style or not
def podium_styles(position):
    first: bool = position == "1"
    second: bool = position == "2"
    third: bool = position == "3"
    number_color: str = rx.cond(
        first,
        "#A87500",
        rx.cond(second, "#66717E", rx.cond(third, "#9C4F20", "inherit")),
    )
    outline: str = rx.cond(
        first,
        "2px solid #D6B143",
        rx.cond(
            second,
            "2px solid #AEB7C2",
            rx.cond(third, "2px solid #B87538", "none"),
        ),
    )
    return number_color, outline
