# Importing libraries
import reflex as rx


# Wrapper component for all the content displayed by the app
def container(*children: rx.Component) -> rx.Component:
    return rx.container(*children, size="4")
