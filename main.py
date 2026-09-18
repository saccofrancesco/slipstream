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

def varint_field(field_number: int, value: int) -> bytes:
    """
    Encode a protobuf field whose value uses the varint wire type
    """
    # Protobuf encodes the field number and wire type together.
    # Wire type 0 represents a varint, so shifting by 3 is sufficient.
    field_key: int = field_number << 3

    # Encode the field key, followed by the actual integer value.
    return varint(field_key) + varint(value)

def bytes_field(field_number: int, value: bytes) -> bytes:
    """
    Encode a protobuf length-delimited bytes field
    """
    # Wire type 2 means the field contains length-delimited data.
    field_key: int = (field_number << 3) | 2

    # Protobuf stores: field key, payload length, then payload bytes.
    return varint(field_key) + varint(len(value)) + value

def string_field(field_number: int, value: str) -> bytes:
    """Encode a protobuf string field as UTF-8 bytes."""
    # Protobuf strings are length-delimited fields.
    # Convert the Python string to UTF-8, then reuse the bytes-field encoder.
    encoded_value: bytes = value.encode("utf-8")
    return bytes_field(field_number, encoded_value)

def message_field(field_number: int, value: bytes) -> bytes:
    """
    Encode a nested protobuf message field
    """
    # A nested message is serialized as bytes.
    # Reuse the bytes-field encoder because messages use wire type 2
    # (length-delimited).
    return bytes_field(field_number, value)

def airport(code: str) -> bytes:
    """
    Encode an airport as a protobuf message
    """
    # Field 1 marks this as an exact airport rather than a broader location.
    exact_airport_marker: bytes = varint_field(1, 1)

    # Field 2 stores the airport's IATA code, such as "MXP".
    iata_code: bytes = string_field(2, code)

    # Combine both encoded fields into the airport message.
    return exact_airport_marker + iata_code
