"""Featured race weekend and season archive for the results page."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import reflex as rx
from reflex.event import EventSpec
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
    ScheduledSession,
    format_weekend_schedule,
    get_past_events,
    get_race_weekend,
    get_track_time_offsets,
    has_session_results,
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
    viewer_timezone: str = "UTC"
    track_time: bool = False

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
        return str(max(len(self.display_schedule_days), 1))

    @rx.var
    def display_schedule_days(self) -> list[ScheduleDay]:
        """Show sessions on the visitor's or the circuit's calendar dates."""
        days, _ = format_weekend_schedule(
            self.schedule_days,
            self.viewer_timezone,
            "track" if self.track_time else "my",
        )
        return days

    @rx.var
    def display_date_range(self) -> str:
        """Keep the weekend date range in the selected timezone."""
        _, date_range = format_weekend_schedule(
            self.schedule_days,
            self.viewer_timezone,
            "track" if self.track_time else "my",
        )
        return date_range or self.race_weekend.get("date_range", "")

    @rx.var
    def track_time_available(self) -> bool:
        """Allow circuit time only when its offset was published."""
        return any(
            session["track_offset_minutes"] is not None
            for day in self.schedule_days
            for session in day["sessions"]
        )

    @rx.event
    def detect_viewer_timezone(self) -> EventSpec:
        """Read the visitor's IANA timezone from their browser."""
        return rx.call_script(
            "Intl.DateTimeFormat().resolvedOptions().timeZone",
            callback=ResultsState.set_viewer_timezone,
        )

    @rx.event
    def set_viewer_timezone(self, timezone_name: str) -> None:
        """Accept a browser timezone when the server can format it."""
        try:
            ZoneInfo(timezone_name)
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            self.viewer_timezone = "UTC"
        else:
            self.viewer_timezone = timezone_name

    @rx.event
    def set_track_time(self, enabled: bool) -> None:
        """Use circuit time when the switch is on and an offset exists."""
        self.track_time = enabled and self.track_time_available

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
        self.track_time = False
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
                track_offsets = await asyncio.to_thread(
                    get_track_time_offsets, weekend["season"], weekend["round"]
                )
                self.archive_season = weekend["season"]
                # Keep the card's scalar values separate from its list of
                # schedule rows, which has a different state type.
                self.race_weekend = {
                    "season": weekend["season"],
                    "status": weekend["status"],
                    "round": weekend["round"],
                    "race_name": weekend["race_name"],
                    "circuit_name": weekend["circuit_name"],
                    "locality": weekend["locality"],
                    "country": weekend["country"],
                    "country_flag": weekend["country_flag"],
                    "date_range": weekend["date_range"],
                }
                self.schedule_days = [
                    {
                        **day,
                        "sessions": [
                            {
                                **session,
                                "track_offset_minutes": track_offsets.get(
                                    session["name"]
                                ),
                            }
                            for session in day["sessions"]
                        ],
                    }
                    for day in weekend["schedule_days"]
                ]
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
        yield

        if self.race_weekend.get("status") == "current":
            # Only a published driver result table makes a session linkable.
            # Treat feed failures independently so other sessions can appear.
            sessions: list[ScheduledSession] = [
                session
                for day in self.schedule_days
                for session in day["sessions"]
            ]
            checks = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        has_session_results,
                        self.race_weekend["season"],
                        self.race_weekend["round"],
                        session["code"],
                    )
                    for session in sessions
                ),
                return_exceptions=True,
            )
            available_codes: set[str] = {
                session["code"]
                for session, available in zip(sessions, checks)
                if available is True
            }
            self.schedule_days = [
                {
                    "day": day["day"],
                    "date": day["date"],
                    "date_iso": day["date_iso"],
                    "sessions": [
                        {
                            **session,
                            "results_available": session["code"] in available_codes,
                        }
                        for session in day["sessions"]
                    ],
                }
                for day in self.schedule_days
            ]
            yield


@rx.page(
    "/results",
    "Results",
    on_load=[ResultsState.detect_viewer_timezone, ResultsState.load_race_weekend],
)
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
                                ResultsState.display_schedule_days,
                                ResultsState.schedule_column_count,
                                ResultsState.display_date_range,
                                ResultsState.track_time,
                                ResultsState.track_time_available,
                                ResultsState.set_track_time,
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
