"""Current race weekend overview for the results page."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import reflex as rx
from slipstream.components import container, navbar, page_header
from slipstream.components.weekend import current_weekend_card, weekend_status_card
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


@rx.page("/results", "Results", on_load=ResultsState.load_current_weekend)
def results() -> rx.Component:
    """Render a weekend overview when today's date falls within its dates."""
    return rx.vstack(
        navbar(active_section="results"),
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
