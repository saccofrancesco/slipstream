# Importing libraries
from __future__ import annotations
import base64
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlencode

# URL hardcoded default constants
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

def varint(value: int) -> bytes:
    """
    Encode an unsigned integer using protobuf's base-128 varint format
    """
    # Accept only values that fit in an unsigned 64-bit integer.
    if not 0 <= value <= MAX_UINT64:
        raise ValueError("protobuf varint must be an unsigned 64-bit integer")
    encoded: bytearray = bytearray()

    # Each byte stores 7 bits of the value.
    # The high bit indicates that more bytes follow.
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)

        # Move to the next group of 7 bits.
        value >>= 7

    # Store the final 7 bits with the continuation bit cleared.
    encoded.append(value)

    # Convert the mutable bytearray to immutable bytes.
    return bytes(encoded)
