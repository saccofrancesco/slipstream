# Importing libraries
import reflex as rx


# Card for a podium entry or a row in the remaining championship standings.
def standing(entry, is_driver: bool, featured: bool = False) -> rx.Component:
    number_color, card_border_color = podium_styles(entry["position"])
    if is_driver:
        identity: rx.Component = rx.vstack(
            rx.text(
                entry["given_name"],
                " ",
                entry["family_name"],
                size="4" if featured else "3",
                weight="bold",
                line_height="1.25",
                overflow="hidden",
                text_overflow="ellipsis",
                white_space="nowrap",
                width="100%",
            ),
            rx.hstack(
                rx.text(
                    entry["team"],
                    size="2",
                    weight="medium",
                    color=rx.color("gray", 11),
                    overflow="hidden",
                    text_overflow="ellipsis",
                    white_space="nowrap",
                ),
                rx.text("·", size="2", color=rx.color("gray", 9)),
                rx.text(
                    entry["nationality"],
                    size="2",
                    color=rx.color("gray", 10),
                    white_space="nowrap",
                ),
                align="center",
                spacing="2",
                width="100%",
                overflow="hidden",
            ),
            align="start",
            spacing="1",
            width="100%",
        )
    else:
        identity = rx.hstack(
            rx.text(
                entry["constructor"],
                size="4",
                weight="bold",
                white_space="nowrap",
                overflow="hidden",
                text_overflow="ellipsis",
                width="100%",
            ),
            align="center",
            spacing="3",
            width="100%",
        )

    return rx.card(
        rx.hstack(
            rx.box(
                width="0.5em",
                min_width="0.5em",
                min_height="2.5em",
                align_self="stretch",
                background_color=entry["team_color"],
                border_radius="1em",
            ),
            rx.grid(
                rx.vstack(
                    rx.text(
                        "RANK",
                        size="1",
                        weight="bold",
                        color=rx.color("gray", 10),
                        letter_spacing="0.1em",
                    ),
                    rx.text(
                        entry["position"],
                        size="7" if featured else "5",
                        weight="bold",
                        color=number_color,
                        line_height="1",
                    ),
                    align="center",
                    spacing="1",
                ),
                identity,
                rx.vstack(
                    rx.text(
                        "POINTS",
                        size="1",
                        weight="bold",
                        color=rx.color("gray", 10),
                        letter_spacing="0.1em",
                    ),
                    rx.text(
                        entry["points"],
                        size="6" if featured else "4",
                        weight="bold",
                        line_height="1",
                        text_align="right",
                    ),
                    align="end",
                    spacing="1",
                ),
                grid_template_columns="3.25rem minmax(0, 1fr) auto",
                align_items="center",
                gap="3" if featured else "2",
                width="100%",
            ),
            align="center",
            spacing="3",
            width="100%",
        ),
        size="2" if featured else "1",
        width="100%",
        background_color=rx.color("gray", 2),
        border_width="2px" if featured else "1px",
        border_style="solid",
        border_color=card_border_color,
    )


# Return the podium number and card border colors for a standing position.
def podium_styles(position):
    first: bool = position == "1"
    second: bool = position == "2"
    third: bool = position == "3"
    number_color: str = rx.cond(
        first,
        "#E2C15A",
        rx.cond(second, "#C5CED8", rx.cond(third, "#CC8950", "inherit")),
    )
    border_color: str = rx.cond(
        first,
        "#E2C15A",
        rx.cond(
            second,
            "#C5CED8",
            rx.cond(third, "#CC8950", rx.color("gray", 5)),
        ),
    )
    return number_color, border_color
