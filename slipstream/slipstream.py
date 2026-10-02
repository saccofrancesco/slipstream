"""Create the main Slipstream Reflex application."""

# Reflex provides the application factory.
import reflex as rx

# Import pages so their ``@rx.page`` declarations register with the app.
import slipstream.pages

# Create the Reflex application instance.
app: rx.App = rx.App()
