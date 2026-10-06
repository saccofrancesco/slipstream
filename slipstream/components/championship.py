"""Build championship standings sections and feedback panels."""

# Reflex provides the reactive values and UI components used below.
import reflex as rx

# Reuse the standing card for both podium and leaderboard rows.
from .standing import standing


def podium_section(
    entries: rx.Var[list[dict[str, str]]], is_driver: bool
) -> rx.Component:
    """Render the top three standings as featured podium cards.

    Args:
        entries: Reactive list of standings to display.
        is_driver: Whether each entry contains driver details.

    Returns:
        A section heading followed by the featured standing cards.
    """
    # Give the podium a typed renderer so each reactive entry is explicit.
    def render_podium_entry(entry: rx.Var[dict[str, str]]) -> rx.Component:
        """Wrap one featured standing card with podium spacing.

        Args:
            entry: Reactive driver or constructor standing.

        Returns:
            A padded podium card for this entry.
        """
        return rx.box(
            standing(entry, is_driver=is_driver, featured=True),
            width="100%",
            padding="1",
        )

    # Give featured cards a full row each until there is room for three.
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.text(
                    "THE PODIUM",
                    size="2",
                    weight="bold",
                    color=rx.color("accent", 11),
                    letter_spacing="0.14em",
                ),
                rx.heading("Leading the way", size="5", weight="bold"),
                align="start",
                spacing="1",
            ),
            align="start",
            width="100%",
        ),
        rx.grid(
            rx.foreach(
                entries,
                render_podium_entry,
            ),
            columns=rx.breakpoints(initial="1", lg="3"),
            spacing="2",
            width="100%",
        ),
        align="stretch",
        width="100%",
    )


def leaderboard_section(
    entries: rx.Var[list[dict[str, str]]],
    is_driver: bool,
) -> rx.Component:
    """Render the standings after the featured podium entries.

    Args:
        entries: Reactive list of standings to display as regular rows.
        is_driver: Whether each entry contains driver details.

    Returns:
        A section heading followed by the remaining standings rows.
    """
    # Render each reactive entry using the regular, non-featured card layout.
    def render_standing(entry: rx.Var[dict[str, str]]) -> rx.Component:
        """Build one regular row in the standings leaderboard.

        Args:
            entry: Reactive driver or constructor standing.

        Returns:
            A nonfeatured standing card for this entry.
        """
        return standing(entry, is_driver=is_driver)

    # Keep the heading separate from the vertically stacked rows.
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.text(
                    "FULL STANDINGS",
                    size="2",
                    weight="bold",
                    color=rx.color("accent", 11),
                    letter_spacing="0.14em",
                ),
                rx.heading("The field", size="5", weight="bold"),
                align="start",
                spacing="1",
            ),
            width="100%",
        ),
        rx.vstack(
            rx.foreach(
                entries,
                render_standing,
            ),
            align="stretch",
            spacing="2",
            width="100%",
        ),
        align="stretch",
        spacing="3",
        width="100%",
    )


def loading_panel() -> rx.Component:
    """Build a card that explains standings are currently loading.

    Returns:
        A centered loading indicator and status message.
    """
    # Center the spinner and its message inside a neutral panel.
    return rx.card(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text("Loading championship standings…", color=rx.color("gray", 11)),
            align="center",
            spacing="3",
            padding_y="8",
            width="100%",
        ),
        width="100%",
        background_color=rx.color("gray", 2),
    )


def message_panel(message: rx.Var[str] | str) -> rx.Component:
    """Build a feedback card for an unavailable or empty standings result.

    Args:
        message: Static text or a reactive message to show to the user.

    Returns:
        A card with an icon, heading, and explanatory message.
    """
    # Pair a status icon with the heading and caller-supplied explanation.
    return rx.card(
        rx.hstack(
            rx.box(
                rx.icon("flag", size=20, color=rx.color("accent", 11)),
                padding="3",
                border_radius="full",
                background_color=rx.color("accent", 3),
            ),
            rx.vstack(
                rx.heading("Standings unavailable", size="4", weight="bold"),
                rx.text(message, color=rx.color("gray", 11), line_height="1.5"),
                align="start",
                spacing="1",
                width="100%",
            ),
            align="center",
            spacing="4",
            width="100%",
        ),
        width="100%",
        background_color=rx.color("gray", 2),
        border_width="1px",
        border_style="solid",
        border_color=rx.color("gray", 5),
    )
