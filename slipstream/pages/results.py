"""Current race weekend overview for the results page."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import reflex as rx
from slipstream.components import container, navbar
from slipstream.components.championship import page_header
from slipstream.services import get_current_race_weekend


class ResultsState(rx.State):
    """Load and expose the race weekend currently underway."""

    current_weekend: dict[str, str] = {}
    schedule_days: list[dict[str, str]] = []
    loading: bool = True
    error: str = ""

    @rx.var
    def has_current_weekend(self) -> bool:
        """Report whether the calendar contains an in-progress weekend."""
        return bool(self.current_weekend)

    @rx.var
    def schedule_column_count(self) -> str:
        """Set one grid column for each date with a scheduled session."""
        return str(max(len(self.schedule_days), 1))

    @rx.event
    async def load_current_weekend(self) -> AsyncGenerator[None, None]:
        """Fetch the schedule and select an event only within its date range."""
        self.loading = True
        self.error = ""
        self.current_weekend = {}
        self.schedule_days = []
        yield
        try:
            weekend: dict[str, Any] | None = await asyncio.to_thread(
                get_current_race_weekend
            )
            if weekend is not None:
                self.current_weekend = {
                    key: weekend[key]
                    for key in (
                        "round",
                        "race_name",
                        "circuit_name",
                        "locality",
                        "country",
                        "date_range",
                    )
                }
                self.schedule_days = weekend["schedule_days"]
        except Exception:
            self.current_weekend = {}
            self.schedule_days = []
            self.error = "Could not load the current race weekend. Please try again."
        finally:
            self.loading = False


def schedule_day_column(day: rx.Var[dict[str, str]]) -> rx.Component:
    """Render one date and its scheduled sessions inside the weekend card."""
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
            rx.text(
                day["sessions"],
                size="2",
                weight="medium",
                color=rx.color("gray", 12),
                white_space="pre-line",
                line_height="1.7",
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


def current_weekend_card(
    weekend: rx.Var[dict[str, str]],
    schedule_days: rx.Var[list[dict[str, str]]],
    schedule_column_count: rx.Var[str],
) -> rx.Component:
    """Render the event, circuit, location, and calendar range in a card."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text(
                        "CURRENT WEEKEND",
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
            rx.vstack(
                rx.text(
                    "EVENT SCHEDULE",
                    size="2",
                    weight="bold",
                    color=rx.color("accent", 11),
                    letter_spacing="0.14em",
                ),
                rx.grid(
                    rx.foreach(schedule_days, schedule_day_column),
                    columns=schedule_column_count,
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


def weekend_status_card(title: str, message: rx.Var | str) -> rx.Component:
    """Render loading, empty, or error feedback in the shared card style."""
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


@rx.page("/results", "Results", on_load=ResultsState.load_current_weekend)
def results() -> rx.Component:
    """Render a weekend overview when today's date falls within its dates."""
    return rx.vstack(
        navbar(),
        container(
            rx.vstack(
                page_header(
                    "Race weekend",
                    "Results",
                    "Follow the action from the current Formula 1 weekend.",
                ),
                rx.cond(
                    ResultsState.loading,
                    weekend_status_card(
                        "Loading the race weekend", "Checking the Formula 1 calendar…"
                    ),
                    rx.cond(
                        ResultsState.error != "",
                        weekend_status_card(
                            "Weekend overview unavailable", ResultsState.error
                        ),
                        rx.cond(
                            ResultsState.has_current_weekend,
                            current_weekend_card(
                                ResultsState.current_weekend,
                                ResultsState.schedule_days,
                                ResultsState.schedule_column_count,
                            ),
                            weekend_status_card(
                                "No race weekend is underway",
                                "The weekend overview will appear here once a Grand Prix weekend begins.",
                            ),
                        ),
                    ),
                ),
                align="stretch",
                spacing="6",
                width="100%",
                padding_bottom="8",
            ),
        ),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
