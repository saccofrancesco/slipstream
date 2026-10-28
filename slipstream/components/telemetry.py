"""Six synchronized distance charts for selected historical laps."""

from math import ceil, floor
from typing import TypedDict

import reflex as rx

from .layout import loading_card, status_card
from .trackmap import (
    TrackmapCorner,
    TrackmapPlaybackLap,
    TrackmapPoint,
    TrackmapSegment,
    telemetry_playback_line,
    telemetry_track_sync,
)

CHART_MARGIN: dict[str, int] = {"top": 10, "right": 20, "left": 0, "bottom": 4}
CHART_MIN_WIDTH: str = "900px"
CHART_HEIGHTS: dict[str, int] = {
    "speed": 310,
    "delta": 100,
    "throttle": 205,
    "brake": 100,
    "rpm": 205,
    "gear": 205,
}
TELEMETRY_CHARTS: tuple[tuple[str, str, bool], ...] = (
    ("speed", "SPEED (km/h)", False),
    ("delta", "DELTA (s)", False),
    ("throttle", "THROTTLE (%)", False),
    ("brake", "BRAKE", False),
    ("rpm", "RPM", False),
    ("gear", "GEAR", True),
)


class TelemetryLine(TypedDict):
    """Presentation details shared by one lap's six series."""

    key: str
    label: str
    color: str
    dash: str
    baseline: bool
    speed_key: str
    delta_key: str
    throttle_key: str
    brake_key: str
    rpm_key: str
    gear_key: str


class TelemetryAxis(TypedDict):
    """Visible tick values and a range containing every plotted sample."""

    domain: list[float]
    ticks: list[float]


class CornerMark(TypedDict):
    """Circuit corner and its projected position on the distance axis."""

    label: str
    distance: int


class SectorMark(TypedDict):
    """Sector boundary and its projected position on the distance axis."""

    label: str
    distance: int


def _channel_values(
    rows: list[dict[str, float | int]], lines: list[TelemetryLine], metric: str
) -> list[float]:
    """Read only the loaded laps' samples for one telemetry channel."""
    keys = [f"{metric}_{line['key']}" for line in lines]
    return [float(row[key]) for row in rows for key in keys if key in row]


def _stepped_axis(values: list[float], first: int, step: int) -> TelemetryAxis:
    """Show each reached multiple while retaining all samples in the domain."""
    low = min([float(first), *values])
    high = max([float(first), *values])
    if low == high:
        low -= step / 2
        high += step / 2
    last_tick = max(first, floor(high / step) * step)
    return {
        "domain": [low, high],
        "ticks": [float(value) for value in range(first, last_tick + 1, step)],
    }


def _rpm_axis(values: list[float]) -> TelemetryAxis:
    """Show only 2000-RPM markers reached within the plotted range."""
    if not values:
        return {"domain": [0.0, 1.0], "ticks": []}
    low, high = min(values), max(values)
    first_tick = max(2000, ceil(low / 2000) * 2000)
    last_tick = floor(high / 2000) * 2000
    domain = [low, high] if low != high else [low - 1000, high + 1000]
    return {
        "domain": domain,
        "ticks": [float(value) for value in range(first_tick, last_tick + 1, 2000)],
    }


def build_telemetry_axes(
    rows: list[dict[str, float | int]], lines: list[TelemetryLine]
) -> dict[str, TelemetryAxis]:
    """Fit the six y-axes to the selected laps' distance-aligned samples."""
    speed = _channel_values(rows, lines, "speed")
    delta = _channel_values(rows, lines, "delta")
    rpm = _channel_values(rows, lines, "rpm")
    gear = _channel_values(rows, lines, "gear")
    largest_delta = max((abs(value) for value in delta), default=0.0)
    delta_extent = largest_delta if largest_delta > 0 else 0.1
    return {
        "speed": _stepped_axis(speed, 100, 50),
        "delta": {
            "domain": [-delta_extent, delta_extent],
            "ticks": (
                [-largest_delta / 2, 0.0, largest_delta / 2]
                if largest_delta > 0
                else [0.0]
            ),
        },
        "throttle": {"domain": [0.0, 100.0], "ticks": [20.0, 60.0, 100.0]},
        "brake": {"domain": [0.0, 1.0], "ticks": [0.0, 1.0]},
        "rpm": _rpm_axis(rpm),
        "gear": {
            "domain": [0.0, 8.0],
            "ticks": [1.0, 3.0, 5.0, 7.0] if 1.0 in gear else [2.0, 4.0, 6.0, 8.0],
        },
    }


def _tooltip_formatter(metric: str) -> rx.Var:
    """Render a Laps-style driver row with the current channel's value."""
    expressions = {
        "speed": "`${Math.round(Number(value))} km/h`",
        "delta": '`${Number(value) > 0 ? "+" : ""}${Number(value).toFixed(3)} s`',
        "throttle": "`${Math.round(Number(value))}%`",
        "brake": '`${Number(value) >= 0.5 ? "1" : "0"}`',
        "rpm": "`${Math.round(Number(value)).toLocaleString()} RPM`",
        "gear": "`${Math.round(Number(value))}`",
    }
    return rx.Var(
        _js_expr=f"""
            (value, name, item) => {{
                const formatted = {expressions[metric]};
                return [jsx("span", {{
                    style: {{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        minWidth: "12rem",
                    }},
                    children: [
                        jsx("span", {{
                            "aria-hidden": true,
                            style: {{
                                width: "0.625rem",
                                height: "0.625rem",
                                borderRadius: "3px",
                                backgroundColor: item.color || item.stroke,
                                flexShrink: 0,
                            }},
                        }}),
                        jsx("span", {{
                            style: {{fontWeight: 700}},
                            children: String(name),
                        }}),
                        jsx("span", {{
                            style: {{
                                marginLeft: "auto",
                                fontVariantNumeric: "tabular-nums",
                            }},
                            children: formatted,
                        }}),
                    ],
                }}), null];
            }}
        """
    )


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
        is_animation_active=True,
        animation_duration=900,
        animation_easing="ease-out",
    )


def _corner_line(corner: rx.Var[CornerMark]) -> rx.Component:
    """Show a faint distance guide and its label along the plot bottom."""
    return rx.recharts.reference_line(
        rx.recharts.label(
            value=corner["label"],
            position="insideBottom",
            offset=5,
            fill=rx.color("gray", 11),
            font_size=8,
            font_weight=600,
        ),
        x=corner["distance"],
        stroke=rx.color("gray", 7),
        stroke_width=1,
        stroke_dasharray="2 5",
        if_overflow="hidden",
    )


def _sector_line(sector: rx.Var[SectorMark]) -> rx.Component:
    """Show the lap's S2 or S3 boundary as a quiet solid guide."""
    return rx.recharts.reference_line(
        rx.recharts.label(
            value=sector["label"],
            position="insideTop",
            offset=5,
            fill=rx.color("gray", 11),
            font_size=8,
        ),
        x=sector["distance"],
        stroke=rx.color("gray", 8),
        stroke_width=1,
        if_overflow="hidden",
    )


def _telemetry_chart(
    metric: str,
    axis_label: str,
    rows: rx.Var[list[dict[str, float | int]]],
    lines: rx.Var[list[TelemetryLine]],
    axis: rx.Var[TelemetryAxis],
    corners: rx.Var[list[CornerMark]],
    sectors: rx.Var[list[SectorMark]],
    distance_metres: rx.Var[float],
    last: bool = False,
) -> rx.Component:
    """Build one channel with the same x scale and synchronized cursor."""
    tick_formatter = (
        '(value) => Number(value) >= 0.5 ? "ON" : "OFF"'
        if metric == "brake"
        else '(value) => { const n = Number(value); return n === 0 ? "0" : '
        '`${n > 0 ? "+" : ""}${Number(n.toFixed(4))}`; }'
        if metric == "delta"
        else None
    )
    return rx.recharts.line_chart(
        rx.recharts.cartesian_grid(
            stroke=rx.color("gray", 5), stroke_dasharray="3 5", vertical=False
        ),
        rx.recharts.x_axis(
            data_key="distance",
            type_="number",
            domain=["dataMin", "dataMax"],
            allow_data_overflow=True,
            hide=rx.cond(corners.length() > 0, True, not last),
            axis_line=False,
            tick_line=False,
            tick_count=7,
            height=24,
            tick_formatter="(value) => `${(value / 1000).toFixed(1)}`",
            stroke=rx.color("gray", 10),
        ),
        rx.recharts.y_axis(
            type_="number",
            width=68,
            domain=axis["domain"],
            padding={"top": 8, "bottom": 8},
            allow_data_overflow=True,
            axis_line=False,
            tick_line=False,
            tick={"fontSize": 11},
            interval=0,
            tick_formatter=tick_formatter,
            custom_attrs={"niceTicks": "none", "ticks": axis["ticks"]},
            stroke=rx.color("gray", 10),
            label={
                "value": axis_label,
                "angle": -90,
                "position": "insideLeft",
                "textAnchor": "middle",
                "fill": rx.color("gray", 10),
                "fontSize": 12,
            },
        ),
        rx.foreach(corners, _corner_line),
        rx.foreach(sectors, _sector_line),
        rx.cond(
            metric == "delta",
            rx.recharts.reference_line(y=0, stroke=rx.color("gray", 9)),
        ),
        telemetry_playback_line(distance_metres=distance_metres),
        rx.recharts.graphing_tooltip(
            cursor={
                "stroke": "var(--gray-8)",
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
            label_style={
                "color": "var(--gray-11)",
                "fontWeight": 700,
                "marginBottom": "6px",
            },
            custom_attrs={
                "formatter": _tooltip_formatter(metric),
                "labelFormatter": rx.Var(
                    _js_expr="(value) => `${Math.round(value)} m`"
                ),
            },
        ),
        rx.foreach(lines, lambda line: _chart_line(line, metric)),
        data=rows,
        sync_id="selected-lap-telemetry",
        sync_method="index",
        width="100%",
        height=CHART_HEIGHTS[metric],
        margin=CHART_MARGIN,
    )


def telemetry_section(
    rows: rx.Var[list[dict[str, float | int]]],
    lines: rx.Var[list[TelemetryLine]],
    axes: rx.Var[dict[str, TelemetryAxis]],
    track_points: rx.Var[list[TrackmapPoint]],
    track_segments: rx.Var[list[TrackmapSegment]],
    track_corners: rx.Var[list[TrackmapCorner]],
    playback_laps: rx.Var[list[TrackmapPlaybackLap]],
    playback_key: rx.Var[str],
    distance_metres: rx.Var[float],
    preserve_orientation: rx.Var[bool],
    animation_key: rx.Var[str],
    corners: rx.Var[list[CornerMark]],
    sectors: rx.Var[list[SectorMark]],
    unavailable: rx.Var[list[str]],
    selected_count: rx.Var[int],
    loading: rx.Var[bool],
    error: rx.Var[str],
    on_open_laps: rx.EventHandler,
    on_retry: rx.EventHandler,
) -> rx.Component:
    """Render selection states and the six-chart comparison stack."""
    return rx.cond(
        selected_count == 0,
        rx.card(
            rx.vstack(
                rx.box(
                    rx.icon("activity", size=20, color=rx.color("accent", 11)),
                    padding="3",
                    border_radius="full",
                    background_color=rx.color("accent", 3),
                ),
                rx.vstack(
                    rx.heading(
                        "Select laps to compare",
                        size="4",
                        weight="bold",
                        text_align="center",
                    ),
                    rx.text(
                        "Choose one or more lap times from the Laps tab to compare speed, throttle, and more.",
                        color=rx.color("gray", 11),
                        line_height="1.5",
                        max_width="42rem",
                        text_align="center",
                    ),
                    align="center",
                    spacing="2",
                    width="100%",
                ),
                rx.button(
                    rx.text("Choose laps"),
                    rx.icon("arrow-right", size=16),
                    on_click=on_open_laps,
                    variant="solid",
                    size="3",
                    cursor="pointer",
                ),
                align="center",
                spacing="4",
                width="100%",
                padding_x="4",
                padding_y="6",
            ),
            width="100%",
            background_color=rx.color("gray", 2),
            border_width="1px",
            border_style="solid",
            border_color=rx.color("gray", 5),
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
                    telemetry_track_sync(
                        rx.box(
                            rx.vstack(
                                *[
                                    _telemetry_chart(
                                        metric,
                                        label,
                                        rows,
                                        lines,
                                        axes[metric],
                                        corners,
                                        sectors,
                                        distance_metres,
                                        last=last,
                                    )
                                    for metric, label, last in TELEMETRY_CHARTS
                                ],
                                width="100%",
                                min_width=CHART_MIN_WIDTH,
                                align="stretch",
                                gap="0.75rem",
                                key=animation_key,
                            ),
                            width="100%",
                            min_width="0",
                            overflow_x="auto",
                            overflow_y="hidden",
                        ),
                        points=track_points,
                        segments=track_segments,
                        corners=track_corners,
                        playback_laps=playback_laps,
                        playback_key=playback_key,
                        distance_metres=distance_metres,
                        preserve_orientation=preserve_orientation,
                        animation_key=animation_key,
                        duration_ms=2200,
                    ),
                ),
            ),
        ),
    )
