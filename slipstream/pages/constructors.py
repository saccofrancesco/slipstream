"""Constructor championship route and its page-specific state."""

from typing import ClassVar, Literal

import reflex as rx

from slipstream.components.championship import championship_page

from .championship import ChampionshipState


class ConstructorsState(ChampionshipState):
    """Configure shared championship loading for constructor standings."""

    championship_kind: ClassVar[Literal["constructor"]] = "constructor"
    minimum_season: ClassVar[int] = 1958


@rx.page("/constructors", "Teams", on_load=ConstructorsState.load_standings)
def constructors() -> rx.Component:
    """Render the latest constructor championship standings."""
    return championship_page(
        ConstructorsState.podium_standings,
        ConstructorsState.remaining_standings,
        ConstructorsState.has_remaining_standings,
        ConstructorsState.has_standings,
        ConstructorsState.loading,
        ConstructorsState.error,
        active_section="teams",
        eyebrow="Team championship",
        title="Teams’ Championship",
        description="Latest team championship standings.",
        is_driver=False,
    )
