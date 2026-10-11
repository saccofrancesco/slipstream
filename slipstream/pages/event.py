"""Archive event detail route and its selected-session classification state."""

import asyncio
import logging
from datetime import date

import reflex as rx

from slipstream.components import container, loading_card, navbar, status_card
from slipstream.components.classification import session_classification_section
from slipstream.components.laps import (
    DriverChip,
    DriverLine,
    TyrePointLine,
    laps_section,
)
from slipstream.components.weekend import event_header
from slipstream.services import (
    DriverClassification,
    EventDetails,
    LapDriver,
    LapPoint,
    SessionLaps,
    SessionOption,
    call_data_source,
    get_event_details,
    get_session_classification,
    get_session_laps,
)

logger = logging.getLogger(__name__)


class EventState(rx.State):
    """Hold event details, classification, and lap data for one session."""

    event_season: str = ""
    round_number: str = ""
    event: dict[str, str] = {}
    sessions: list[SessionOption] = []
    selected_session: str = "R"
    classification: list[DriverClassification] = []
    loading: bool = True
    error: str = ""
    active_tab: str = "session"
    lap_drivers: list[LapDriver] = []
    lap_points: list[LapPoint] = []
    selected_drivers: list[str] = []
    show_outliers: bool = False
    laps_loading: bool = False
    laps_loaded: bool = False
    laps_error: str = ""
    load_id: int = 0

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

    @rx.var
    def driver_chips(self) -> list[DriverChip]:
        """Mark selections and use white for a selected teammate's line."""
        first_by_team: dict[str, str] = {}
        for code in self.selected_drivers:
            driver = next((item for item in self.lap_drivers if item["code"] == code), None)
            if driver is not None:
                first_by_team.setdefault(driver["team"] or code, code)
        team_order: list[str] = []
        drivers_by_team: dict[str, list[LapDriver]] = {}
        for driver in self.lap_drivers:
            team = driver["team"] or driver["code"]
            if team not in drivers_by_team:
                team_order.append(team)
                drivers_by_team[team] = []
            drivers_by_team[team].append(driver)

        chips: list[DriverChip] = []
        for team in team_order:
            for driver in drivers_by_team[team]:
                team_color = driver["team_color"]
                chips.append(
                    {
                        **driver,
                        "selected": driver["code"] in self.selected_drivers,
                        "plot_color": (
                            team_color
                            if first_by_team.get(team) == driver["code"]
                            else "#FFFFFF"
                        ),
                        "selected_fill": (
                            f"color-mix(in srgb, {team_color} 22%, transparent)"
                        ),
                    }
                )
        return chips

    @rx.var
    def visible_lap_points(self) -> list[LapPoint]:
        """Apply the outlier switch before building chart lines and markers."""
        return [
            lap
            for lap in self.lap_points
            if self.show_outliers or not lap["outlier"]
        ]

    @rx.var
    def driver_lines(self) -> list[DriverLine]:
        """Describe selected drivers that have visible laps for this chart."""
        visible_codes = {lap["driver"] for lap in self.visible_lap_points}
        return [
            {"code": chip["code"], "color": chip["plot_color"]}
            for chip in self.driver_chips
            if chip["selected"] and chip["code"] in visible_codes
        ]

    @rx.var
    def tyre_point_lines(self) -> list[TyrePointLine]:
        """Create filled known-tyre markers and hollow unknown-tyre markers."""
        series: list[TyrePointLine] = []
        for driver in self.driver_lines:
            compounds: dict[str, str] = {
                lap["compound"]: lap["compound_color"]
                for lap in self.visible_lap_points
                if lap["driver"] == driver["code"]
            }
            for compound, compound_color in sorted(compounds.items()):
                series.append(
                    {
                        "key": f"marker_{driver['code']}_{compound}",
                        "code": driver["code"],
                        # Match the plot background so the line does not show
                        # through an unknown-tyre marker's hollow center.
                        "color": (
                            compound_color
                            if compound
                            in {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"}
                            else "var(--gray-1)"
                        ),
                        "line_color": driver["color"],
                    }
                )
        return series

    @rx.var
    def lap_chart_data(self) -> list[dict[str, float | int | None]]:
        """Align selected drivers and tyre markers by the shared lap number."""
        if not self.driver_lines:
            return []
        markers_by_driver: dict[str, list[TyrePointLine]] = {}
        for marker in self.tyre_point_lines:
            markers_by_driver.setdefault(marker["code"], []).append(marker)

        chart_rows: dict[int, dict[str, float | int | None]] = {}
        for lap in self.visible_lap_points:
            if lap["driver"] not in markers_by_driver:
                continue
            row = chart_rows.setdefault(lap["number"], {"lap_number": lap["number"]})
            for driver in self.driver_lines:
                row.setdefault(driver["code"], None)
                for marker in markers_by_driver[driver["code"]]:
                    row.setdefault(marker["key"], None)
            row[lap["driver"]] = lap["seconds"]
            row[f"marker_{lap['driver']}_{lap['compound']}"] = lap["seconds"]

        return [chart_rows[number] for number in sorted(chart_rows)]

    @rx.var
    def selected_driver_count(self) -> int:
        """Return how many drivers are currently plotted."""
        return len(self.selected_drivers)

    @rx.event(background=True)
    async def change_tab(self, tab: str) -> None:
        """Load laps without holding the state lock after opening the tab."""
        async with self:
            self.active_tab = tab
            if tab != "laps" or not self.event or self.laps_loaded or self.laps_loading:
                return
            self.laps_loading = True
            load_id = self.load_id
            season, round_number = self.event_season, self.round_number
            session_code = self.selected_session
            completed = self._session_completed(session_code)
            fresh = self._event_is_current()
        await self._fetch_laps(load_id, season, round_number, session_code, completed, fresh)

    @rx.event
    def toggle_driver(self, code: str) -> None:
        """Add or remove a selectable driver from the lap chart."""
        if not any(driver["code"] == code for driver in self.lap_drivers):
            return
        if code in self.selected_drivers:
            self.selected_drivers = [item for item in self.selected_drivers if item != code]
        else:
            self.selected_drivers = [*self.selected_drivers, code]

    @rx.event
    def set_show_outliers(self, value: bool) -> None:
        """Include or hide flagged laps in the chart."""
        self.show_outliers = value

    def _session_completed(self, session_code: str) -> bool:
        """Read the selected session's published completion flag."""
        return any(
            session["code"] == session_code and session["completed"]
            for session in self.sessions
        )

    def _event_is_current(self) -> bool:
        """Keep the ongoing weekend fresh instead of using archived timing."""
        return self.event.get("race_date_iso", "") >= date.today().isoformat()

    @rx.event(background=True)
    async def load_event(self) -> None:
        """Load route metadata, then the selected session's classification."""
        async with self:
            params: dict[str, str] = self.router.page.params
            season = params.get("season", "")
            round_number = params.get("round", "")
            requested_session = self.router.url.query_parameters.get("session", "R")
            self.load_id += 1
            load_id = self.load_id
            self.event_season = season
            self.round_number = round_number
            self.event = {}
            self.sessions = []
            self.selected_session = "R"
            self.classification = []
            self.error = ""
            self.loading = True
            self.active_tab = "session"
            self.lap_drivers = []
            self.lap_points = []
            self.selected_drivers = []
            self.show_outliers = False
            self.laps_loading = False
            self.laps_loaded = False
            self.laps_error = ""

        try:
            details: EventDetails | None = await asyncio.to_thread(
                call_data_source, get_event_details, season, round_number, fresh=True
            )
        except Exception:
            logger.exception("Could not load event details for %s/%s", season, round_number)
            async with self:
                if self.load_id == load_id:
                    self.error = "Could not load this archive event. Please try again."
                    self.loading = False
            return

        async with self:
            if self.load_id != load_id:
                return
            if details is None:
                self.error = "The requested archive event could not be found."
                self.loading = False
                return
            self.event = {
                key: value for key, value in details.items() if key != "sessions"
            }
            self.sessions = details["sessions"]
            if any(session["code"] == requested_session for session in self.sessions):
                self.selected_session = requested_session
            session_code = self.selected_session
            completed = self._session_completed(session_code)
            fresh = self._event_is_current()
        await self._fetch_classification(
            load_id, season, round_number, session_code, completed, fresh
        )

    @rx.event(background=True)
    async def select_session(self, session_code: str) -> None:
        """Load a selection and ignore any previous in-flight response."""
        async with self:
            if not self.event or not any(
                session["code"] == session_code for session in self.sessions
            ):
                return
            self.load_id += 1
            load_id = self.load_id
            self.selected_session = session_code
            self.classification = []
            self.error = ""
            self.loading = True
            self.lap_drivers = []
            self.lap_points = []
            self.selected_drivers = []
            self.laps_loading = self.active_tab == "laps"
            self.laps_loaded = False
            self.laps_error = ""
            load_laps = self.active_tab == "laps"
            season, round_number = self.event_season, self.round_number
            completed = self._session_completed(session_code)
            fresh = self._event_is_current()
        requests = [
            self._fetch_classification(
                load_id, season, round_number, session_code, completed, fresh
            )
        ]
        if load_laps:
            requests.append(
                self._fetch_laps(
                    load_id, season, round_number, session_code, completed, fresh
                )
            )
        await asyncio.gather(*requests)

    async def _fetch_classification(
        self, load_id: int, season: str, round_number: str,
        session_code: str, completed: bool, fresh: bool,
    ) -> None:
        """Fetch classification outside the lock and apply it if still selected."""
        try:
            rows: list[DriverClassification] = await asyncio.to_thread(
                call_data_source,
                get_session_classification,
                season,
                round_number,
                session_code,
                completed,
                fresh=fresh,
            )
        except Exception:
            logger.exception("Could not load classification for %s/%s/%s", season, round_number, session_code)
            async with self:
                if self.load_id == load_id and self.selected_session == session_code:
                    self.classification = []
                    self.error = "Could not load this session's classification. Please try again."
                    self.loading = False
            return
        async with self:
            if self.load_id == load_id and self.selected_session == session_code:
                self.classification = rows
                self.error = ""
                self.loading = False

    async def _fetch_laps(
        self, load_id: int, season: str, round_number: str,
        session_code: str, completed: bool, fresh: bool,
    ) -> None:
        """Fetch timed laps outside the lock and apply them if still selected."""
        try:
            data: SessionLaps = await asyncio.to_thread(
                call_data_source,
                get_session_laps,
                season,
                round_number,
                session_code,
                completed,
                fresh=fresh,
            )
        except Exception:
            logger.exception("Could not load laps for %s/%s/%s", season, round_number, session_code)
            async with self:
                if self.load_id == load_id and self.selected_session == session_code:
                    self.lap_drivers = []
                    self.lap_points = []
                    self.laps_error = "Could not load this session's lap times. Please try again."
                    self.laps_loading = False
            return
        async with self:
            if self.load_id == load_id and self.selected_session == session_code:
                self.lap_drivers = data["drivers"]
                self.lap_points = data["laps"]
                self.laps_loaded = bool(data["laps"])
                self.laps_error = ""
                self.laps_loading = False

    @rx.event(background=True)
    async def retry_classification(self) -> None:
        """Retry the selected classification after a temporary failure."""
        async with self:
            if not self.event:
                return
            self.error = ""
            self.loading = True
            load_id = self.load_id
            season, round_number = self.event_season, self.round_number
            session_code = self.selected_session
            completed = self._session_completed(session_code)
            fresh = self._event_is_current()
        await self._fetch_classification(
            load_id, season, round_number, session_code, completed, fresh
        )

    @rx.event(background=True)
    async def retry_laps(self) -> None:
        """Retry the selected session's laps after a temporary failure."""
        async with self:
            if not self.event:
                return
            self.laps_error = ""
            self.laps_loading = True
            load_id = self.load_id
            season, round_number = self.event_season, self.round_number
            session_code = self.selected_session
            completed = self._session_completed(session_code)
            fresh = self._event_is_current()
        await self._fetch_laps(
            load_id, season, round_number, session_code, completed, fresh
        )


@rx.page("/results/[season]/[round]", "Grand Prix results", on_load=EventState.load_event)
def event_results() -> rx.Component:
    """Render one archived event and the selected session classification."""
    return rx.vstack(
        navbar(active_section="results"),
        container(
            rx.vstack(
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
                    padding_top="7",
                ),
                rx.cond(
                    EventState.has_event,
                    rx.vstack(
                        event_header(EventState.event),
                        rx.tabs.root(
                            rx.tabs.list(
                                rx.tabs.trigger(
                                    "Session",
                                    value="session",
                                    flex_grow="1",
                                    flex_basis="0",
                                ),
                                rx.tabs.trigger(
                                    "Laps",
                                    value="laps",
                                    flex_grow="1",
                                    flex_basis="0",
                                ),
                                rx.tabs.trigger(
                                    "Telemetry",
                                    value="telemetry",
                                    flex_grow="1",
                                    flex_basis="0",
                                ),
                                width="100%",
                            ),
                            rx.box(
                                rx.tabs.content(
                                    session_classification_section(
                                        EventState.sessions,
                                        EventState.selected_session,
                                        EventState.selected_session_label,
                                        EventState.select_session,
                                        EventState.loading,
                                        EventState.error,
                                        EventState.classification,
                                        EventState.has_classification,
                                        EventState.retry_classification,
                                    ),
                                    value="session",
                                    width="100%",
                                ),
                                rx.tabs.content(
                                    laps_section(
                                        EventState.selected_session_label,
                                        EventState.driver_chips,
                                        EventState.toggle_driver,
                                        EventState.lap_chart_data,
                                        EventState.driver_lines,
                                        EventState.tyre_point_lines,
                                        EventState.selected_driver_count,
                                        EventState.show_outliers,
                                        EventState.set_show_outliers,
                                        EventState.laps_loading,
                                        EventState.laps_loaded,
                                        EventState.laps_error,
                                        EventState.retry_laps,
                                    ),
                                    value="laps",
                                    width="100%",
                                ),
                                rx.tabs.content(value="telemetry"),
                                width="100%",
                                padding_top="1rem",
                            ),
                            default_value="session",
                            on_change=EventState.change_tab,
                            width="100%",
                        ),
                        align="stretch",
                        spacing="4",
                        width="100%",
                    ),
                    rx.cond(
                        EventState.loading,
                        loading_card(
                            "Looking up the event schedule and session results…"
                        ),
                        rx.vstack(
                            status_card("Event unavailable", EventState.error),
                            rx.button(
                                "Retry event", on_click=EventState.load_event,
                                variant="soft",
                            ),
                            align="start",
                            spacing="2",
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
