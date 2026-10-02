"""Build reusable cards for championship standings."""

# Reflex provides the reactive values and UI components used by this module.
import reflex as rx


def standing(
    entry: rx.Var[dict[str, str]],
    is_driver: bool,
    featured: bool = False,
) -> rx.Component:
    """Build a card for a driver or constructor championship standing.

    Args:
        entry: Reactive standing data used to populate the card.
        is_driver: Whether the entry describes a driver.
        featured: Whether the entry is displayed as part of the podium.

    Returns:
        A Reflex card containing the standing details.
    """
    # Select the text and border colors for this entry's position.
    podium_colors: tuple[rx.Var[str], rx.Var[str]] = podium_styles(entry["position"])
    number_color: rx.Var[str] = podium_colors[0]
    card_border_color: rx.Var[str] = podium_colors[1]

    # Build the identity details appropriate to the entry type.
    identity: rx.Component
    if is_driver:
        # Show a driver's name above their team and nationality.
        identity = rx.vstack(
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
        # Keep a constructor's name on one line.
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

    # Arrange the rank, identity, and points in a single card.
    return rx.card(
        rx.hstack(
            # Mark the card with the team's color.
            rx.box(
                width="0.5em",
                min_width="0.5em",
                min_height="2.5em",
                align_self="stretch",
                background_color=entry["team_color"],
                border_radius="1em",
            ),
            # Center rank and identity, with points in a right-aligned column.
            rx.grid(
                # Show the position and highlight podium ranks with their medal color.
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
                # Keep the points label and total aligned at the end of the row.
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


def podium_styles(
    position: rx.Var[str],
) -> tuple[rx.Var[str], rx.Var[str]]:
    """Return reactive number and border colors for a standing position.

    Args:
        position: Reactive variable containing the entry's rank.

    Returns:
        A pair containing the rank number color and card border color.
    """
    # Keep rank checks reactive so Reflex can evaluate them in the browser.
    first: rx.Var[bool] = position == "1"
    second: rx.Var[bool] = position == "2"
    third: rx.Var[bool] = position == "3"

    # Use medal colors for the top three ranks and the default text color otherwise.
    number_color: rx.Var[str] = rx.cond(
        first,
        "#E2C15A",
        rx.cond(second, "#C5CED8", rx.cond(third, "#CC8950", "inherit")),
    )
    # Match each podium card's border to its rank, with a neutral fallback.
    border_color: rx.Var[str] = rx.cond(
        first,
        "#E2C15A",
        rx.cond(
            second,
            "#C5CED8",
            rx.cond(third, "#CC8950", rx.color("gray", 5)),
        ),
    )
    return number_color, border_color
