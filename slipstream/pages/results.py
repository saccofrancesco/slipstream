"""Featured race weekend and season archive for the results page."""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal
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
    TrackSessionDetails,
    call_data_source,
    format_weekend_schedule,
    get_past_events,
    get_race_weekend,
    get_track_session_details,
    has_session_results,
)

logger = logging.getLogger(__name__)


def _set_result_status(
    days: list[ScheduleDay], code: str,
    status: Literal["pending", "available", "unpublished", "error"],
) -> list[ScheduleDay]:
    """Return new schedule rows with one session's availability updated."""
    return [
        {
            **day,
            "sessions": [
                {**session, "result_status": status}
                if session["code"] == code
                else session
                for session in day["sessions"]
            ],
        }
        for day in days
    ]


def _session_completed(session: ScheduledSession, today: date) -> bool:
    """Classify a started session as completed after its known or likely end."""
    starts_at = session["starts_at"]
    if not starts_at:
        return False
    start = datetime.fromisoformat(starts_at)
    end = (
        datetime.fromisoformat(session["ends_at"])
        if session["ends_at"]
        else start + timedelta(hours=3)
    )
    now = datetime.now(timezone.utc)
    return end <= now or start.date() < today


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
    load_id: int = 0

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

    @rx.event(background=True)
    async def load_race_weekend(self) -> None:
        """Show the schedule first, then load independent details and results."""
        current_date = date.today()
        async with self:
            self.load_id += 1
            load_id = self.load_id
            self.loading = True
            self.archive_loading = True
            self.error = ""
            self.archive_error = ""
            self.race_weekend = {}
            self.schedule_days = []
            self.track_time = False
            self.past_events = []
            self.archive_season = str(current_date.year)

        try:
            weekend: RaceWeekend | None = await asyncio.to_thread(
                call_data_source, get_race_weekend, current_date, fresh=True
            )
        except Exception:
            logger.exception("Could not load the featured race weekend")
            weekend = None
            async with self:
                if self.load_id == load_id:
                    self.error = "Could not load the race schedule. Please try again."

        async with self:
            if self.load_id != load_id:
                return
            if weekend is not None:
                self.archive_season = weekend["season"]
                self.race_weekend = {
                    key: value
                    for key, value in weekend.items()
                    if key != "schedule_days"
                }
                self.schedule_days = weekend["schedule_days"]
            self.loading = False

        archive_season = weekend["season"] if weekend else str(current_date.year)
        tasks = [self._load_archive(load_id, archive_season, current_date)]
        if weekend is not None:
            tasks.append(self._load_track_details(load_id, weekend))
            if weekend["status"] == "current":
                tasks.append(self._check_session_results(load_id, weekend, current_date))
        await asyncio.gather(*tasks)

    async def _load_archive(
        self, load_id: int, season: str, current_date: date
    ) -> None:
        """Populate the archive without delaying the weekend card."""
        try:
            events = await asyncio.to_thread(
                call_data_source, get_past_events, season, current_date, fresh=True
            )
        except Exception:
            logger.exception("Could not load the %s archive", season)
            events = []
            error = "Could not load past events. Please try again."
        else:
            error = ""
        async with self:
            if self.load_id == load_id:
                self.past_events = events
                self.archive_error = error
                self.archive_loading = False

    @rx.event(background=True)
    async def retry_archive(self) -> None:
        """Retry the archive independently of the featured weekend."""
        async with self:
            self.archive_error = ""
            self.archive_loading = True
            load_id = self.load_id
            season = self.archive_season
        await self._load_archive(load_id, season, date.today())

    async def _load_track_details(self, load_id: int, weekend: RaceWeekend) -> None:
        """Add optional local-time offsets when their source responds."""
        try:
            details: dict[str, TrackSessionDetails] = await asyncio.to_thread(
                call_data_source,
                get_track_session_details,
                weekend["season"],
                weekend["round"],
                fresh=True,
            )
        except Exception:
            logger.exception("Could not load track-time details for %s/%s", weekend["season"], weekend["round"])
            return
        async with self:
            if self.load_id != load_id:
                return
            self.schedule_days = [
                {
                    **day,
                    "sessions": [
                        {
                            **session,
                            "track_offset_minutes": (
                                details[session["name"]]["offset_minutes"]
                                if session["name"] in details else None
                            ),
                            "ends_at": (
                                details[session["name"]]["ends_at"]
                                if session["name"] in details else ""
                            ),
                        }
                        for session in day["sessions"]
                    ],
                }
                for day in self.schedule_days
            ]

    async def _check_session_results(
        self, load_id: int, weekend: RaceWeekend, current_date: date
    ) -> None:
        """Check each started session separately and publish its status."""
        for day in weekend["schedule_days"]:
            for session in day["sessions"]:
                async with self:
                    if self.load_id != load_id:
                        return
                if not session["result_check_due"]:
                    continue
                status = await self._result_status(
                    weekend["season"], weekend["round"], session, current_date
                )
                async with self:
                    if self.load_id != load_id:
                        return
                    self.schedule_days = _set_result_status(
                        self.schedule_days, session["code"], status
                    )

    async def _result_status(
        self, season: str, round_number: str, session: ScheduledSession,
        current_date: date,
    ) -> Literal["available", "unpublished", "error"]:
        """Distinguish published rows, unpublished rows, and failed checks."""
        try:
            available = await asyncio.to_thread(
                call_data_source,
                has_session_results,
                season,
                round_number,
                session["code"],
                _session_completed(session, current_date),
                fresh=True,
            )
        except Exception:
            logger.exception(
                "Could not check results for %s/%s/%s",
                season, round_number, session["code"],
            )
            return "error"
        return "available" if available else "unpublished"

    @rx.event(background=True)
    async def retry_result(self, code: str) -> None:
        """Retry one failed availability check without reloading the page."""
        async with self:
            if not self.race_weekend:
                return
            session = next(
                (item for day in self.schedule_days for item in day["sessions"]
                 if item["code"] == code and item["result_status"] == "error"),
                None,
            )
            if session is None:
                return
            weekend = dict(self.race_weekend)
            load_id = self.load_id
            self.schedule_days = _set_result_status(self.schedule_days, code, "pending")
        status = await self._result_status(
            weekend["season"], weekend["round"], session, date.today()
        )
        async with self:
            if self.load_id == load_id:
                self.schedule_days = _set_result_status(self.schedule_days, code, status)


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
                    loading_card("Preparing the race weekend schedule…"),
                    rx.cond(
                        ResultsState.error != "",
                        rx.vstack(
                            status_card(
                                "Weekend overview unavailable", ResultsState.error
                            ),
                            rx.button(
                                "Retry schedule",
                                on_click=ResultsState.load_race_weekend,
                                variant="soft",
                            ),
                            align="start",
                            spacing="2",
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
                                ResultsState.retry_result,
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
                    ResultsState.retry_archive,
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
