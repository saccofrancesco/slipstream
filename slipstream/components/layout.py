# Importing libraries
import reflex as rx

# Setting up hardcoded dimensions' limits
CONTENT_MAX_WIDTH: str = "75em"
CONTENT_PADDING_X: str = "1.5em"


# Wrapper component for all the content displayed by the app
def content_container(*children: rx.Component) -> rx.Component:
    return rx.box(
        *children,
        width="100%",
        max_width=CONTENT_MAX_WIDTH,
        margin_x="auto",
        padding_x=CONTENT_PADDING_X,
        box_sizing="border-box",
    )
