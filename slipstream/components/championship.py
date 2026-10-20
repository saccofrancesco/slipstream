"""Build championship standings sections and feedback panels."""

from typing import Literal

import reflex as rx

from .layout import container, loading_card, page_header, status_card
from .navbar import navbar
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


def championship_section(
    podium: rx.Var[list[dict[str, str]]],
    remaining: rx.Var[list[dict[str, str]]],
    has_remaining: rx.Var[bool],
    has_standings: rx.Var[bool],
    loading: rx.Var[bool],
    error: rx.Var[str],
    is_driver: bool,
) -> rx.Component:
    """Render the shared championship loading, feedback, and standings flow."""
    standings_content: rx.Component = rx.vstack(
        podium_section(podium, is_driver=is_driver),
        rx.cond(
            has_remaining,
            leaderboard_section(remaining, is_driver=is_driver),
            rx.fragment(),
        ),
        align="stretch",
        spacing="7",
        width="100%",
        padding_bottom="8",
    )
    return rx.cond(
        loading,
        loading_card("Loading championship standings…"),
        rx.cond(
            error != "",
            status_card("Standings unavailable", error),
            rx.cond(
                has_standings,
                standings_content,
                status_card("Standings unavailable", "No standings are available yet."),
            ),
        ),
    )


def championship_page(
    podium: rx.Var[list[dict[str, str]]],
    remaining: rx.Var[list[dict[str, str]]],
    has_remaining: rx.Var[bool],
    has_standings: rx.Var[bool],
    loading: rx.Var[bool],
    error: rx.Var[str],
    *,
    active_section: Literal["drivers", "teams"],
    eyebrow: str,
    title: str,
    description: str,
    is_driver: bool,
) -> rx.Component:
    """Render the shared responsive page shell for a championship route."""
    return rx.vstack(
        navbar(active_section=active_section),
        container(
            rx.vstack(
                page_header(eyebrow, title, description),
                championship_section(
                    podium,
                    remaining,
                    has_remaining,
                    has_standings,
                    loading,
                    error,
                    is_driver=is_driver,
                ),
                align="stretch",
                spacing="6",
                width="100%",
            ),
        ),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
