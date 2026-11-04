"""Presentation components for the Slipstream landing page."""

import reflex as rx


def _destination_card(title: str, description: str, href: str) -> rx.Component:
    """Link to a main section of the application."""
    return rx.link(
        rx.card(
            rx.vstack(
                rx.heading(title, as_="h2", size="5"),
                rx.text(description, color=rx.color("gray", 11), size="3"),
                align="start",
                spacing="2",
            ),
            width="100%",
            height="100%",
        ),
        href=href,
        underline="none",
        color="inherit",
        width="100%",
        border_radius="var(--radius-3)",
        _hover={"color": "inherit", "text_decoration": "none"},
        _focus_visible={
            "outline": f"2px solid {rx.color('accent', 9)}",
            "outline_offset": "3px",
        },
    )


def home_destinations() -> rx.Component:
    """Render links to the application's main sections."""
    return rx.grid(
        _destination_card(
            "Results",
            "Explore race weekends, session results, laps, and telemetry.",
            "/results",
        ),
        _destination_card(
            "Drivers",
            "Follow the drivers’ championship standings.",
            "/drivers",
        ),
        _destination_card(
            "Teams",
            "Follow the constructors’ championship standings.",
            "/constructors",
        ),
        columns=rx.breakpoints(initial="1", md="3"),
        spacing="4",
        width="100%",
    )
