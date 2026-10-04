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


def page_header(eyebrow: str, title: str, description: str) -> rx.Component:
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
