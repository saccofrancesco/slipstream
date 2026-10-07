"""Shared page layout components."""

# Reflex provides the component primitives used by the shared layout.
import reflex as rx


def container(*children: rx.Component) -> rx.Component:
    """Center page content and constrain it to the shared layout width.

    Args:
        *children: Components to place inside the page container.

    Returns:
        A responsive Reflex container holding the supplied components.
    """
    return rx.container(*children, size="4", width="100%", margin_x="auto")


def page_header(
    eyebrow: str | rx.Var[str], title: str, description: str | rx.Var[str]
) -> rx.Component:
    """Build the eyebrow, title, and description at the top of a page.

    Args:
        eyebrow: Short uppercase label above the page title.
        title: Main page heading.
        description: Supporting sentence below the heading.

    Returns:
        A vertically stacked page header component.
    """
    # Group the small label, prominent title, and supporting description.
    return rx.vstack(
        rx.text(
            eyebrow,
            size="2",
            weight="bold",
            color=rx.color("accent", 11),
            letter_spacing="0.16em",
            text_transform="uppercase",
        ),
        rx.heading(
            title,
            as_="h1",
            size="9",
            weight="bold",
            font_size="clamp(2rem, 6vw, 3.5rem)",
            letter_spacing="-0.04em",
            line_height="1.05",
        ),
        rx.text(
            description,
            size="4",
            color=rx.color("gray", 11),
            max_width="42rem",
            line_height="1.6",
        ),
        align="start",
        spacing="2",
        width="100%",
        padding_top="7",
        padding_bottom="2",
    )


def status_card(title: str, message: rx.Var[str] | str) -> rx.Component:
    """Display a loading, empty, or error message in the shared card style."""
    return rx.card(
        rx.hstack(
            rx.box(
                rx.icon("flag", size=20, color=rx.color("accent", 11)),
                padding="3",
                border_radius="full",
                background_color=rx.color("accent", 3),
            ),
            rx.vstack(
                rx.heading(title, size="4", weight="bold"),
                rx.text(message, color=rx.color("gray", 11), line_height="1.5"),
                align="start",
                spacing="1",
                width="100%",
            ),
            align="center",
            spacing="4",
            width="100%",
        ),
        width="100%",
        background_color=rx.color("gray", 2),
        border_width="1px",
        border_style="solid",
        border_color=rx.color("gray", 5),
    )


def loading_card(message: str) -> rx.Component:
    """Show a centered spinner and loading message in the shared card style."""
    return rx.card(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(message, color=rx.color("gray", 11)),
            align="center",
            spacing="3",
            padding_y="8",
            width="100%",
        ),
        width="100%",
        background_color=rx.color("gray", 2),
    )
