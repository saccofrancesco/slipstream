"""Archive event detail route and its selected-session classification state."""

import asyncio
from collections.abc import AsyncGenerator

import reflex as rx

from slipstream.components import container, navbar, page_header
from slipstream.components.classification import session_classification_section
from slipstream.components.weekend import event_summary_card, weekend_status_card
from slipstream.services import (
    DriverClassification,
    EventDetails,
    SessionOption,
    get_event_details,
    get_session_classification,
)


class EventState(rx.State):
    """Hold event details and the classification for one selected session."""

    event_season: str = ""
    round_number: str = ""
    event: dict[str, str] = {}
    sessions: list[SessionOption] = []
    selected_session: str = "R"
    classification: list[DriverClassification] = []
    loading: bool = True
    error: str = ""

    @rx.var
    def has_event(self) -> bool:
        """Report whether valid event metadata has been loaded."""
        return bool(self.event)

    @rx.var
    def has_classification(self) -> bool:
        """Report whether the selected session has driver results."""
        return bool(self.classification)

    @rx.var
    def selected_session_label(self) -> str:
        """Return the display label for the currently selected session."""
        for session in self.sessions:
            if session["code"] == self.selected_session:
                return session["name"]
        return "Race"

    @rx.event
    async def load_event(self) -> AsyncGenerator[None, None]:
        """Load route event metadata, then its default Race classification."""
        params: dict[str, str] = self.router.page.params
        self.event_season = params.get("season", "")
        self.round_number = params.get("round", "")
        self.event = {}
        self.sessions = []
        self.selected_session = "R"
        self.classification = []
        self.error = ""
        self.loading = True
        yield

        try:
            details: EventDetails | None = await asyncio.to_thread(
                get_event_details, self.event_season, self.round_number
            )
        except Exception:
            self.error = "Could not load this archive event. Please try again."
            self.loading = False
            return

        if details is None:
            self.error = "The requested archive event could not be found."
            self.loading = False
            return

        self.event = {
            "season": details["season"],
            "round": details["round"],
            "race_name": details["race_name"],
            "race_date": details["race_date"],
            "circuit_name": details["circuit_name"],
            "locality": details["locality"],
            "country": details["country"],
            "country_flag": details["country_flag"],
            "date_range": details["date_range"],
        }
        self.sessions = details["sessions"]
        yield

        await self._load_classification(self.selected_session)
        self.loading = False

    @rx.event
    async def select_session(
        self, session_code: str
    ) -> AsyncGenerator[None, None]:
        """Replace the visible classification with a selected session's rows.

        Args:
            session_code: FastF1 identifier selected from the event schedule.

        Yields:
            A state update that clears old rows and displays loading feedback.
        """
        if not self.event or not any(
            session["code"] == session_code for session in self.sessions
        ):
            return

        self.selected_session = session_code
        self.classification = []
        self.error = ""
        self.loading = True
        yield

        await self._load_classification(session_code)
        self.loading = False

    async def _load_classification(self, session_code: str) -> None:
        """Fetch one session's driver rows without blocking the event loop."""
        try:
            rows: list[DriverClassification] = await asyncio.to_thread(
                get_session_classification,
                self.event_season,
                self.round_number,
                session_code,
            )
        except Exception:
            self.classification = []
            self.error = "Could not load this session's classification. Please try again."
            return

        self.classification = rows
        if not rows:
            self.error = (
                "The timing feed has not published results for this session."
            )


@rx.page("/results/[season]/[round]", "Session results", on_load=EventState.load_event)
def event_results() -> rx.Component:
    """Render one archived event and the selected session classification."""
    return rx.vstack(
        navbar(active_section="results"),
        container(
            rx.vstack(
                page_header(
                    "Formula 1 archive",
                    "Session results",
                    "Choose a session to view its driver classification.",
                ),
                rx.link(
                    rx.hstack(
                        rx.icon("arrow-left", size=16),
                        rx.text("Back to Results", size="2", weight="medium"),
                        align="center",
                        spacing="2",
                    ),
                    href="/results",
                    underline="none",
                    color=rx.color("gray", 11),
                    _hover={"color": rx.color("accent", 11)},
                ),
                rx.cond(
                    EventState.has_event,
                    rx.vstack(
                        event_summary_card(EventState.event),
                        session_classification_section(
                            EventState.sessions,
                            EventState.selected_session,
                            EventState.selected_session_label,
                            EventState.select_session,
                            EventState.loading,
                            EventState.error,
                            EventState.classification,
                            EventState.has_classification,
                        ),
                        align="stretch",
                        spacing="4",
                        width="100%",
                    ),
                    rx.cond(
                        EventState.loading,
                        weekend_status_card(
                            "Loading archive event",
                            "Looking up the event schedule and session results…",
                        ),
                        weekend_status_card(
                            "Event unavailable", EventState.error
                        ),
                    ),
                ),
                align="stretch",
                spacing="4",
                width="100%",
                padding_bottom="8",
            ),
        ),
        width="100%",
        align="center",
        min_height="100vh",
        spacing="0",
    )
