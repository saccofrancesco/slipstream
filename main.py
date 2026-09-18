# Importing libraries
from __future__ import annotations
import base64
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlencode

# URL hardcoded default constants
GOOGLE_FLIGHTS_SEARCH_URL: str = "https://www.google.com/travel/flights/search"
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


@dataclass(frozen=True)  # Makes instances immutable after creation
class FlightSearch:
    """
    Fields needed for a one-way or round-trip Google Flights search
    """

    origin: str  # Departure airport code, e.g. "MXP"
    destination: str  # Arrival airport code, e.g. "ACE"
    departure_date: str | date  # Departure date as text or a date object
    return_date: str | date | None = None  # Optional return date for round trips
    cabin: str = "economy"  # Travel cabin, such as economy or business
    adults: int = 1  # Number of adult passengers
    children: int = 0  # Number of child passengers
    infants_in_seat: int = 0  # Infants occupying their own seat
    infants_on_lap: int = 0  # Infants traveling on an adult's lap


def varint(value: int) -> bytes:
    """
    Encode an unsigned integer using protobuf's base-128 varint format
    """
    # Accept only values that fit in an unsigned 64-bit integer
    if not 0 <= value <= MAX_UINT64:
        raise ValueError("protobuf varint must be an unsigned 64-bit integer")
    encoded: bytearray = bytearray()

    # Each byte stores 7 bits of the value
    # The high bit indicates that more bytes follow
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)

        # Move to the next group of 7 bits
        value >>= 7

    # Store the final 7 bits with the continuation bit cleared
    encoded.append(value)

    # Convert the mutable bytearray to immutable bytes
    return bytes(encoded)


def varint_field(field_number: int, value: int) -> bytes:
    """
    Encode a protobuf field whose value uses the varint wire type
    """
    # Protobuf encodes the field number and wire type together
    # Wire type 0 represents a varint, so shifting by 3 is sufficient
    field_key: int = field_number << 3

    # Encode the field key, followed by the actual integer value
    return varint(field_key) + varint(value)


def bytes_field(field_number: int, value: bytes) -> bytes:
    """
    Encode a protobuf length-delimited bytes field
    """
    # Wire type 2 means the field contains length-delimited data
    field_key: int = (field_number << 3) | 2

    # Protobuf stores: field key, payload length, then payload bytes
    return varint(field_key) + varint(len(value)) + value


def string_field(field_number: int, value: str) -> bytes:
    """Encode a protobuf string field as UTF-8 bytes"""
    # Protobuf strings are length-delimited fields
    # Convert the Python string to UTF-8, then reuse the bytes-field encoder
    encoded_value: bytes = value.encode("utf-8")
    return bytes_field(field_number, encoded_value)


def message_field(field_number: int, value: bytes) -> bytes:
    """
    Encode a nested protobuf message field
    """
    # A nested message is serialized as bytes
    # Reuse the bytes-field encoder because messages use wire type 2
    # (length-delimited)
    return bytes_field(field_number, value)


def airport(code: str) -> bytes:
    """
    Encode an airport as a protobuf message
    """
    # Field 1 marks this as an exact airport rather than a broader location
    exact_airport_marker: bytes = varint_field(1, 1)

    # Field 2 stores the airport's IATA code, such as "MXP"
    iata_code: bytes = string_field(2, code)

    # Combine both encoded fields into the airport message
    return exact_airport_marker + iata_code


def flight_leg(day: date, origin: str, destination: str) -> bytes:
    """
    Encode one flight leg as a protobuf message
    """
    # Field 2 stores the travel date in ISO-8601 format, e.g. "2026-09-18"
    travel_date: bytes = string_field(2, day.isoformat())

    # Fields 13 and 14 store the origin and destination airport messages
    origin_airport: bytes = message_field(13, airport(origin))
    destination_airport: bytes = message_field(14, airport(destination))

    # Combine the date, origin, and destination fields
    return travel_date + origin_airport + destination_airport


def airport_code(value: str, name: str) -> str:
    """
    Validate and normalize a three-letter IATA airport code
    """
    # Reject values that are not strings
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a three-letter IATA airport code")

    # Remove surrounding whitespace and normalize to uppercase
    code: str = value.strip().upper()

    # Ensure the code contains exactly three uppercase letters
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError(f"{name} must be a three-letter IATA airport code")

    return code


def parse_date(value: str | date, name: str) -> date:
    """
    Parse a value as a strict YYYY-MM-DD date
    """

    # datetime is a subclass of date, so reject it explicitly first
    if isinstance(value, datetime):
        raise ValueError(f"{name} must be a date, not a datetime")

    # Date objects can be returned directly
    if isinstance(value, date):
        return value

    # All other values must be strings
    if not isinstance(value, str):
        raise ValueError(f"{name} must use YYYY-MM-DD format")
    try:
        # Parse the string using ISO-8601 date syntax
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD format") from exc

    # Ensure the input used the exact canonical YYYY-MM-DD representation
    if parsed.isoformat() != value:
        raise ValueError(f"{name} must use YYYY-MM-DD format")

    return parsed


def encode_tfs(search: FlightSearch) -> str:
    """
    Encode a FlightSearch as Google Flights' URL-safe ``tfs`` value
    """

    # Normalize and validate the departure and arrival airport codes
    origin: str = airport_code(search.origin, "origin")
    destination: str = airport_code(search.destination, "destination")

    # A flight cannot depart from and arrive at the same airport
    if origin == destination:
        raise ValueError("origin and destination must be different airports")

    # Parse and validate the departure date
    departure: date = parse_date(search.departure_date, "departure_date")

    # Parse the return date when this is a round-trip search
    returning: date | None = (
        parse_date(search.return_date, "return_date")
        if search.return_date is not None
        else None
    )

    # A return flight cannot occur before the departure flight
    if returning is not None and returning < departure:
        raise ValueError("return_date cannot be before departure_date")

    # Normalize the cabin name so inputs like "Premium Economy" work
    # consistently with the values used by the protobuf payload
    cabin: str = search.cabin.strip().lower().replace(" ", "-").replace("_", "-")

    # Ensure the cabin is supported by the encoder
    if cabin not in CABIN_VALUES:
        choices: str = ", ".join(CABIN_VALUES)
        raise ValueError(f"cabin must be one of: {choices}")

    # Group passenger categories with their requested counts
    passenger_counts: tuple[tuple[str, int]] = (
        ("adults", search.adults),
        ("children", search.children),
        ("infants_in_seat", search.infants_in_seat),
        ("infants_on_lap", search.infants_on_lap),
    )

    # Validate that every passenger count is a non-negative integer
    # bool is rejected explicitly because bool is a subclass of int in Python
    for name, count in passenger_counts:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"{name} must be a non-negative integer")

    # Apply the passenger constraints supported by Google Flights
    total_passengers: int = sum(count for _, count in passenger_counts)

    if search.adults < 1:
        raise ValueError("at least one adult is required")
    if total_passengers > 9:
        raise ValueError("Google Flights searches support at most 9 passengers")
    if search.infants_on_lap > search.adults:
        raise ValueError("infants_on_lap cannot exceed the number of adults")

    # These envelope fields and the all-results sentinel appear in the
    # reference URL. Their meanings are not part of Google's public contract
    payload: bytearray = bytearray(varint_field(1, 28) + varint_field(2, 2))

    # Field 3 contains the outbound flight leg
    payload.extend(message_field(3, flight_leg(departure, origin, destination)))

    # A return leg is encoded as another field 3 message with the airports
    # reversed, representing the journey back to the origin
    if returning is not None:
        payload.extend(message_field(3, flight_leg(returning, destination, origin)))

    # Encode each passenger as a repeated field 8 entry
    for name, count in passenger_counts:
        passenger_value: int = PASSENGER_VALUES[name]
        for _ in range(count):
            payload.extend(varint_field(8, passenger_value))

    # Encode the selected cabin
    payload.extend(varint_field(9, CABIN_VALUES[cabin]))

    # Add reference-payload marker fields
    payload.extend(varint_field(14, 1))
    payload.extend(message_field(16, varint_field(1, MAX_UINT64)))

    # Mark the search as round-trip or one-way
    payload.extend(varint_field(19, 1 if returning is not None else 2))

    # Encode the protobuf bytes using URL-safe Base64
    # Google Flights' token omits trailing Base64 padding characters
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def build_google_flights_url(
    search: FlightSearch,
    *,
    language: str | None = None,
    currency: str | None = None,
    tfu: str | None = DEFAULT_TFU,
) -> str:
    """
    Return a scrapable Google Flights search URL for ``search``
    ``tfu`` defaults to the companion value in the supplied example. Set it to
    ``None`` to omit it. Language (``hl``) and display currency (``curr``) are
    optional URL parameters
    """

    # Encode the flight search as the required Google Flights ``tfs`` parameter
    params: list[tuple[str, str]] = [("tfs", encode_tfs(search))]

    # Include the optional ``tfu`` parameter unless explicitly omitted
    if tfu is not None:
        params.append(("tfu", tfu))

    # Add the optional interface language parameter
    if language:
        params.append(("hl", language))

    # Add the optional display-currency parameter in uppercase form
    if currency:
        params.append(("curr", currency.upper()))

    # URL-encode all parameters and append them to the Google Flights URL
    return f"{GOOGLE_FLIGHTS_SEARCH_URL}?{urlencode(params)}"


def prompt_airport(label: str) -> str:
    """
    Read and validate an IATA airport code
    """
    while True:
        # Keep asking until the user enters a valid three-letter airport code
        value: str = input(f"{label} airport (IATA code): ").strip()
        try:
            return airport_code(value, label.lower())
        except ValueError as exc:
            print(f"Invalid airport: {exc}")


def prompt_date_value(label: str, *, optional: bool = False) -> str | None:
    """
    Read a date in strict YYYY-MM-DD format
    """
    while True:
        # An empty return date means that the search is one-way
        optional_hint: str = ", leave blank for one-way" if optional else ""
        value: str = input(f"{label} (YYYY-MM-DD{optional_hint}): ").strip()
        if optional and not value:
            return None
        try:
            return parse_date(value, label.lower()).isoformat()
        except ValueError as exc:
            print(f"Invalid date: {exc}")


def prompt_nonnegative_int(label: str, default: int, *, minimum: int = 0) -> int:
    """
    Read a passenger count with a default and lower bound
    """
    while True:
        # Passenger fields use sensible defaults so the first test is quick
        value: str = input(f"{label} [{default}]: ").strip()
        if not value:
            return default
        try:
            count: int = int(value)
        except ValueError:
            print("Please enter a whole number.")
            continue
        if count < minimum:
            print(f"Please enter a number greater than or equal to {minimum}.")
            continue
        return count


def prompt_cabin() -> str:
    """
    Read one of the cabin names supported by the encoder
    """
    # Use the same cabin names as the existing protobuf encoder
    choices: str = ", ".join(CABIN_VALUES)
    while True:
        value: str = input(f"Cabin ({choices}) [economy]: ").strip()
        cabin: str = value or "economy"
        cabin: str = cabin.lower().replace(" ", "-").replace("_", "-")
        if cabin in CABIN_VALUES:
            return cabin
        print(f"Please choose one of: {choices}.")


def collect_flight_search() -> FlightSearch:
    """
    Collect the fields needed to create a FlightSearch from the terminal
    """
    # Collect and normalize the route before asking for the remaining fields
    origin: str = prompt_airport("Origin")
    while True:
        destination: str = prompt_airport("Destination")
        if destination != origin:
            break
        print("Origin and destination must be different airports.")

    # The departure date is required; the return date is optional
    departure_value: str | None = prompt_date_value("Departure date")
    assert departure_value is not None
    departure_date: str = departure_value
    while True:
        return_date: str | None = prompt_date_value("Return date", optional=True)
        if return_date is None or return_date >= departure_date:
            break
        print("Return date cannot be before departure date.")
    cabin: str = prompt_cabin()
    while True:
        # Build the immutable search object from all collected user input
        search: FlightSearch = FlightSearch(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            cabin=cabin,
            adults=prompt_nonnegative_int("Adults", 1, minimum=1),
            children=prompt_nonnegative_int("Children", 0),
            infants_in_seat=prompt_nonnegative_int("Infants in own seat", 0),
            infants_on_lap=prompt_nonnegative_int("Infants on lap", 0),
        )
        try:
            # Validate the complete combination, including passenger limits
            encode_tfs(search)
        except ValueError as exc:
            # Ask for the passenger counts again if the combination is invalid
            print(f"Invalid passenger setup: {exc}")
            continue
        return search


def main() -> None:
    """
    Collect a search and print its generated Google Flights URL
    """
    # Gather the user's search criteria and create a FlightSearch instance
    search: FlightSearch = collect_flight_search()

    # Encode the search and generate the final link for manual testing
    link: str = build_google_flights_url(search)

    # Print the URL so the user can compare the result
    print("\nGenerated Google Flights link:")
    print(link)


if __name__ == "__main__":
    main()
