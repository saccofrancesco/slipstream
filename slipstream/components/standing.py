# Importing libraries
import reflex as rx


# Card for one driver's or constructor's championship standing.
def standing(entry, is_driver: bool) -> rx.Component:
    number_color, podium_outline = podium_styles(entry["position"])
    if is_driver:
        detail_cells: tuple[rx.Component] = (
            rx.text(
                entry["given_name"],
                size="4",
                text_transform="uppercase",
                white_space="nowrap",
                overflow="hidden",
                text_overflow="ellipsis",
            ),
            rx.text(
                entry["family_name"],
                size="4",
                weight="bold",
                text_transform="uppercase",
                white_space="nowrap",
                overflow="hidden",
                text_overflow="ellipsis",
            ),
            rx.text(
                entry["nationality"],
                size="3",
                color="gray",
                text_transform="uppercase",
                white_space="nowrap",
                overflow="hidden",
                text_overflow="ellipsis",
            ),
            rx.text(
                entry["team"],
                size="3",
                weight="medium",
                text_transform="uppercase",
                white_space="nowrap",
                overflow="hidden",
                text_overflow="ellipsis",
            ),
        )
    else:
        detail_cells: tuple[rx.Component] = (
            rx.box(),
            rx.text(
                entry["constructor"],
                size="4",
                weight="bold",
                text_transform="uppercase",
                white_space="nowrap",
                overflow="hidden",
                text_overflow="ellipsis",
            ),
            rx.box(),
            rx.box(),
        )

    return rx.card(
        rx.hstack(
            rx.box(
                width="0.5em",
                min_width="0.5px",
                min_height="2em",
                align_self="stretch",
                background_color=entry["team_color"],
                border_radius="1em",
            ),
            rx.box(
                rx.grid(
                    rx.text(
                        entry["position"],
                        size="5",
                        weight="bold",
                        text_align="center",
                        color=number_color,
                    ),
                    *detail_cells,
                    rx.hstack(
                        rx.text("PTS", size="3", weight="bold", color="gray"),
                        rx.heading(entry["points"], size="5"),
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
        "#E2C15A",
        rx.cond(second, "#C5CED8", rx.cond(third, "#CC8950", "inherit")),
    )
    outline: str = rx.cond(
        first,
        "2px solid #E2C15A",
        rx.cond(
            second,
            "2px solid #C5CED8",
            rx.cond(third, "2px solid #CC8950", "none"),
        ),
    )
    return number_color, outline
