# Importing libraries
import reflex as rx
from .layout import container


# Single navbar icon item
def navbar_icon_item(text: str, icon: str, url: str, active: bool = False) -> rx.Component:
    return rx.link(
        rx.hstack(rx.icon(icon), rx.text(text, size="4", weight="medium")),
        href=url,
        underline="none",
        padding_x="2",
        padding_y="1",
        border_radius="full",
        style={
            "color": rx.color("accent", 11) if active else "inherit",
            "background_color": rx.color("accent", 3) if active else "transparent",
            "transition": "background-color 150ms ease, color 150ms ease",
            "_hover": {
                "color": rx.color("accent", 11),
                "background_color": rx.color("accent", 3),
                "text_decoration": "none",
            },
        },
    )


# Full navbar component to be displayed in all pages
def navbar(active_section: str | None = None) -> rx.Component:
    return rx.box(
        container(
            rx.hstack(
                rx.link(
                    rx.heading("SLIPSTREAM", as_="h2", size="7", weight="bold"),
                    href="/",
                    underline="none",
                    style={
                        "color": "inherit",
                        "opacity": 1,
                        "transition": "none",
                        "_hover": {
                            "color": "inherit",
                            "opacity": 1,
                            "text_decoration": "none",
                        },
                        "_active": {"color": "inherit", "opacity": 1},
                        "_visited": {"color": "inherit"},
                    },
                ),
                rx.hstack(
                    navbar_icon_item(
                        "DRIVERS", "trophy", "/drivers", active_section == "drivers"
                    ),
                    navbar_icon_item(
                        "TEAMS", "users", "/constructors", active_section == "teams"
                    ),
                    spacing="6",
                ),
                justify="between",
                align="center",
                width="100%",
            ),
        ),
        bg=rx.color("accent", 3),
        width="100%",
        position="sticky",
        top="0",
        z_index="10",
    )
