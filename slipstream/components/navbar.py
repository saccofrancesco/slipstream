# Importing libraries
import reflex as rx


# Single navbar icon item
def navbar_icon_item(text: str, icon: str, url: str) -> rx.Component:
    return rx.link(
        rx.hstack(rx.icon(icon), rx.text(text, size="4", weight="medium")), href=url
    )


# Full navbar component to be displayed in all pages
def navbar() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.heading("Slipstream", as_="h2", size="7", weight="bold"),
            rx.hstack(
                navbar_icon_item("Drivers", "trophy", "/drivers"),
                navbar_icon_item("Teams", "users", "/#"),
                spacing="6",
            ),
            justify="between",
            align="center",
            width="100%",
        ),
        padding_y="1em",
        width="100%",
        position="sticky",
        top="0",
        z_index="10",
    )
