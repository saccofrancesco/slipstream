"""Current race weekend overview for the results page."""

import asyncio
from collections.abc import AsyncGenerator

import reflex as rx
from slipstream.components import container, navbar, page_header
from slipstream.components.weekend import current_weekend_card, weekend_status_card
from slipstream.services import (
    CurrentRaceWeekend,
    ScheduleDay,
    get_current_race_weekend,
)


class ResultsState(rx.State):
    """Hold the current weekend, its schedule, and the request status.

    Scalar event details and schedule rows are stored separately so the card
    can render each schedule date with ``rx.foreach``.
    """

    current_weekend: dict[str, str] = {}
    schedule_days: list[ScheduleDay] = []
    loading: bool = True
    error: str = ""

    @rx.var
    def has_current_weekend(self) -> bool:
        """Report whether the calendar contains an in-progress weekend."""
        return bool(self.current_weekend)

    @rx.var
    def schedule_column_count(self) -> str:
        """Give the schedule grid one column per date, with one as a minimum."""
        return str(max(len(self.schedule_days), 1))

    @rx.event
    async def load_current_weekend(self) -> AsyncGenerator[None, None]:
        """Fetch the current weekend and publish its display data.

        Yields:
            A state update that shows the loading card before the API call.
        """
        # Clear the previous result before yielding so a reload cannot show
        # stale event details while the calendar request is in progress.
        self.loading = True
        self.error = ""
        self.current_weekend = {}
        self.schedule_days = []
        yield
        try:
            # The FastF1 client is synchronous; keep its request off the
            # Reflex event loop while retaining an async page-load event.
            weekend: CurrentRaceWeekend | None = await asyncio.to_thread(
                get_current_race_weekend
            )
            if weekend is not None:
                # Keep the card's scalar values separate from its list of
                # schedule rows, which has a different state type.
                self.current_weekend = {
                    "round": weekend["round"],
                    "race_name": weekend["race_name"],
                    "circuit_name": weekend["circuit_name"],
                    "locality": weekend["locality"],
                    "country": weekend["country"],
                    "date_range": weekend["date_range"],
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
    """Render the current weekend or the appropriate request status.

    Returns:
        The Results page with navigation, header, and weekend content.
    """
    return rx.vstack(
        navbar(active_section="results"),
        container(
            rx.vstack(
                page_header(
                    "Race weekend",
                    "Results",
                    "Follow the action from the current Formula 1 weekend.",
                ),
                # Resolve loading and errors before checking for an event;
                # an empty result has its own explanatory status card.
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
