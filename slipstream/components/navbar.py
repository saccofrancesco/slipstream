"""Navigation components shared by every application page."""

# Reflex provides the component and styling primitives for navigation.
import reflex as rx

# Reuse the shared page-width wrapper for the header contents.
from .layout import container


def navbar_icon_item(
    text: str,
    icon: str,
    url: str,
    active: bool = False,
) -> rx.Component:
    """Build a linked navigation item with an optional active state.

    Args:
        text: Label displayed beside the icon.
        icon: Icon name accepted by ``rx.icon``.
        url: Destination route for the link.
        active: Whether the link represents the current page.

    Returns:
        A styled Reflex link containing the icon and label.
    """
    # Use text color to show interaction states without adding a background fill.
    return rx.link(
        rx.hstack(
            rx.icon(icon),
            rx.text(
                text,
                size="4",
                weight="medium",
                display=rx.breakpoints(initial="none", md="block"),
            ),
        ),
        href=url,
        aria_label=text,
        underline="none",
        padding_x=rx.breakpoints(initial="1", md="2"),
        padding_y="1",
        border_radius="full",
        color=rx.color("accent", 11) if active else "inherit",
        background_color="transparent",
        transition="color 150ms ease",
        _hover={
            "color": rx.color("accent", 11),
            "background_color": "transparent",
            "text_decoration": "none",
        },
    )


def navbar(active_section: str | None = None) -> rx.Component:
    """Build the sticky site header and its section navigation links.

    Args:
        active_section: Name of the currently selected navigation section.

    Returns:
        A full-width header containing the brand link and page links.
    """
    # Keep the brand link's appearance unchanged across its interaction states.
    return rx.box(
        container(
            rx.hstack(
                rx.link(
                    rx.hstack(
                        rx.image(
                            src=rx.color_mode_cond(
                                "/icons/light.svg", "/icons/dark.svg"
                            ),
                            alt="",
                            width=rx.breakpoints(initial="5rem", md="7rem"),
                            height="auto",
                        ),
                        rx.heading(
                            "SLIPSTREAM",
                            as_="h2",
                            size=rx.breakpoints(initial="5", md="7"),
                            weight="bold",
                        ),
                        align="center",
                        spacing=rx.breakpoints(initial="2", md="3"),
                    ),
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
                        "RESULTS", "flag", "/results", active_section == "results"
                    ),
                    navbar_icon_item(
                        "DRIVERS", "trophy", "/drivers", active_section == "drivers"
                    ),
                    navbar_icon_item(
                        "TEAMS", "users", "/constructors", active_section == "teams"
                    ),
                    rx.color_mode.button(
                        allow_system=True,
                        size="2",
                        variant="ghost",
                        aria_label="Choose color theme",
                        title="Choose color theme",
                        style={
                            "align_self": "center",
                            "display": "flex",
                            "align_items": "center",
                            "justify_content": "center",
                        },
                    ),
                    spacing=rx.breakpoints(initial="1", md="4"),
                    align="center",
                ),
                justify="between",
                align="center",
                width="100%",
            ),
        ),
        # Use a near-background surface and a fine edge to distinguish the sticky bar.
        bg=rx.color("gray", 2),
        border_bottom_width="1px",
        border_bottom_style="solid",
        border_bottom_color=rx.color("gray", 4),
        width="100%",
        position="sticky",
        top="0",
        z_index="10",
    )
