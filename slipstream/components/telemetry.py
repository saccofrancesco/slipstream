"""Six synchronized distance charts for selected FastF1 laps."""

from typing import TypedDict

import reflex as rx

from .layout import loading_card, status_card

CHART_MARGIN: dict[str, int] = {"top": 10, "right": 20, "left": 0, "bottom": 4}
CHART_MIN_WIDTH: str = "900px"


class TelemetryLine(TypedDict):
    """Presentation details shared by one lap's six series."""

    key: str
    label: str
    time: str
    color: str
    dash: str
    baseline: bool
    speed_key: str
    delta_key: str
    throttle_key: str
    brake_key: str
    rpm_key: str
    gear_key: str


class CornerMark(TypedDict):
    """Circuit corner and its position below the shared distance axis."""

    label: str
    distance: int
    lane: int
    left: str


def _formatter(metric: str) -> rx.Var:
    """Keep each chart's tooltip values compact and unit-aware."""
    expressions = {
        "speed": '(value) => `${Math.round(value)} km/h`',
        "delta": '(value) => `${value >= 0 ? "+" : ""}${Number(value).toFixed(3)} s`',
        "throttle": '(value) => `${Math.round(value)}%`',
        "brake": '(value) => value ? "On" : "Off"',
        "rpm": '(value) => `${Math.round(value).toLocaleString()} RPM`',
        "gear": '(value) => `Gear ${Math.round(value)}`',
    }
    return rx.Var(_js_expr=expressions[metric])


def _chart_line(line: rx.Var[TelemetryLine], metric: str) -> rx.Component:
    """Render the same lap color and dash pattern in every channel."""
    return rx.recharts.line(
        data_key=line[f"{metric}_key"],
        name=line["label"],
        type_="stepAfter" if metric in {"brake", "gear"} else "linear",
        stroke=line["color"],
        stroke_width=rx.cond(line["baseline"], 2.6, 2),
        stroke_dasharray=line["dash"],
        dot=False,
        active_dot=False,
        is_animation_active=False,
    )


def _corner_line(corner: rx.Var[CornerMark]) -> rx.Component:
    """Show a quiet vertical guide at the corner's real distance."""
    return rx.recharts.reference_line(
        x=corner["distance"],
        stroke=rx.color("gray", 7),
        stroke_width=1,
        stroke_dasharray="2 5",
        if_overflow="hidden",
    )


def _telemetry_chart(
    metric: str,
    title: str,
    unit: str,
    rows: rx.Var[list[dict[str, float | int]]],
    lines: rx.Var[list[TelemetryLine]],
    corners: rx.Var[list[CornerMark]],
    last: bool = False,
) -> rx.Component:
    """Build one channel with the same x axis and synchronized cursor."""
    axis_props: dict[str, object] = {"domain": ["dataMin", "dataMax"]}
    if metric == "throttle":
        axis_props = {"domain": [0, 100], "ticks": [0, 50, 100]}
    elif metric == "brake":
        axis_props = {"domain": [0, 1], "ticks": [0, 1]}
    elif metric == "gear":
        axis_props = {"domain": [0, 8], "ticks": [0, 2, 4, 6, 8]}
    axis_formatter = (
        '(value) => value ? "On" : "Off"'
        if metric == "brake"
        else '(value) => `${value > 0 ? "+" : ""}${Number(value).toFixed(3)}`'
        if metric == "delta"
        else '(value) => `${Math.round(value)}`'
    )
    return rx.vstack(
        rx.hstack(
            rx.text(title, weight="bold", size="2"),
            rx.text(unit, size="1", color=rx.color("gray", 10)),
            spacing="2",
            align="baseline",
        ),
        rx.recharts.line_chart(
            rx.recharts.cartesian_grid(
                stroke=rx.color("gray", 5), stroke_dasharray="3 5", vertical=False
            ),
            rx.recharts.x_axis(
                data_key="distance",
                type_="number",
                domain=["dataMin", "dataMax"],
                allow_data_overflow=True,
                hide=not last,
                axis_line=False,
                tick_line=False,
                tick_count=7,
                height=40,
                tick_formatter='(value) => `${(value / 1000).toFixed(1)}`',
                stroke=rx.color("gray", 10),
            ),
            rx.recharts.y_axis(
                type_="number",
                width=68,
                tick_count=5,
                padding={"top": 8, "bottom": 8},
                allow_decimals=metric == "delta",
                allow_data_overflow=True,
                axis_line=False,
                tick_line=False,
                stroke=rx.color("gray", 10),
                tick_formatter=axis_formatter,
                **axis_props,
            ),
            rx.foreach(corners, _corner_line),
            rx.cond(
                metric == "delta",
                rx.recharts.reference_line(y=0, stroke=rx.color("gray", 9)),
            ),
            rx.recharts.graphing_tooltip(
                cursor={
                    "stroke": "rgba(255,255,255,0.65)",
                    "strokeWidth": 1,
                    "strokeDasharray": "4 4",
                },
                filter_null=True,
                is_animation_active=False,
                wrapper_style={"outline": "none", "zIndex": 10},
                content_style={
                    "backgroundColor": "var(--gray-2)",
                    "border": "1px solid var(--gray-6)",
                    "borderRadius": "10px",
                    "padding": "8px 10px",
                },
                item_style={
                    "color": "var(--gray-12)",
                    "fontVariantNumeric": "tabular-nums",
                },
                label_style={"color": "var(--gray-11)", "fontWeight": 700},
                custom_attrs={
                    "formatter": _formatter(metric),
                    "labelFormatter": rx.Var(
                        _js_expr='(value) => `${Math.round(value)} m`'
                    ),
                },
            ),
            rx.foreach(lines, lambda line: _chart_line(line, metric)),
            data=rows,
            sync_id="selected-lap-telemetry",
            sync_method="index",
            width="100%",
            height=210 if last else 180,
            margin=CHART_MARGIN,
        ),
        width="100%",
        align="stretch",
        spacing="1",
    )


def _corner_label(corner: rx.Var[CornerMark]) -> rx.Component:
    """Place a staggered corner tag under its distance guide."""
    return rx.text(
        corner["label"],
        position="absolute",
        left=corner["left"],
        top=rx.cond(
            corner["lane"] == 0,
            "0px",
            rx.cond(corner["lane"] == 1, "19px", "38px"),
        ),
        transform="translateX(-50%)",
        color=rx.color("gray", 11),
        font_size="11px",
        font_weight="600",
        white_space="nowrap",
        font_variant_numeric="tabular-nums",
    )


def _legend_item(line: rx.Var[TelemetryLine]) -> rx.Component:
    """Identify each lap and its shared chart color."""
    return rx.hstack(
        rx.box(
            width="20px",
            border_top="3px solid",
            border_color=line["color"],
            border_style=rx.cond(line["dash"] == "", "solid", "dashed"),
        ),
        rx.text(line["label"], size="2", weight="medium"),
        rx.text(
            line["time"],
            size="2",
            color=rx.color("gray", 10),
            font_variant_numeric="tabular-nums",
        ),
        rx.cond(line["baseline"], rx.badge("Baseline", size="1", variant="soft")),
        spacing="2",
        align="center",
    )


def telemetry_section(
    session_label: rx.Var[str],
    rows: rx.Var[list[dict[str, float | int]]],
    lines: rx.Var[list[TelemetryLine]],
    corners: rx.Var[list[CornerMark]],
    unavailable: rx.Var[list[str]],
    selected_count: rx.Var[int],
    loading: rx.Var[bool],
    error: rx.Var[str],
    on_open_laps: rx.EventHandler,
    on_retry: rx.EventHandler,
) -> rx.Component:
    """Render the selection state and six aligned telemetry channels."""
    return rx.vstack(
        rx.vstack(
            rx.text(
                "TELEMETRY COMPARISON",
                size="2",
                weight="bold",
                color=rx.color("accent", 11),
                letter_spacing="0.14em",
            ),
            rx.heading(session_label, as_="h2", size="5", weight="bold"),
            align="start",
            spacing="1",
        ),
        rx.cond(
            selected_count == 0,
            rx.vstack(
                status_card(
                    "No laps selected",
                    "Select lap times in the Laps table to compare telemetry.",
                ),
                rx.button("Choose laps", on_click=on_open_laps, variant="soft"),
                width="100%",
                align="start",
            ),
            rx.cond(
                loading,
                loading_card("Loading selected laps' telemetry…"),
                rx.cond(
                    error != "",
                    rx.vstack(
                        status_card("Telemetry unavailable", error),
                        rx.button("Try again", on_click=on_retry, variant="soft"),
                        width="100%",
                        align="start",
                    ),
                    rx.cond(
                        lines.length() == 0,
                        rx.vstack(
                            status_card(
                                "Telemetry unavailable",
                                "The selected laps have no usable car telemetry.",
                            ),
                            rx.text(
                                "Unavailable: ",
                                unavailable.join(", "),
                                size="2",
                                color=rx.color("gray", 11),
                            ),
                            width="100%",
                            align="start",
                        ),
                        rx.vstack(
                            rx.flex(
                                rx.foreach(lines, _legend_item),
                                gap="0.75rem 1.5rem",
                                flex_wrap="wrap",
                                align="center",
                                width="100%",
                            ),
                            rx.cond(
                                unavailable.length() > 0,
                                rx.callout(
                                    rx.hstack(
                                        rx.text("No usable telemetry for:"),
                                        rx.text(unavailable.join(", "), weight="bold"),
                                        spacing="1",
                                        flex_wrap="wrap",
                                    ),
                                    icon="triangle-alert",
                                    color_scheme="amber",
                                    width="100%",
                                ),
                            ),
                            rx.box(
                                rx.vstack(
                                    _telemetry_chart(
                                        "speed", "SPEED", "km/h", rows, lines, corners
                                    ),
                                    _telemetry_chart(
                                        "delta", "LAP DELTA", "seconds", rows, lines, corners
                                    ),
                                    _telemetry_chart(
                                        "throttle", "THROTTLE", "%", rows, lines, corners
                                    ),
                                    _telemetry_chart(
                                        "brake", "BRAKE", "on / off", rows, lines, corners
                                    ),
                                    _telemetry_chart(
                                        "rpm", "RPM", "rev/min", rows, lines, corners
                                    ),
                                    _telemetry_chart(
                                        "gear", "GEAR", "", rows, lines, corners, last=True
                                    ),
                                    rx.cond(
                                        corners.length() > 0,
                                        rx.box(
                                            rx.foreach(corners, _corner_label),
                                            width="100%",
                                            height="62px",
                                            position="relative",
                                        ),
                                    ),
                                    rx.text(
                                        rx.cond(
                                            corners.length() > 0,
                                            "DISTANCE (KM)  ·  TRACK CORNERS",
                                            "DISTANCE (KM)",
                                        ),
                                        size="1",
                                        color=rx.color("gray", 10),
                                        padding_left="68px",
                                    ),
                                    width="100%",
                                    min_width=CHART_MIN_WIDTH,
                                    align="stretch",
                                    spacing="3",
                                ),
                                width="100%",
                                overflow_x="auto",
                                overflow_y="hidden",
                            ),
                            width="100%",
                            align="stretch",
                            spacing="4",
                        ),
                    ),
                ),
            ),
        ),
        width="100%",
        align="stretch",
        spacing="4",
    )
