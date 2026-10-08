"""Session lap chart and its driver, compound, and outlier controls."""

from typing import TypedDict

import reflex as rx

from .layout import loading_card, status_card

CHART_ANIMATION_DURATION_MS: int = 1500


class DriverChip(TypedDict):
    """Driver selection state and its current chart color."""

    code: str
    name: str
    team: str
    team_color: str
    selected: bool
    plot_color: str
    selected_fill: str


class DriverLine(TypedDict):
    """One driver's line and legend color."""

    code: str
    color: str


class TyrePointLine(TypedDict):
    """A compound-colored marker series for one selected driver."""

    key: str
    code: str
    color: str
    line_color: str


def _driver_line(series: rx.Var[DriverLine]) -> rx.Component:
    """Render one animated, monotone driver lap-time line."""
    return rx.recharts.line(
        data_key=series["code"],
        name=series["code"],
        type_="monotone",
        stroke=series["color"],
        stroke_width=2.5,
        dot=False,
        active_dot=False,
        connect_nulls=True,
        is_animation_active=True,
        animation_duration=CHART_ANIMATION_DURATION_MS,
        animation_easing="ease-in-out",
    )


def _tyre_point_line(series: rx.Var[TyrePointLine]) -> rx.Component:
    """Render tyre-colored point marks while keeping them out of the tooltip."""
    return rx.recharts.line(
        data_key=series["key"],
        name=series["code"],
        type_="monotone",
        stroke="transparent",
        stroke_width=0,
        dot={
            "r": 4,
            "fill": series["color"],
            "stroke": series["line_color"],
            "strokeWidth": 1.5,
        },
        active_dot=False,
        connect_nulls=False,
        legend_type="none",
        is_animation_active=True,
        animation_duration=CHART_ANIMATION_DURATION_MS,
        animation_easing="ease-in-out",
        custom_attrs={"tooltipType": "none"},
    )


def _driver_chip(chip: rx.Var[DriverChip], on_toggle: rx.EventHandler) -> rx.Component:
    """Render a selectable driver code in its team's colors."""
    return rx.button(
        chip["code"],
        title=chip["name"],
        on_click=lambda: on_toggle(chip["code"]),
        variant="ghost",
        size="2",
        width="3.75rem",
        box_sizing="border-box",
        padding_x="0.5rem",
        margin="0",
        font_weight="bold",
        letter_spacing="0.04em",
        color=chip["team_color"],
        border_style="solid",
        border_color=chip["team_color"],
        border_width="1px",
        background_color=rx.cond(chip["selected"], chip["selected_fill"], "transparent"),
        _hover={"background_color": chip["selected_fill"]},
        aria_pressed=chip["selected"],
        cursor="pointer",
    )


def _lap_time_formatter() -> rx.Var:
    """Return whole-second labels for the numeric lap-time axis."""
    return rx.Var(
        _js_expr=(
            '(value) => { const totalSeconds = Math.floor(Number(value)); '
            'const minutes = Math.floor(totalSeconds / 60); '
            'const seconds = String(totalSeconds % 60).padStart(2, "0"); '
            'return `${minutes}:${seconds}`; }'
        )
    )


def _lap_tooltip_formatter() -> rx.Var:
    """Render each driver's tooltip row with its line color and lap tyre."""
    return rx.Var(
        _js_expr="""
            (value, name, item) => {
                const code = String(name);
                const row = item.payload ?? {};
                const markerPrefix = `marker_${code}_`;
                const markerKey = Object.keys(row).find(
                    (key) => key.startsWith(markerPrefix) && row[key] != null
                );
                const compound = markerKey ? markerKey.slice(markerPrefix.length) : "";
                const tyreIcons = {
                    SOFT: "/tyres/soft.svg",
                    MEDIUM: "/tyres/medium.svg",
                    HARD: "/tyres/hard.svg",
                    INTERMEDIATE: "/tyres/intermediate.svg",
                    WET: "/tyres/wet.svg",
                };
                const tyreIcon = tyreIcons[compound];
                const ms = Math.round(Number(value) * 1000);
                const minutes = Math.floor(ms / 60000);
                const seconds = ((ms % 60000) / 1000).toFixed(3).padStart(6, "0");
                const children = [
                    jsx("span", {
                        "aria-hidden": true,
                        style: {
                            width: "0.625rem",
                            height: "0.625rem",
                            borderRadius: "3px",
                            backgroundColor: item.color || item.stroke,
                            flexShrink: 0,
                        },
                    }),
                    jsx("span", {style: {fontWeight: 700}, children: code}),
                    jsx("span", {
                        style: {marginLeft: "auto", fontVariantNumeric: "tabular-nums"},
                        children: `${minutes}:${seconds}`,
                    }),
                ];
                if (tyreIcon) {
                    children.push(jsx("img", {
                        src: tyreIcon,
                        alt: `${compound.toLowerCase()} tyre`,
                        width: 24,
                        height: 24,
                        style: {display: "block", objectFit: "contain", flexShrink: 0},
                    }));
                } else {
                    children.push(jsx("span", {
                        role: "img",
                        "aria-label": "Tyre unknown",
                        title: "Tyre unknown",
                        style: {
                            width: "1.5rem",
                            height: "1.5rem",
                            border: "1px solid var(--gray-9)",
                            borderRadius: "50%",
                            flexShrink: 0,
                        },
                    }));
                }
                return [jsx("span", {
                    style: {
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        minWidth: "11rem",
                    },
                    children,
                }), null];
            }
        """
    )


def laps_section(
    selected_session_label: rx.Var[str],
    chips: rx.Var[list[DriverChip]],
    on_toggle_driver: rx.EventHandler,
    chart_data: rx.Var[list[dict[str, float | int | None]]],
    driver_lines: rx.Var[list[DriverLine]],
    tyre_point_lines: rx.Var[list[TyrePointLine]],
    selected_count: rx.Var[int],
    show_outliers: rx.Var[bool],
    on_outliers_change: rx.EventHandler,
    loading: rx.Var[bool],
    loaded: rx.Var[bool],
    error: rx.Var[str],
) -> rx.Component:
    """Render the selected session's controls and interactive lap chart."""
    time_formatter = _lap_time_formatter()
    tooltip_formatter = _lap_tooltip_formatter()
    tooltip_lap_formatter = rx.Var(_js_expr='(value) => `Lap ${value}`')

    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.text(
                    "LAP ANALYSIS",
                    size="2",
                    weight="bold",
                    color=rx.color("accent", 11),
                    letter_spacing="0.14em",
                ),
                rx.heading(selected_session_label, as_="h2", size="5", weight="bold"),
                align="start",
                spacing="1",
            ),
            rx.spacer(),
            rx.hstack(
                rx.switch(checked=show_outliers, on_change=on_outliers_change, size="2"),
                rx.text("Show outliers", size="2", weight="medium"),
                align="center",
                spacing="2",
            ),
            width="100%",
            align="center",
            flex_wrap="wrap",
            gap="3",
        ),
        rx.cond(
            loading,
            loading_card("Loading lap times for this session…"),
            rx.cond(
                error != "",
                status_card("Lap times unavailable", error),
                rx.cond(
                    loaded,
                    rx.flex(
                        rx.vstack(
                            rx.text(
                                "DRIVERS",
                                size="1",
                                weight="bold",
                                color=rx.color("gray", 10),
                                letter_spacing="0.1em",
                            ),
                            rx.grid(
                                rx.foreach(
                                    chips,
                                    lambda chip: _driver_chip(chip, on_toggle_driver),
                                ),
                                grid_template_columns="repeat(2, 3.75rem)",
                                gap="0.5rem",
                                width="fit-content",
                            ),
                            align="stretch",
                            spacing="2",
                            width="fit-content",
                            flex_shrink="0",
                        ),
                        rx.box(
                            rx.recharts.line_chart(
                                rx.recharts.cartesian_grid(
                                    stroke=rx.color("gray", 5),
                                    stroke_dasharray="3 5",
                                    vertical=True,
                                ),
                                rx.recharts.x_axis(
                                    data_key="lap_number",
                                    type_="number",
                                    domain=["dataMin", "dataMax"],
                                    allow_decimals=False,
                                    tick_count=9,
                                    axis_line=False,
                                    tick_line=False,
                                    stroke=rx.color("gray", 10),
                                    height=56,
                                    label={
                                        "value": "LAP NUMBER",
                                        "position": "insideBottom",
                                        "offset": 4,
                                        "fill": rx.color("gray", 10),
                                    },
                                ),
                                rx.recharts.y_axis(
                                    type_="number",
                                    domain=["auto", "auto"],
                                    tick_count=5,
                                    tick_formatter=time_formatter,
                                    axis_line=False,
                                    tick_line=False,
                                    width=64,
                                    stroke=rx.color("gray", 10),
                                    label={
                                        "value": "LAP TIME",
                                        "angle": -90,
                                        "position": "insideLeft",
                                        "fill": rx.color("gray", 10),
                                    },
                                ),
                                rx.recharts.graphing_tooltip(
                                    cursor={
                                        "stroke": "rgba(255,255,255,0.55)",
                                        "strokeWidth": 1,
                                        "strokeDasharray": "4 4",
                                    },
                                    separator="  ",
                                    filter_null=True,
                                    wrapper_style={"outline": "none"},
                                    content_style={
                                        "backgroundColor": "var(--gray-2)",
                                        "border": "1px solid var(--gray-6)",
                                        "borderRadius": "10px",
                                        "boxShadow": "0 8px 24px rgba(0,0,0,0.28)",
                                        "padding": "10px 12px",
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
                                    is_animation_active=False,
                                    custom_attrs={
                                        "formatter": tooltip_formatter,
                                        "labelFormatter": tooltip_lap_formatter,
                                    },
                                ),
                                rx.recharts.legend(
                                    layout="horizontal",
                                    align="center",
                                    vertical_align="top",
                                    height=30,
                                    wrapper_style={"fontSize": "12px"},
                                ),
                                rx.foreach(driver_lines, _driver_line),
                                rx.foreach(tyre_point_lines, _tyre_point_line),
                                data=chart_data,
                                width="100%",
                                height=440,
                                margin={"top": 8, "right": 20, "left": 6, "bottom": 20},
                            ),
                            rx.cond(
                                selected_count == 0,
                                rx.text(
                                    "Select a driver to plot lap times",
                                    size="2",
                                    color=rx.color("gray", 10),
                                    text_align="center",
                                    position="absolute",
                                    top="50%",
                                    left="50%",
                                    transform="translate(-50%, -50%)",
                                    pointer_events="none",
                                ),
                            ),
                            position="relative",
                            width="100%",
                            min_width="0",
                            flex="1",
                        ),
                        direction=rx.breakpoints(initial="column", md="row"),
                        gap="1.5rem",
                        width="100%",
                        align="start",
                    ),
                    status_card(
                        "No lap times available",
                        "The timing feed has not published timed laps for this session.",
                    ),
                ),
            ),
        ),
        width="100%",
        align="stretch",
        spacing="4",
    )
