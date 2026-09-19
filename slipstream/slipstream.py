# Importing libraries
import reflex as rx


# Initializing the app's mutable data
class State(rx.State):

    # Creating the actual var which will hold the value
    count: int = 0

    # Setting up the handlers, triggered by user actions, which will change the value of the vars
    @rx.event
    def increment(self):
        self.count += 1

    @rx.event
    def decrement(self):
        self.count -= 1


# Defining the application UI via functions
def index():
    return rx.hstack(
        rx.button(
            "Decrement",
            color_scheme="ruby",
            on_click=State.decrement,
        ),
        rx.heading(State.count, as_="h2", font_size="2em"),
        rx.button(
            "Increment",
            color_scheme="grass",
            on_click=State.increment,
        ),
        spacing="4",
    )


# Initialize the app and register the page at the base route
app = rx.App()
app.add_page(index)
