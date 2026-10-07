"""Reusable selector and ranked driver cards for session results."""

import reflex as rx

from slipstream.services import DriverClassification, SessionOption

from .flag import flag_icon
from .layout import loading_card, status_card
from .standing import podium_styles


def _session_option(option: rx.Var[SessionOption]) -> rx.Component:
    """Render one scheduled session as a select item."""
    return rx.select.item(option["name"], value=option["code"])


def _classification_row(entry: rx.Var[DriverClassification]) -> rx.Component:
    """Render one driver's time and rank in the selected session."""
    position_color, border_color = podium_styles(entry["position"])
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
                        size="5",
                        weight="bold",
                        color=position_color,
                        line_height="1",
                    ),
                    align="center",
                    spacing="1",
                ),
                rx.vstack(
                    rx.hstack(
                        flag_icon(entry["country_flag"], entry["nationality"]),
                        rx.text(
                            entry["given_name"],
                            " ",
                            entry["family_name"],
                            size="3",
                            weight="bold",
                            line_height="1.25",
                            overflow="hidden",
                            text_overflow="ellipsis",
                            white_space="nowrap",
                            min_width="0",
                        ),
                        align="center",
                        spacing="2",
                        width="100%",
                        min_width="0",
                        overflow="hidden",
                    ),
                    rx.text(
                        entry["team"],
                        size="2",
                        weight="medium",
                        color=rx.color("gray", 11),
                        overflow="hidden",
                        text_overflow="ellipsis",
                        white_space="nowrap",
                        width="100%",
                    ),
                    align="start",
                    spacing="1",
                    width="100%",
                    min_width="0",
                ),
                rx.vstack(
                    rx.text(
                        entry["time_label"],
                        size="1",
                        weight="bold",
                        color=rx.color("gray", 10),
                        letter_spacing="0.1em",
                    ),
                    rx.text(
                        entry["time"],
                        size="4",
                        weight="bold",
                        line_height="1",
                        text_align="right",
                        white_space="nowrap",
                        font_variant_numeric="tabular-nums",
                    ),
                    align="end",
                    spacing="1",
                ),
                grid_template_columns="3.25rem minmax(0, 1fr) auto",
                align_items="center",
                gap="2",
                width="100%",
            ),
            align="center",
            spacing="3",
            width="100%",
        ),
        size="1",
        width="100%",
        background_color=rx.color("gray", 2),
        border_width="1px",
        border_style="solid",
        border_color=border_color,
        key=f"{entry['given_name']}_{entry['family_name']}",
    )


def session_classification_section(
    sessions: rx.Var[list[SessionOption]],
    selected_session: rx.Var[str],
    selected_session_label: rx.Var[str],
    on_session_change: rx.EventHandler,
    loading: rx.Var[bool],
    error: rx.Var[str],
    classification: rx.Var[list[DriverClassification]],
    has_classification: rx.Var[bool],
) -> rx.Component:
    """Render the session selector and only its selected classification."""
    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.text(
                    "SELECT SESSION",
                    size="1",
                    weight="bold",
                    color=rx.color("gray", 10),
                    letter_spacing="0.1em",
                ),
                rx.select.root(
                    rx.select.trigger(
                        rx.text(selected_session_label),
                        width="100%",
                    ),
                    rx.select.content(
                        rx.foreach(sessions, _session_option),
                        position="popper",
                        width="100%",
                    ),
                    value=selected_session,
                    on_change=on_session_change,
                    disabled=loading | (sessions.length() == 0),
                    width="100%",
                    size="3",
                ),
                align="stretch",
                spacing="2",
                width="100%",
            ),
            width="100%",
            background_color=rx.color("gray", 2),
            border_width="1px",
            border_style="solid",
            border_color=rx.color("gray", 5),
        ),
        rx.cond(
            loading,
            loading_card("Loading the selected classification…"),
            rx.cond(
                error != "",
                status_card("Session results unavailable", error),
                rx.cond(
                    has_classification,
                    rx.vstack(
                        rx.vstack(
                            rx.text(
                                "SESSION CLASSIFICATION",
                                size="2",
                                weight="bold",
                                color=rx.color("accent", 11),
                                letter_spacing="0.14em",
                            ),
                            rx.heading(
                                selected_session_label,
                                as_="h2",
                                size="5",
                                weight="bold",
                            ),
                            align="start",
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.foreach(classification, _classification_row),
                            align="stretch",
                            spacing="2",
                            width="100%",
                        ),
                        align="stretch",
                        spacing="3",
                        width="100%",
                    ),
                    status_card(
                        "No classification available",
                        "The timing feed has not published results for this session.",
                    ),
                ),
            ),
        ),
        align="stretch",
        spacing="4",
        width="100%",
    )
