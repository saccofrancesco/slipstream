"""Redirect the root route to the driver championship."""

import reflex as rx
from reflex.event import EventSpec


class RootRedirectState(rx.State):
    """Handle visits to the root route."""

    @rx.event
    def redirect_to_drivers(self) -> EventSpec:
        """Send visitors from the root route to the driver standings."""
        return rx.redirect("/drivers")


@rx.page(route="/", on_load=RootRedirectState.redirect_to_drivers)
def root_redirect() -> rx.Component:
    """Render no landing-page content while the redirect runs."""
    return rx.fragment()
