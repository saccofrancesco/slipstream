"""Archive event detail route and its selected-session classification state."""

import asyncio
from collections.abc import AsyncGenerator

import reflex as rx

from slipstream.components import container, loading_card, navbar, status_card
from slipstream.components.classification import session_classification_section
from slipstream.components.laps import (
    DriverChip,
    DriverLine,
    LapStripCell,
    LapStripRow,
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
    get_event_details,
    get_session_classification,
    get_session_laps,
)

TYRE_ICON_PATHS: dict[str, str] = {
    "SOFT": "/tyres/soft.svg",
    "MEDIUM": "/tyres/medium.svg",
    "HARD": "/tyres/hard.svg",
    "INTERMEDIATE": "/tyres/intermediate.svg",
    "WET": "/tyres/wet.svg",
}


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
    def lap_strip_lap_numbers(self) -> list[int]:
        """Return every lap number present in the loaded session."""
        highest_lap = max(
            (lap["number"] for lap in self.lap_points),
            default=0,
        )
        return list(range(1, highest_lap + 1))

    @rx.var
    def lap_strip_grid_columns(self) -> str:
        """Keep the driver label and lap cells aligned across strip rows."""
        lap_count = len(self.lap_strip_lap_numbers)
        if not lap_count:
            return "5rem"
        return f"5rem repeat({lap_count}, minmax(10rem, 1fr))"

    @rx.var
    def lap_strip_rows(self) -> list[LapStripRow]:
        """Build selected-driver rows without applying the chart outlier filter."""
        laps_by_driver_and_number: dict[tuple[str, int], LapPoint] = {
            (lap["driver"], lap["number"]): lap for lap in self.lap_points
        }
        rows: list[LapStripRow] = []
        for code in self.selected_drivers:
            cells: list[LapStripCell] = []
            for lap_number in self.lap_strip_lap_numbers:
                lap = laps_by_driver_and_number.get((code, lap_number))
                if lap is None:
                    cells.append(
                        {
                            "time": "N/A",
                            "tyre_icon": "",
                            "tyre_alt": "No timed lap",
                            "has_lap": False,
                        }
                    )
                    continue

                compound = lap["compound"].upper()
                tyre_icon = TYRE_ICON_PATHS.get(compound, "")
                cells.append(
                    {
                        "time": lap["time"],
                        "tyre_icon": tyre_icon,
                        "tyre_alt": (
                            f"{compound.lower()} tyre"
                            if tyre_icon
                            else "Unknown tyre compound"
                        ),
                        "has_lap": True,
                    }
                )
            rows.append({"code": code, "cells": cells})
        return rows

    @rx.var
    def selected_driver_count(self) -> int:
        """Return how many drivers are currently plotted."""
        return len(self.selected_drivers)

    @rx.event
    async def change_tab(self, tab: str) -> AsyncGenerator[None, None]:
        """Load the selected session's laps the first time its tab opens."""
        self.active_tab = tab
        if tab == "laps" and self.event and not self.laps_loaded and not self.laps_loading:
            async for update in self._load_laps(self.selected_session):
                yield update

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
        self.active_tab = "session"
        self.lap_drivers = []
        self.lap_points = []
        self.selected_drivers = []
        self.show_outliers = False
        self.laps_loading = False
        self.laps_loaded = False
        self.laps_error = ""
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
        requested_session: str = self.router.url.query_parameters.get("session", "R")
        if any(session["code"] == requested_session for session in self.sessions):
            self.selected_session = requested_session
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
        self.lap_drivers = []
        self.lap_points = []
        self.selected_drivers = []
        self.laps_loading = self.active_tab == "laps"
        self.laps_loaded = False
        self.laps_error = ""
        yield

        await self._load_classification(session_code)
        self.loading = False
        if self.active_tab == "laps":
            async for update in self._load_laps(session_code):
                yield update

    async def _load_laps(self, session_code: str) -> AsyncGenerator[None, None]:
        """Fetch the selected session's timed laps without blocking the UI."""
        self.laps_loading = True
        self.laps_error = ""
        yield
        try:
            data: SessionLaps = await asyncio.to_thread(
                get_session_laps,
                self.event_season,
                self.round_number,
                session_code,
            )
        except Exception:
            if self.selected_session != session_code:
                return
            self.lap_drivers = []
            self.lap_points = []
            self.laps_error = "Could not load this session's lap times. Please try again."
        else:
            if self.selected_session != session_code:
                return
            self.lap_drivers = data["drivers"]
            self.lap_points = data["laps"]
            self.laps_loaded = bool(data["laps"])
        self.laps_loading = False

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
                                        EventState.lap_strip_lap_numbers,
                                        EventState.lap_strip_grid_columns,
                                        EventState.lap_strip_rows,
                                        EventState.selected_driver_count,
                                        EventState.show_outliers,
                                        EventState.set_show_outliers,
                                        EventState.laps_loading,
                                        EventState.laps_loaded,
                                        EventState.laps_error,
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
                        status_card(
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
