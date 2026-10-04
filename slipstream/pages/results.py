"""Current or upcoming race weekend overview for the results page."""

import asyncio
from collections.abc import AsyncGenerator

import reflex as rx
from slipstream.components import container, navbar, page_header
from slipstream.components.weekend import race_weekend_card, weekend_status_card
from slipstream.services import (
    RaceWeekend,
    ScheduleDay,
    get_race_weekend,
)


class ResultsState(rx.State):
    """Hold the selected weekend, its schedule, and the request status.

    Scalar event details and schedule rows are stored separately so the card
    can render each schedule date with ``rx.foreach``.
    """

    race_weekend: dict[str, str] = {}
    schedule_days: list[ScheduleDay] = []
    loading: bool = True
    error: str = ""

    @rx.var
    def has_race_weekend(self) -> bool:
        """Report whether the calendar contains a current or future weekend."""
        return bool(self.race_weekend)

    @rx.var
    def weekend_heading(self) -> str:
        """Label the page for the selected weekend."""
        if not self.race_weekend:
            return "Race weekend"
        return (
            "Current race weekend"
            if self.race_weekend["status"] == "current"
            else "Upcoming race weekend"
        )

    @rx.var
    def weekend_description(self) -> str:
        """Describe the selected weekend without suggesting it is underway."""
        if not self.race_weekend:
            return "Explore the Formula 1 race calendar."
        return (
            "Follow the action from the current Formula 1 weekend."
            if self.race_weekend["status"] == "current"
            else "Get ready for the next Formula 1 weekend."
        )

    @rx.var
    def schedule_column_count(self) -> str:
        """Give the schedule grid one column per date, with one as a minimum."""
        return str(max(len(self.schedule_days), 1))

    @rx.event
    async def load_race_weekend(self) -> AsyncGenerator[None, None]:
        """Fetch the current or next weekend and publish its display data.

        Yields:
            A state update that shows the loading card before the API call.
        """
        # Clear the previous result before yielding so a reload cannot show
        # stale event details while the calendar request is in progress.
        self.loading = True
        self.error = ""
        self.race_weekend = {}
        self.schedule_days = []
        yield
        try:
            # The FastF1 client is synchronous; keep its request off the
            # Reflex event loop while retaining an async page-load event.
            weekend: RaceWeekend | None = await asyncio.to_thread(
                get_race_weekend
            )
            if weekend is not None:
                # Keep the card's scalar values separate from its list of
                # schedule rows, which has a different state type.
                self.race_weekend = {
                    "status": weekend["status"],
                    "round": weekend["round"],
                    "race_name": weekend["race_name"],
                    "circuit_name": weekend["circuit_name"],
                    "locality": weekend["locality"],
                    "country": weekend["country"],
                    "date_range": weekend["date_range"],
                }
                self.schedule_days = weekend["schedule_days"]
        except Exception:
            self.race_weekend = {}
            self.schedule_days = []
            self.error = "Could not load the race schedule. Please try again."
        finally:
            self.loading = False


@rx.page("/results", "Results", on_load=ResultsState.load_race_weekend)
def results() -> rx.Component:
    """Render the current or next weekend, or the request status.

    Returns:
        The Results page with navigation, header, and weekend content.
    """
    return rx.vstack(
        navbar(active_section="results"),
        container(
            rx.vstack(
                page_header(
                    ResultsState.weekend_heading,
                    "Results",
                    ResultsState.weekend_description,
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
                            ResultsState.has_race_weekend,
                            race_weekend_card(
                                ResultsState.race_weekend,
                                ResultsState.schedule_days,
                                ResultsState.schedule_column_count,
                            ),
                            weekend_status_card(
                                "No upcoming race is scheduled",
                                "The next Grand Prix weekend will appear here when its calendar is published.",
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
