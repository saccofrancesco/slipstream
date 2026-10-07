"""Featured race weekend and season archive for the results page."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import date

import reflex as rx
from slipstream.components import (
    container,
    loading_card,
    navbar,
    page_header,
    status_card,
)
from slipstream.components.weekend import (
    race_weekend_card,
    season_archive_section,
)
from slipstream.services import (
    PastEvent,
    RaceWeekend,
    ScheduleDay,
    get_past_events,
    get_race_weekend,
)


class ResultsState(rx.State):
    """Hold the featured weekend, its schedule, and the season archive.

    Scalar event details, schedule days, and archive entries are stored
    separately so each list can render with ``rx.foreach``.
    """

    race_weekend: dict[str, str] = {}
    schedule_days: list[ScheduleDay] = []
    past_events: list[PastEvent] = []
    archive_season: str = str(date.today().year)
    loading: bool = True
    archive_loading: bool = True
    error: str = ""
    archive_error: str = ""

    @rx.var
    def has_race_weekend(self) -> bool:
        """Report whether the calendar contains a current or future weekend."""
        return bool(self.race_weekend)

    @rx.var
    def has_past_events(self) -> bool:
        """Report whether the chosen season has any completed races."""
        return bool(self.past_events)

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
        """Load the featured weekend, then its season's past events.

        Yields:
            Loading feedback, followed by the featured weekend when ready.
        """
        current_date: date = date.today()
        # Clear the previous result before yielding so a reload cannot show
        # stale event details or archive entries during either request.
        self.loading = True
        self.archive_loading = True
        self.error = ""
        self.archive_error = ""
        self.race_weekend = {}
        self.schedule_days = []
        self.past_events = []
        self.archive_season = str(current_date.year)
        yield
        try:
            # The FastF1 client is synchronous; keep its request off the
            # Reflex event loop while retaining an async page-load event.
            weekend: RaceWeekend | None = await asyncio.to_thread(
                get_race_weekend, current_date
            )
            if weekend is not None:
                self.archive_season = weekend["season"]
                # Keep the card's scalar values separate from its list of
                # schedule rows, which has a different state type.
                self.race_weekend = {
                    "status": weekend["status"],
                    "round": weekend["round"],
                    "race_name": weekend["race_name"],
                    "circuit_name": weekend["circuit_name"],
                    "locality": weekend["locality"],
                    "country": weekend["country"],
                    "country_flag": weekend["country_flag"],
                    "date_range": weekend["date_range"],
                }
                self.schedule_days = weekend["schedule_days"]
        except Exception:
            self.race_weekend = {}
            self.schedule_days = []
            self.error = "Could not load the race schedule. Please try again."
        finally:
            self.loading = False
        yield

        try:
            self.past_events = await asyncio.to_thread(
                get_past_events, self.archive_season, current_date
            )
        except Exception:
            self.past_events = []
            self.archive_error = "Could not load past events. Please try again."
        finally:
            self.archive_loading = False


@rx.page("/results", "Results", on_load=ResultsState.load_race_weekend)
def results() -> rx.Component:
    """Render the featured weekend and the matching season archive.

    Returns:
        The Results page with navigation, featured weekend, and past events.
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
                    loading_card("Checking the Formula 1 calendar…"),
                    rx.cond(
                        ResultsState.error != "",
                        status_card(
                            "Weekend overview unavailable", ResultsState.error
                        ),
                        rx.cond(
                            ResultsState.has_race_weekend,
                            race_weekend_card(
                                ResultsState.race_weekend,
                                ResultsState.schedule_days,
                                ResultsState.schedule_column_count,
                            ),
                            status_card(
                                "No upcoming race is scheduled",
                                "The next Grand Prix weekend will appear here when its calendar is published.",
                            ),
                        ),
                    ),
                ),
                season_archive_section(
                    ResultsState.archive_season,
                    ResultsState.past_events,
                    ResultsState.archive_loading,
                    ResultsState.archive_error,
                    ResultsState.has_past_events,
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
