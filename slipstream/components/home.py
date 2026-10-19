"""Presentation components for the Slipstream landing page."""

import reflex as rx


def _eyebrow() -> rx.Component:
    """Build the compact product label shown above the hero heading."""
    return rx.hstack(
        rx.box(
            width="0.55rem",
            height="0.55rem",
            border_radius="full",
            background_color=rx.color("accent", 9),
            box_shadow=f"0 0 0 0.3rem {rx.color('accent', 3)}",
        ),
        rx.text(
            "FORMULA 1, MADE CLEAR",
            size="2",
            weight="bold",
            color=rx.color("gray", 11),
            letter_spacing="0.16em",
        ),
        align="center",
        spacing="3",
    )


def _hero_action(
    label: str,
    href: str,
    icon: str,
    primary: bool = False,
) -> rx.Component:
    """Create one prominent hero link.

    Args:
        label: Text shown inside the link.
        href: Internal route opened by the link.
        icon: Lucide icon placed beside the label.
        primary: Whether to use the filled accent treatment.

    Returns:
        A button-like navigation link.
    """
    return rx.link(
        rx.hstack(
            rx.text(label, weight="bold"),
            rx.icon(icon, size=18),
            align="center",
            spacing="2",
        ),
        href=href,
        underline="none",
        color="white" if primary else rx.color("gray", 12),
        background_color=(rx.color("accent", 9) if primary else rx.color("gray", 3)),
        border_width="1px",
        border_style="solid",
        border_color=(rx.color("accent", 9) if primary else rx.color("gray", 6)),
        border_radius="0.65rem",
        padding_x="1.15rem",
        padding_y="0.75rem",
        transition="transform 160ms ease, background-color 160ms ease, border-color 160ms ease",
        _hover={
            "color": "white" if primary else rx.color("gray", 12),
            "background_color": (
                rx.color("accent", 10) if primary else rx.color("gray", 4)
            ),
            "border_color": (
                rx.color("accent", 10) if primary else rx.color("gray", 7)
            ),
            "text_decoration": "none",
            "transform": "translateY(-2px)",
        },
    )


def _data_label(icon: str, label: str, detail: str) -> rx.Component:
    """Render one capability inside the hero's data panel."""
    return rx.hstack(
        rx.center(
            rx.icon(icon, size=18, color="white"),
            width="2.35rem",
            height="2.35rem",
            border_radius="0.65rem",
            background_color="rgba(255, 255, 255, 0.12)",
            border="1px solid rgba(255, 255, 255, 0.12)",
            flex_shrink="0",
        ),
        rx.vstack(
            rx.text(
                label,
                size="2",
                weight="bold",
                color="white",
                letter_spacing="0.08em",
            ),
            rx.text(
                detail,
                size="1",
                color="rgba(255, 255, 255, 0.62)",
            ),
            align="start",
            spacing="0",
        ),
        align="center",
        spacing="3",
        width="100%",
    )


def _race_data_panel() -> rx.Component:
    """Build the decorative race-analysis panel beside the hero copy."""
    return rx.box(
        # Oversized rings suggest a circuit without presenting invented data.
        rx.box(
            position="absolute",
            width="25rem",
            height="25rem",
            border="1px solid rgba(255, 255, 255, 0.09)",
            border_radius="45% 55% 52% 48%",
            top="-9rem",
            right="-8rem",
            transform="rotate(-18deg)",
        ),
        rx.box(
            position="absolute",
            width="19rem",
            height="19rem",
            border="1px dashed rgba(255, 255, 255, 0.08)",
            border_radius="52% 48% 44% 56%",
            bottom="-10rem",
            left="-5rem",
            transform="rotate(24deg)",
        ),
        rx.vstack(
            rx.hstack(
                rx.hstack(
                    rx.box(
                        width="0.5rem",
                        height="0.5rem",
                        border_radius="full",
                        background_color="#ff4d4f",
                        box_shadow="0 0 0 0.25rem rgba(255, 77, 79, 0.14)",
                    ),
                    rx.text(
                        "RACE INTELLIGENCE",
                        size="1",
                        weight="bold",
                        color="rgba(255, 255, 255, 0.72)",
                        letter_spacing="0.16em",
                    ),
                    align="center",
                    spacing="3",
                ),
                rx.icon(
                    "activity",
                    size=20,
                    color="rgba(255, 255, 255, 0.5)",
                ),
                justify="between",
                align="center",
                width="100%",
            ),
            rx.vstack(
                rx.text(
                    "FOLLOW THE",
                    size="2",
                    weight="bold",
                    color="rgba(255, 255, 255, 0.48)",
                    letter_spacing="0.18em",
                ),
                rx.heading(
                    "WHOLE RACE.",
                    as_="h2",
                    size="8",
                    color="white",
                    letter_spacing="-0.04em",
                    line_height="0.95",
                ),
                align="start",
                spacing="2",
                width="100%",
                padding_y="5",
            ),
            rx.vstack(
                _data_label("calendar-days", "WEEKEND", "Sessions and results"),
                rx.separator(color_scheme="gray", opacity="0.3"),
                _data_label("gauge", "PACE", "Lap-by-lap comparison"),
                rx.separator(color_scheme="gray", opacity="0.3"),
                _data_label("radio-tower", "TELEMETRY", "Driver inputs in context"),
                align="stretch",
                spacing="3",
                width="100%",
            ),
            align="stretch",
            justify="between",
            spacing="4",
            width="100%",
            min_height="27rem",
            position="relative",
            z_index="1",
        ),
        position="relative",
        overflow="hidden",
        width="100%",
        min_height="27rem",
        padding=rx.breakpoints(initial="1.5rem", md="2rem"),
        border_radius="1.25rem",
        background="linear-gradient(145deg, #241416 0%, #151112 55%, #0c0b0c 100%)",
        border="1px solid rgba(255, 255, 255, 0.08)",
        box_shadow="0 1.5rem 4rem rgba(0, 0, 0, 0.24)",
    )


def home_hero() -> rx.Component:
    """Render the landing-page hero and its race-analysis visual."""
    return rx.grid(
        rx.vstack(
            _eyebrow(),
            rx.heading(
                "EVERY LAP",
                rx.text(
                    "TELLS A STORY.",
                    as_="span",
                    display="block",
                    color=rx.color("accent", 10),
                ),
                as_="h1",
                size="9",
                weight="bold",
                font_size="clamp(3rem, 8vw, 5.75rem)",
                line_height="0.9",
                letter_spacing="-0.055em",
            ),
            rx.text(
                "Slipstream brings race weekends, championship battles, lap pace, and driver telemetry into one focused view.",
                size="5",
                color=rx.color("gray", 11),
                line_height="1.65",
                max_width="39rem",
            ),
            rx.flex(
                _hero_action("Explore results", "/results", "arrow-right", True),
                _hero_action("View standings", "/drivers", "trophy"),
                direction=rx.breakpoints(initial="column", sm="row"),
                gap="0.75rem",
                width=rx.breakpoints(initial="100%", sm="auto"),
            ),
            align="start",
            justify="center",
            spacing="6",
            width="100%",
            padding_y=rx.breakpoints(initial="3rem", md="5rem"),
        ),
        _race_data_panel(),
        columns=rx.breakpoints(initial="1", md="2"),
        spacing=rx.breakpoints(initial="7", md="9"),
        align="center",
        width="100%",
    )


def _destination_card(
    eyebrow: str,
    title: str,
    description: str,
    href: str,
    icon: str,
) -> rx.Component:
    """Create a linked card for one of Slipstream's main sections."""
    return rx.link(
        rx.vstack(
            rx.hstack(
                rx.center(
                    rx.icon(icon, size=21, color=rx.color("accent", 11)),
                    width="2.75rem",
                    height="2.75rem",
                    border_radius="0.75rem",
                    background_color=rx.color("accent", 3),
                ),
                rx.icon(
                    "arrow-up-right",
                    size=19,
                    color=rx.color("gray", 9),
                ),
                justify="between",
                align="center",
                width="100%",
            ),
            rx.vstack(
                rx.text(
                    eyebrow,
                    size="1",
                    weight="bold",
                    color=rx.color("accent", 11),
                    letter_spacing="0.14em",
                ),
                rx.heading(title, as_="h3", size="6", letter_spacing="-0.025em"),
                rx.text(
                    description,
                    size="3",
                    color=rx.color("gray", 11),
                    line_height="1.55",
                ),
                align="start",
                spacing="2",
            ),
            align="start",
            justify="between",
            spacing="6",
            width="100%",
            min_height="15rem",
            padding="1.4rem",
        ),
        href=href,
        underline="none",
        color="inherit",
        background_color=rx.color("gray", 2),
        border_width="1px",
        border_style="solid",
        border_color=rx.color("gray", 5),
        border_radius="1rem",
        transition="transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease",
        _hover={
            "color": "inherit",
            "text_decoration": "none",
            "transform": "translateY(-4px)",
            "border_color": rx.color("accent", 7),
            "box_shadow": "0 1rem 2.5rem rgba(0, 0, 0, 0.10)",
        },
    )


def home_destinations() -> rx.Component:
    """Render the section links beneath the landing-page hero."""
    return rx.vstack(
        rx.flex(
            rx.vstack(
                rx.text(
                    "START YOUR ANALYSIS",
                    size="2",
                    weight="bold",
                    color=rx.color("accent", 11),
                    letter_spacing="0.16em",
                ),
                rx.heading(
                    "Pick your view of the season.",
                    as_="h2",
                    size="7",
                    letter_spacing="-0.035em",
                ),
                align="start",
                spacing="2",
            ),
            rx.text(
                "Move from the latest weekend to the title fight in a single stop.",
                size="3",
                color=rx.color("gray", 11),
                line_height="1.55",
                max_width="24rem",
            ),
            justify="between",
            align=rx.breakpoints(initial="start", md="end"),
            direction=rx.breakpoints(initial="column", md="row"),
            gap="1rem",
            width="100%",
        ),
        rx.grid(
            _destination_card(
                "RACE WEEKENDS",
                "Results",
                "Browse the calendar, session classifications, lap charts, and telemetry from each Grand Prix.",
                "/results",
                "flag",
            ),
            _destination_card(
                "CHAMPIONSHIP",
                "Drivers",
                "See how every driver stacks up after the latest completed round of the season.",
                "/drivers",
                "trophy",
            ),
            _destination_card(
                "CONSTRUCTORS",
                "Teams",
                "Follow the battle between teams and the points shaping the constructors' championship.",
                "/constructors",
                "users",
            ),
            columns=rx.breakpoints(initial="1", md="3"),
            spacing="4",
            width="100%",
        ),
        align="stretch",
        spacing="6",
        width="100%",
        padding_top="2rem",
        padding_bottom="5rem",
    )
