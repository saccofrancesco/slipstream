"""Components for the current or upcoming race weekend overview."""

import reflex as rx
from slipstream.services import ScheduleDay, ScheduledSession


def _schedule_session_row(session: rx.Var[ScheduledSession]) -> rx.Component:
    """Keep a session's name and UTC start time on one aligned row."""
    return rx.hstack(
        rx.text(
            session["name"],
            size="2",
            weight="medium",
            color=rx.color("gray", 12),
        ),
        rx.text(
            session["time"],
            size="2",
            weight="bold",
            color=rx.color("accent", 11),
            white_space="nowrap",
            font_variant_numeric="tabular-nums",
            text_align="right",
            flex_shrink="0",
        ),
        justify="between",
        align="start",
        spacing="3",
        width="100%",
    )


def _schedule_day_column(day: rx.Var[ScheduleDay]) -> rx.Component:
    """Render one date and its sessions inside the weekend card.

    Args:
        day: Reactive row containing the date and timed sessions.

    Returns:
        A card for one scheduled day.
    """
    return rx.card(
        rx.vstack(
            rx.text(
                day["day"],
                size="2",
                weight="bold",
                color=rx.color("accent", 11),
                letter_spacing="0.08em",
            ),
            rx.text(day["date"], size="2", color=rx.color("gray", 10)),
            rx.separator(),
            rx.vstack(
                rx.foreach(day["sessions"], _schedule_session_row),
                align="stretch",
                spacing="2",
                width="100%",
            ),
            align="stretch",
            spacing="2",
            width="100%",
        ),
        size="2",
        width="100%",
        background_color=rx.color("gray", 1),
        border_width="1px",
        border_style="solid",
        border_color=rx.color("gray", 5),
    )


def race_weekend_card(
    weekend: rx.Var[dict[str, str]],
    schedule_days: rx.Var[list[ScheduleDay]],
    schedule_column_count: rx.Var[str],
) -> rx.Component:
    """Render the selected event details and its schedule.

    Args:
        weekend: Reactive event fields such as race and circuit names.
        schedule_days: Reactive schedule rows, one for each event date.
        schedule_column_count: Reactive number of grid columns as a string.

    Returns:
        A card with the event identity, venue, dates, and sessions.
    """
    return rx.card(
        rx.vstack(
            # Bind the header to the reactive fields updated by ResultsState.
            rx.hstack(
                rx.vstack(
                    rx.text(
                        rx.cond(
                            weekend["status"] == "current",
                            "CURRENT WEEKEND",
                            "UPCOMING WEEKEND",
                        ),
                        size="2",
                        weight="bold",
                        color=rx.color("accent", 11),
                        letter_spacing="0.14em",
                    ),
                    rx.heading(
                        weekend["race_name"],
                        as_="h2",
                        size="7",
                        weight="bold",
                        letter_spacing="-0.03em",
                    ),
                    align="start",
                    spacing="1",
                ),
                rx.badge(
                    f"ROUND {weekend['round']}",
                    color_scheme="red",
                    variant="soft",
                    size="2",
                ),
                justify="between",
                align="start",
                width="100%",
                flex_wrap="wrap",
                gap="3",
            ),
            rx.separator(),
            rx.hstack(
                rx.icon("map-pin", size=20, color=rx.color("accent", 11)),
                rx.vstack(
                    rx.text(weekend["circuit_name"], weight="bold"),
                    rx.text(
                        f"{weekend['locality']}, {weekend['country']}",
                        color=rx.color("gray", 11),
                    ),
                    align="start",
                    spacing="1",
                ),
                align="center",
                spacing="3",
                width="100%",
            ),
            rx.hstack(
                rx.icon("calendar-days", size=20, color=rx.color("accent", 11)),
                rx.text(weekend["date_range"], weight="medium"),
                align="center",
                spacing="3",
                width="100%",
            ),
            rx.separator(),
            # rx.foreach renders one card for each reactive schedule row; the
            # state-derived column count controls how those cards form a grid.
            rx.vstack(
                rx.hstack(
                    rx.text(
                        "EVENT SCHEDULE",
                        size="2",
                        weight="bold",
                        color=rx.color("accent", 11),
                        letter_spacing="0.14em",
                    ),
                    rx.text("ALL TIMES UTC", size="1", color=rx.color("gray", 10)),
                    justify="between",
                    align="center",
                    width="100%",
                    flex_wrap="wrap",
                    gap="2",
                ),
                rx.grid(
                    rx.foreach(schedule_days, _schedule_day_column),
                    columns=rx.breakpoints(initial="1", md=schedule_column_count),
                    spacing="3",
                    width="100%",
                ),
                align="stretch",
                spacing="3",
                width="100%",
            ),
            align="stretch",
            spacing="4",
            width="100%",
        ),
        width="100%",
        background_color=rx.color("gray", 2),
        border_width="1px",
        border_style="solid",
        border_color=rx.color("gray", 5),
    )


def weekend_status_card(title: str, message: rx.Var[str] | str) -> rx.Component:
    """Render loading, empty, or error feedback in the shared card style.

    Args:
        title: Heading for the current request status.
        message: Static text or a reactive error message.

    Returns:
        A status card matching the race weekend card's appearance.
    """
    return rx.card(
        rx.hstack(
            rx.box(
                rx.icon("flag", size=20, color=rx.color("accent", 11)),
                padding="3",
                border_radius="full",
                background_color=rx.color("accent", 3),
            ),
            rx.vstack(
                rx.heading(title, size="4", weight="bold"),
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
