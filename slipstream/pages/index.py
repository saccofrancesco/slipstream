# Importing libraries and components
import reflex as rx
from slipstream.components import navbar


# Defining the index default page
@rx.page("/", "Home")
def index() -> rx.Component:
    return navbar()
