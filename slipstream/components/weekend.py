"""Components for the featured weekend and the past-race archive."""

import reflex as rx
from slipstream.services import PastEvent, ScheduleDay, ScheduledSession

from .flag import flag_icon
from .layout import loading_card


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
                    rx.hstack(
                        rx.cond(
                            weekend["country_flag"] != "",
                            rx.box(
                                flag_icon(
                                    weekend["country_flag"], weekend["country"]
                                ),
                                font_size="2rem",
                                line_height="1",
                                flex_shrink="0",
                            ),
                            rx.fragment(),
                        ),
                        rx.heading(
                            weekend["race_name"],
                            as_="h2",
                            size="7",
                            weight="bold",
                            letter_spacing="-0.03em",
                            min_width="0",
                            flex="1",
                        ),
                        align="center",
                        spacing="2",
                        width="100%",
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
                    rx.hstack(
                        rx.text(
                            f"{weekend['locality']}, {weekend['country']}",
                            color=rx.color("gray", 11),
                        ),
                        align="center",
                        spacing="2",
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


def event_header(event: rx.Var[dict[str, str]]) -> rx.Component:
    """Use the selected Grand Prix details as the event page header.

    Args:
        event: Normalized event fields for the dynamic session-results page.

    Returns:
        A responsive page header above the session selector.
    """
    return rx.vstack(
        rx.hstack(
            rx.text(
                f"{event['season']} FORMULA 1 GRAND PRIX",
                size="2",
                weight="bold",
                color=rx.color("accent", 11),
                letter_spacing="0.14em",
            ),
            rx.badge(
                f"ROUND {event['round']}",
                color_scheme="red",
                variant="soft",
                size="2",
                white_space="nowrap",
            ),
            align="center",
            flex_wrap="wrap",
            gap="2",
            width="100%",
        ),
        rx.hstack(
            rx.cond(
                event["country_flag"] != "",
                rx.box(
                    flag_icon(event["country_flag"], event["country"]),
                    font_size="2.25rem",
                    line_height="1",
                    flex_shrink="0",
                ),
                rx.fragment(),
            ),
            rx.heading(
                event["race_name"],
                as_="h1",
                size="9",
                weight="bold",
                font_size="clamp(2rem, 6vw, 3.5rem)",
                letter_spacing="-0.04em",
                line_height="1.05",
                min_width="0",
            ),
            align="center",
            spacing="3",
            width="100%",
        ),
        rx.vstack(
            rx.hstack(
                rx.icon("map-pin", size=17, color=rx.color("accent", 11)),
                rx.text(
                    f"{event['circuit_name']} · {event['locality']}, {event['country']}",
                    size="3",
                    color=rx.color("gray", 11),
                ),
                align="start",
                spacing="2",
                width="100%",
            ),
            rx.hstack(
                rx.icon("calendar-days", size=17, color=rx.color("accent", 11)),
                rx.text(
                    event["date_range"],
                    size="3",
                    color=rx.color("gray", 11),
                ),
                align="center",
                spacing="2",
            ),
            align="start",
            spacing="2",
            width="100%",
        ),
        align="start",
        spacing="3",
        width="100%",
        padding_top="2",
        padding_bottom="3",
    )


def _past_event_card(
    event: rx.Var[PastEvent], season: rx.Var[str]
) -> rx.Component:
    """Render one compact archive entry as a full-card event link."""
    return rx.link(
        rx.card(
            rx.hstack(
                rx.cond(
                    event["country_flag"] != "",
                    rx.box(
                        flag_icon(event["country_flag"], event["country"]),
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        font_size="2rem",
                        width="2.75rem",
                        min_width="2.75rem",
                        min_height="2.75rem",
                    ),
                    rx.fragment(),
                ),
                rx.vstack(
                    rx.text(
                        event["race_name"],
                        size="3",
                        weight="bold",
                        color=rx.color("gray", 12),
                        line_height="1.3",
                        overflow="hidden",
                        text_overflow="ellipsis",
                        white_space="nowrap",
                        width="100%",
                    ),
                    rx.cond(
                        event["circuit_name"] != "",
                        rx.hstack(
                            rx.text(
                                event["circuit_name"],
                                size="2",
                                color=rx.color("gray", 10),
                                line_height="1.3",
                                overflow="hidden",
                                text_overflow="ellipsis",
                                white_space="nowrap",
                                min_width="0",
                                flex_shrink="1",
                            ),
                            rx.text("·", size="2", color=rx.color("gray", 9)),
                            rx.text(
                                event["race_date"],
                                size="2",
                                color=rx.color("gray", 11),
                                white_space="nowrap",
                                flex_shrink="0",
                            ),
                            align="center",
                            spacing="1",
                            width="100%",
                        ),
                        rx.text(
                            event["race_date"],
                            size="2",
                            color=rx.color("gray", 11),
                            white_space="nowrap",
                        ),
                    ),
                    align="stretch",
                    spacing="1",
                    min_width="0",
                    flex="1",
                ),
                rx.badge(
                    f"ROUND {event['round']}",
                    color_scheme="red",
                    variant="soft",
                    size="2",
                    flex_shrink="0",
                    white_space="nowrap",
                    padding_x="3",
                    padding_y="2",
                ),
                align="center",
                spacing="3",
                width="100%",
            ),
            size="2",
            width="100%",
            background_color=rx.color("gray", 2),
            border_width="1px",
            border_style="solid",
            border_color=rx.color("gray", 5),
            transition="border-color 150ms ease, transform 150ms ease",
            _hover={
                "border_color": rx.color("accent", 8),
                "transform": "translateY(-1px)",
            },
        ),
        href=f"/results/{season}/{event['round']}",
        underline="none",
        width="100%",
        key=event["round"],
    )


def _archive_message(message: rx.Var[str] | str) -> rx.Component:
    """Show a short loading, empty, or error message below the archive title."""
    return rx.card(
        rx.text(message, size="2", color=rx.color("gray", 11)),
        size="1",
        width="100%",
        background_color=rx.color("gray", 2),
        border_width="1px",
        border_style="solid",
        border_color=rx.color("gray", 5),
    )


def season_archive_section(
    season: rx.Var[str],
    events: rx.Var[list[PastEvent]],
    loading: rx.Var[bool],
    error: rx.Var[str],
    has_events: rx.Var[bool],
) -> rx.Component:
    """Render a season's past races as a compact, vertically flowing list."""

    def render_event(event: rx.Var[PastEvent]) -> rx.Component:
        """Bind the archive season to one event card's destination."""
        return _past_event_card(event, season)

    return rx.vstack(
        rx.heading(f"{season} Season archive", as_="h2", size="5"),
        rx.cond(
            loading,
            loading_card("Loading past events…"),
            rx.cond(
                error != "",
                _archive_message(error),
                rx.cond(
                    has_events,
                    rx.vstack(
                        rx.foreach(events, render_event),
                        align="stretch",
                        spacing="2",
                        width="100%",
                    ),
                    _archive_message("No past events in this season yet."),
                ),
            ),
        ),
        align="stretch",
        spacing="3",
        width="100%",
    )
