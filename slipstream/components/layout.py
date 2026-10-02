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
