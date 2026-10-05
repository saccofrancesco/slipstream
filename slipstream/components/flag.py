"""Small accessible country-flag indicator for reactive cards."""

import reflex as rx


def flag_icon(flag: rx.Var[str], label: rx.Var[str]) -> rx.Component:
    """Show a flag emoji when one is known, labeled for assistive tools."""
    return rx.cond(
        flag != "",
        rx.text(
            flag,
            role="img",
            aria_label=f"{label} flag",
            font_size="1.1em",
            line_height="1",
            flex_shrink="0",
        ),
        rx.fragment(),
    )
