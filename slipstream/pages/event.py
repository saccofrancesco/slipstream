"""Archive event detail route and its selected-session classification state."""

import asyncio
from collections.abc import AsyncGenerator
from math import floor
from typing import TypedDict

import reflex as rx
from reflex.event import EventSpec

from slipstream.components import container, loading_card, navbar, status_card
from slipstream.components.classification import session_classification_section
from slipstream.components.laps import (
    DriverChip,
    DriverLine,
    LapChartAxis,
    LapStripCell,
    LapStripRow,
    TyrePointLine,
    laps_section,
)
from slipstream.components.telemetry import (
    CornerMark,
    SectorMark,
    TelemetryLine,
    telemetry_section,
)
from slipstream.components.weekend import event_header
from slipstream.services import (
    DriverClassification,
    EventDetails,
    LapDriver,
    LapPoint,
    SessionLaps,
    SessionTelemetry,
    SessionOption,
    TelemetryCorner,
    TelemetryLap,
    TelemetrySector,
    get_event_details,
    get_session_classification,
    get_session_laps,
    get_session_telemetry,
)

TYRE_ICON_PATHS: dict[str, str] = {
    "SOFT": "/tyres/soft.svg",
    "MEDIUM": "/tyres/medium.svg",
    "HARD": "/tyres/hard.svg",
    "INTERMEDIATE": "/tyres/intermediate.svg",
    "WET": "/tyres/wet.svg",
}


class SelectedLap(TypedDict):
    """A uniquely identified timed lap in the current session's pool."""

    driver: str
    number: int


def _lap_chart_axis(times: list[float]) -> LapChartAxis:
    """Fit axis bounds and distinct labels to the laps plotted on the chart."""
    if not times:
        return {"domain": [0.0, 1.0], "ticks": [], "precision": 0, "width": 64}

    lower, upper = min(times), max(times)
    if lower == upper:
        lower -= 0.5
        upper += 0.5
    else:
        # Keep the endpoint dots clear of the chart's clipping boundary.
        margin = (upper - lower) * 0.025
        lower -= margin
        upper += margin

    # Use fewer ticks only when millisecond labels cannot distinguish five.
    for tick_count in range(5, 1, -1):
        ticks = [
            lower + (upper - lower) * index / (tick_count - 1)
            for index in range(tick_count)
        ]
        for precision in range(4):
            scale = 10**precision
            label_units = [
                floor(tick) if precision == 0 else floor(tick * scale + 0.5)
                for tick in ticks
            ]
            if len(set(label_units)) == tick_count:
                return {
                    "domain": [lower, upper],
                    "ticks": ticks,
                    "precision": precision,
                    "width": 64 if precision == 0 else 72 if precision < 3 else 80,
                }

    return {"domain": [lower, upper], "ticks": [lower, upper], "precision": 3, "width": 80}


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
    selected_laps: list[SelectedLap] = []
    show_outliers: bool = False
    laps_loading: bool = False
    laps_loaded: bool = False
    laps_error: str = ""
    telemetry_rows: list[dict[str, float | int]] = []
    telemetry_laps: list[TelemetryLap] = []
    telemetry_corner_rows: list[TelemetryCorner] = []
    telemetry_sector_rows: list[TelemetrySector] = []
    telemetry_unavailable: list[str] = []
    telemetry_baseline_key: str = ""
    telemetry_distance_metres: int = 0
    telemetry_loaded_for: str = ""
    telemetry_loading: bool = False
    telemetry_error: str = ""

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
    def lap_chart_y_axis(self) -> LapChartAxis:
        """Scale the chart to selected drivers after the outlier switch."""
        selected_codes = set(self.selected_drivers)
        return _lap_chart_axis(
            [
                lap["seconds"]
                for lap in self.visible_lap_points
                if lap["driver"] in selected_codes
            ]
        )

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
    def lap_strip_rows(self) -> list[LapStripRow]:
        """Build selected-driver rows without applying the chart outlier filter."""
        laps_by_driver_and_number: dict[tuple[str, int], LapPoint] = {
            (lap["driver"], lap["number"]): lap for lap in self.lap_points
        }
        fastest_laps: dict[str, LapPoint] = {}
        for lap in self.lap_points:
            current = fastest_laps.get(lap["driver"])
            if current is None or (lap["seconds"], lap["number"]) < (
                current["seconds"],
                current["number"],
            ):
                fastest_laps[lap["driver"]] = lap
        selected_lap_keys: set[tuple[str, int]] = {
            (lap["driver"], lap["number"]) for lap in self.selected_laps
        }
        rows: list[LapStripRow] = []
        for code in self.selected_drivers:
            cells: list[LapStripCell] = []
            for lap_number in self.lap_strip_lap_numbers:
                lap = laps_by_driver_and_number.get((code, lap_number))
                if lap is None:
                    cells.append(
                        {
                            "number": lap_number,
                            "time": "N/A",
                            "tyre_icon": "",
                            "tyre_alt": "No timed lap",
                            "has_lap": False,
                            "fastest": False,
                            "selected": False,
                        }
                    )
                    continue

                compound = lap["compound"].upper()
                tyre_icon = TYRE_ICON_PATHS.get(compound, "")
                cells.append(
                    {
                        "number": lap_number,
                        "time": lap["time"],
                        "tyre_icon": tyre_icon,
                        "tyre_alt": (
                            f"{compound.lower()} tyre"
                            if tyre_icon
                            else "Unknown tyre compound"
                        ),
                        "has_lap": True,
                        "fastest": lap_number == fastest_laps[code]["number"],
                        "selected": (code, lap_number) in selected_lap_keys,
                    }
                )
            rows.append({"code": code, "cells": cells})
        return rows

    @rx.var
    def selected_driver_count(self) -> int:
        """Return how many drivers are currently plotted."""
        return len(self.selected_drivers)

    @rx.var
    def selected_lap_count(self) -> int:
        """Return the number of unique laps in the telemetry pool."""
        return len(self.selected_laps)

    @rx.var
    def telemetry_lines(self) -> list[TelemetryLine]:
        """Match the Laps chart's team colors and distinguish repeat laps."""
        driver_by_code = {driver["code"]: driver for driver in self.lap_drivers}
        active_chip_colors = {
            chip["code"]: chip["plot_color"]
            for chip in self.driver_chips
            if chip["selected"]
        }
        first_selected_by_team: dict[str, str] = {}
        for code in self.selected_drivers:
            driver = driver_by_code.get(code)
            if driver is not None:
                first_selected_by_team.setdefault(driver["team"] or code, code)

        first_plotted_by_team: set[str] = set()
        color_by_driver: dict[str, str] = {}
        repeats_by_driver: dict[str, int] = {}
        dash_styles = ("", "7 4", "2 4", "10 3 2 3")
        lines: list[TelemetryLine] = []
        for lap in self.telemetry_laps:
            driver = str(lap["driver"])
            key = str(lap["key"])
            metadata = driver_by_code.get(driver)
            team = (metadata["team"] or driver) if metadata else driver
            if driver not in color_by_driver:
                team_color = metadata["team_color"] if metadata else "#FFFFFF"
                if driver in active_chip_colors:
                    color = active_chip_colors[driver]
                elif team in first_selected_by_team:
                    color = "#FFFFFF"
                elif team in first_plotted_by_team:
                    color = "#FFFFFF"
                else:
                    color = team_color
                first_plotted_by_team.add(team)
                color_by_driver[driver] = color
            color = color_by_driver[driver]
            repeat = repeats_by_driver.get(driver, 0)
            repeats_by_driver[driver] = repeat + 1
            seconds = float(lap["seconds"])
            minutes = int(seconds // 60)
            lines.append(
                {
                    "key": key,
                    "label": f"{driver} - Lap {lap['number']}",
                    "time": f"{minutes}:{seconds - minutes * 60:06.3f}",
                    "color": color,
                    "dash": dash_styles[repeat % len(dash_styles)],
                    "baseline": key == self.telemetry_baseline_key,
                    "speed_key": f"speed_{key}",
                    "delta_key": f"delta_{key}",
                    "throttle_key": f"throttle_{key}",
                    "brake_key": f"brake_{key}",
                    "rpm_key": f"rpm_{key}",
                    "gear_key": f"gear_{key}",
                }
            )
        return lines

    @rx.var
    def telemetry_corners(self) -> list[CornerMark]:
        """Return projected corner positions for labels inside each chart."""
        return [
            {
                "label": str(corner["label"]),
                "distance": int(corner["distance"]),
            }
            for corner in self.telemetry_corner_rows
        ]

    @rx.var
    def telemetry_sectors(self) -> list[SectorMark]:
        """Return projected sector boundaries for each synchronized chart."""
        return [
            {"label": str(sector["label"]), "distance": int(sector["distance"])}
            for sector in self.telemetry_sector_rows
        ]

    def _telemetry_selection_key(self) -> str:
        """Identify the session and exact selected lap pool for stale-load checks."""
        laps = ",".join(f"{lap['driver']}:{lap['number']}" for lap in self.selected_laps)
        return f"{self.event_season}:{self.round_number}:{self.selected_session}:{laps}"

    def _clear_telemetry(self) -> None:
        """Drop chart data when the selected session or laps change."""
        self.telemetry_rows = []
        self.telemetry_laps = []
        self.telemetry_corner_rows = []
        self.telemetry_sector_rows = []
        self.telemetry_unavailable = []
        self.telemetry_baseline_key = ""
        self.telemetry_distance_metres = 0
        self.telemetry_loaded_for = ""
        self.telemetry_loading = False
        self.telemetry_error = ""

    @rx.event
    async def change_tab(self, tab: str) -> AsyncGenerator[EventSpec | None, None]:
        """Load lap or telemetry data when its tab becomes active."""
        self.active_tab = tab
        if tab == "laps" and self.event and not self.laps_loaded and not self.laps_loading:
            async for update in self._load_laps(self.selected_session):
                yield update
        if (
            tab == "telemetry"
            and self.selected_laps
            and self.telemetry_loaded_for != self._telemetry_selection_key()
            and not self.telemetry_loading
        ):
            async for update in self._load_telemetry():
                yield update

    async def _load_telemetry(self) -> AsyncGenerator[EventSpec | None, None]:
        """Fetch the current lap pool without blocking tab interaction."""
        request_key = self._telemetry_selection_key()
        requested_laps = [
            (lap["driver"], lap["number"]) for lap in self.selected_laps
        ]
        self.telemetry_loading = True
        self.telemetry_error = ""
        yield
        try:
            data: SessionTelemetry = await asyncio.to_thread(
                get_session_telemetry,
                self.event_season,
                self.round_number,
                self.selected_session,
                requested_laps,
            )
        except Exception:
            if self._telemetry_selection_key() == request_key:
                self.telemetry_error = (
                    "Could not load the selected laps' telemetry. Please try again."
                )
                self.telemetry_loading = False
            return
        if self._telemetry_selection_key() != request_key:
            return
        self.telemetry_rows = data["rows"]
        self.telemetry_laps = data["laps"]
        self.telemetry_corner_rows = data["corners"]
        self.telemetry_sector_rows = data["sectors"]
        self.telemetry_unavailable = data["unavailable"]
        self.telemetry_baseline_key = data["baseline_key"]
        self.telemetry_distance_metres = data["distance_metres"]
        self.telemetry_loaded_for = request_key
        self.telemetry_loading = False
        if self.telemetry_unavailable and self.telemetry_laps:
            yield rx.toast(
                "No usable telemetry for: " + ", ".join(self.telemetry_unavailable),
                duration=7000,
            )

    @rx.event
    async def retry_telemetry(self) -> AsyncGenerator[EventSpec | None, None]:
        """Retry the current lap pool after a telemetry load failure."""
        if not self.selected_laps or self.telemetry_loading:
            return
        self._clear_telemetry()
        async for update in self._load_telemetry():
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
    def toggle_lap(self, code: str, number: int) -> EventSpec | None:
        """Toggle a timed lap in the current session's telemetry pool."""
        if not any(
            lap["driver"] == code and lap["number"] == number
            for lap in self.lap_points
        ):
            return None

        if any(
            lap["driver"] == code and lap["number"] == number
            for lap in self.selected_laps
        ):
            self.selected_laps = [
                lap
                for lap in self.selected_laps
                if lap["driver"] != code or lap["number"] != number
            ]
            self._clear_telemetry()
            return None

        self.selected_laps = [*self.selected_laps, {"driver": code, "number": number}]
        self._clear_telemetry()
        return rx.toast(
            f"Lap {number} ({code}) added",
            action={
                "label": "View Telemetry",
                "on_click": EventState.change_tab("telemetry"),
            },
            style={
                "background": "var(--gray-2)",
                "color": "var(--gray-12)",
                "border": "1px solid var(--gray-6)",
                "border_radius": "0.75rem",
                "box_shadow": "0 8px 24px rgba(0, 0, 0, 0.16)",
            },
        )

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
        self.selected_laps = []
        self.show_outliers = False
        self.laps_loading = False
        self.laps_loaded = False
        self.laps_error = ""
        self._clear_telemetry()
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

        if session_code != self.selected_session:
            self.selected_laps = []
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
        self._clear_telemetry()
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
                                    rx.hstack(
                                        rx.text("Telemetry"),
                                        rx.cond(
                                            EventState.selected_lap_count > 0,
                                            rx.badge(
                                                EventState.selected_lap_count,
                                                color_scheme="gray",
                                                variant="soft",
                                                color=rx.color("accent", 11),
                                                radius="full",
                                            ),
                                        ),
                                        align="center",
                                        spacing="2",
                                    ),
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
                                        EventState.lap_chart_y_axis,
                                        EventState.driver_lines,
                                        EventState.tyre_point_lines,
                                        EventState.lap_strip_lap_numbers,
                                        EventState.lap_strip_rows,
                                        EventState.selected_driver_count,
                                        EventState.toggle_lap,
                                        EventState.show_outliers,
                                        EventState.set_show_outliers,
                                        EventState.laps_loading,
                                        EventState.laps_loaded,
                                        EventState.laps_error,
                                    ),
                                    value="laps",
                                    width="100%",
                                ),
                                rx.tabs.content(
                                    telemetry_section(
                                        EventState.telemetry_rows,
                                        EventState.telemetry_lines,
                                        EventState.telemetry_corners,
                                        EventState.telemetry_sectors,
                                        EventState.telemetry_unavailable,
                                        EventState.selected_lap_count,
                                        EventState.telemetry_loading,
                                        EventState.telemetry_error,
                                        EventState.change_tab("laps"),
                                        EventState.retry_telemetry,
                                    ),
                                    value="telemetry",
                                    width="100%",
                                ),
                                width="100%",
                                padding_top="1rem",
                            ),
                            value=EventState.active_tab,
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
