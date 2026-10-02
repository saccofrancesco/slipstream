"""Build shared headers, standings sections, and feedback panels."""

# Reflex provides the reactive values and UI components used below.
import reflex as rx

# Reuse the standing card for both podium and leaderboard rows.
from .standing import standing


def page_header(eyebrow: str, title: str, description: str) -> rx.Component:
    """Build the eyebrow, title, and description at the top of a page.

    Args:
        eyebrow: Short uppercase label above the page title.
        title: Main page heading.
        description: Supporting sentence below the heading.

    Returns:
        A vertically stacked page header component.
    """
    # Group the small label, prominent title, and supporting description.
    return rx.vstack(
        rx.text(
            eyebrow,
            size="2",
            weight="bold",
            color=rx.color("accent", 11),
            letter_spacing="0.16em",
            text_transform="uppercase",
        ),
        rx.heading(
            title,
            as_="h1",
            size="9",
            weight="bold",
            font_size="clamp(2rem, 6vw, 3.5rem)",
            letter_spacing="-0.04em",
            line_height="1.05",
        ),
        rx.text(
            description,
            size="4",
            color=rx.color("gray", 11),
            max_width="42rem",
            line_height="1.6",
        ),
        align="start",
        spacing="2",
        width="100%",
        padding_top="7",
        padding_bottom="2",
    )


def championship_filters(
    seasons: rx.Var[list[str]],
    selected_season: rx.Var[str],
    on_season_change: rx.EventHandler,
    races: rx.Var[list[dict[str, str]]],
    selected_round: rx.Var[str],
    selected_round_label: rx.Var[str],
    on_round_change: rx.EventHandler,
    season_disabled: rx.Var[bool],
    round_disabled: rx.Var[bool],
) -> rx.Component:
    """Build the shared season and completed-race selectors.

    Args:
        seasons: Available season years for the first selector.
        selected_season: Currently selected season year.
        on_season_change: Event handler called when the season changes.
        races: Completed race options for the selected season.
        selected_round: Round number currently selected.
        selected_round_label: Race label shown in the round selector trigger.
        on_round_change: Event handler called when the selected race changes.
        season_disabled: Whether the season selector is unavailable.
        round_disabled: Whether the race selector is unavailable.

    Returns:
        A compact responsive card containing both selectors.
    """

    def render_race_option(race: rx.Var[dict[str, str]]) -> rx.Component:
        """Render one race option with its numeric round as the value."""
        return rx.select.item(race["label"], value=race["round"])

    return rx.card(
        rx.hstack(
            rx.vstack(
                rx.text(
                    "SEASON",
                    size="1",
                    weight="bold",
                    color=rx.color("gray", 10),
                    letter_spacing="0.1em",
                ),
                rx.select(
                    seasons,
                    value=selected_season,
                    on_change=on_season_change,
                    disabled=season_disabled,
                    width="100%",
                    size="3",
                ),
                align="stretch",
                spacing="2",
                width="100%",
            ),
            rx.vstack(
                rx.text(
                    "STANDINGS THROUGH",
                    size="1",
                    weight="bold",
                    color=rx.color("gray", 10),
                    letter_spacing="0.1em",
                ),
                rx.select.root(
                    rx.select.trigger(
                        rx.text(selected_round_label),
                        width="100%",
                    ),
                    rx.select.content(
                        rx.foreach(races, render_race_option),
                        position="popper",
                        width="100%",
                    ),
                    value=selected_round,
                    on_change=on_round_change,
                    disabled=round_disabled,
                    width="100%",
                    size="3",
                ),
                align="stretch",
                spacing="2",
                width="100%",
            ),
            width="100%",
        ),
        width="100%",
        background_color=rx.color("gray", 2),
    )


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
        """Wrap one featured standing card with podium spacing."""
        return rx.box(
            standing(entry, is_driver=is_driver, featured=True),
            width="100%",
            padding="1",
        )

    # Pair the section label with one horizontally arranged card per entry.
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
        rx.hstack(
            rx.foreach(
                entries,
                render_podium_entry,
            ),
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
        """Build one regular row in the standings leaderboard."""
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


def message_panel(message: rx.Var | str) -> rx.Component:
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
