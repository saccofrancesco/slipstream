# Importing libraries
import reflex as rx


# Main application page component
def index() -> rx.Component:
    return rx.container(
        rx.box(
            "What is Reflex?",
            # The user's question is on the right
            text_align="right",
        ),
        rx.box(
            "A way to build web apps in pure Python!",
            # The answer to the user's question is on the left
            text_align="left",
        ),
    )


# Instanciating the app object and adding the index page as the root
app = rx.App()
app.add_page(index)
