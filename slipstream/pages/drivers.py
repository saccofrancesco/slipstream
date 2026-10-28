"""Driver championship route and its page-specific state."""

from typing import ClassVar, Literal

import reflex as rx

from slipstream.components.championship import championship_page

from .championship import ChampionshipState


class DriversState(ChampionshipState, rx.State):
    """Configure shared championship loading for driver standings."""

    championship_kind: ClassVar[Literal["driver"]] = "driver"


@rx.page("/drivers", "Drivers", on_load=DriversState.load_standings)
def drivers() -> rx.Component:
    """Render the latest driver championship standings."""
    return championship_page(
        DriversState.podium_standings,
        DriversState.remaining_standings,
        DriversState.has_remaining_standings,
        DriversState.standings.length() > 0,
        DriversState.loading,
        DriversState.error,
        active_section="drivers",
        eyebrow="Driver championship",
        title="Drivers’ Championship",
        description="Latest driver championship standings.",
        is_driver=True,
    )
