# Exposing the service function to populate the UI with data
from .api import get_constructor_standings, get_driver_standings

__all__ = ["get_constructor_standings", "get_driver_standings"]
