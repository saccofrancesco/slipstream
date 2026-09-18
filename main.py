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
