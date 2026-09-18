# Importing libraries
from __future__ import annotations
import base64
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlencode

# URL hardocoded default constants
GOOGLE_FLIGHT_SEARCH_URL: str = "https://www.google.com/travel/flights/search"
DEFAULT_TFU: str = "EgYIABAAGAA"
CABIN_VALUES: dict[str, int] = {
    "economy": 1,
    "premium-economy": 2,
    "business": 3,
    "first": 4,
}
PASSENGER_VALUES: dict[str, int] = {
    "adults": 1,
    "children": 2,
    "infants_in_seat": 3,
    "infants_on_lap": 4,
}
MAX_UINT64: int = (1 << 64) - 1

@dataclass(frozen=True) # Makes instances immutable after creation
class FlightSearch:
    """
    Fields needed for a one-way or round-trip Google Flights search
    """
    origin: str  # Departure airport code, e.g. "MXP".
    destination: str  # Arrival airport code, e.g. "ACE".
    departure_date: str | date  # Departure date as text or a date object.
    return_date: str | date | None = None  # Optional return date for round trips.
    cabin: str = "economy"  # Travel cabin, such as economy or business.
    adults: int = 1  # Number of adult passengers.
    children: int = 0  # Number of child passengers.
    infants_in_seat: int = 0  # Infants occupying their own seat.
    infants_on_lap: int = 0  # Infants traveling on an adult's lap.
