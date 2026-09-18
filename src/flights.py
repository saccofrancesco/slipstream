# Importing libraries
from __future__ import annotations
import base64
import re
from dataclasses import dataclass, field
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
class LegFilters:
    """Optional Google Flights filters that apply to one flight leg"""

    max_stops: int | None = (
        None  # Maximum allowed stops: 0 = nonstop, 1 = one stop or fewer, etc
    )
    include_airlines: tuple[str, ...] = ()  # Airline codes that must be included
    exclude_airlines: tuple[str, ...] = ()  # Airline codes that must be excluded
    departure_start_hour: int | None = (
        None  # Earliest permitted departure hour, from 0 to 23
    )
    departure_end_hour: int | None = (
        None  # Latest permitted departure hour, from 0 to 23
    )
    arrival_start_hour: int | None = (
        None  # Earliest permitted arrival hour, from 0 to 23
    )
    arrival_end_hour: int | None = None  # Latest permitted arrival hour, from 0 to 23
    max_duration_minutes: int | None = None  # Maximum total duration of the flight leg
    include_connecting_airports: tuple[
        str, ...
    ] = ()  # Connection airports that must be used
    exclude_connecting_airports: tuple[
        str, ...
    ] = ()  # Connection airports that must not be used
    less_emissions_only: bool = (
        False  # When True, request flights with lower estimated emissions
    )


@dataclass(frozen=True)  # Makes instances immutable after creation
class FlightSearch:
    """Fields needed for a one-way or round-trip Google Flights search"""

    origin: str  # Departure airport code, e.g. "MXP"
    destination: str  # Arrival airport code, e.g. "ACE"
    departure_date: str | date  # Departure date as text or a date object
    return_date: str | date | None = None  # Optional return date for round trips
    cabin: str = "economy"  # Travel cabin, such as economy or business
    adults: int = 1  # Number of adult passengers
    children: int = 0  # Number of child passengers
    infants_in_seat: int = 0  # Infants occupying their own seat
    infants_on_lap: int = 0  # Infants traveling on an adult's lap
    leg_filters: LegFilters = field(default_factory=LegFilters)
    return_leg_filters: LegFilters | None = (
        None  # Optional filters specific to the return leg; if omitted, the outbound leg filters are reused
    )
    max_price: int | None = (
        None  # Maximum ticket price allowed; None means no maximum price filter
    )
    carry_on_bags: int = (
        0  # Number of carry-on bags whose estimated fees should be included; 0 means no carry-on bag filter
    )
    checked_bags: int = (
        0  # Number of checked bags whose estimated fees should be included; 0 means no checked-bag filter
    )


def varint(value: int) -> bytes:
    """Encode an unsigned integer using protobuf's base-128 varint format"""
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
    """Encode a protobuf field whose value uses the varint wire type"""
    # Protobuf encodes the field number and wire type together
    # Wire type 0 represents a varint, so shifting by 3 is sufficient
    field_key: int = field_number << 3

    # Encode the field key, followed by the actual integer value
    return varint(field_key) + varint(value)


def bytes_field(field_number: int, value: bytes) -> bytes:
    """Encode a protobuf length-delimited bytes field"""
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
    """Encode a nested protobuf message field"""
    # A nested message is serialized as bytes
    # Reuse the bytes-field encoder because messages use wire type 2
    # (length-delimited)
    return bytes_field(field_number, value)


def airport(code: str) -> bytes:
    """Encode an airport as a protobuf message"""
    # Field 1 marks this as an exact airport rather than a broader location
    exact_airport_marker: bytes = varint_field(1, 1)

    # Field 2 stores the airport's IATA code, such as "MXP"
    iata_code: bytes = string_field(2, code)

    # Combine both encoded fields into the airport message
    return exact_airport_marker + iata_code


def flight_leg(
    day: date, origin: str, destination: str, filters: LegFilters | None = None
) -> bytes:
    """Encode one flight leg as a protobuf message"""
    # Field 2 stores the travel date in ISO-8601 format, e.g. "2026-09-18"
    encoded: bytearray = bytearray(string_field(2, day.isoformat()))

    # Google uses presence-sensitive fields for these leg filters. In
    # particular, max_stops=0 means nonstop, while an omitted field means no
    # stops filter
    if filters is not None:
        if filters.max_stops is not None:
            encoded.extend(varint_field(5, filters.max_stops))
        for airline in filters.include_airlines:
            encoded.extend(string_field(6, airline))
        for airline in filters.exclude_airlines:
            encoded.extend(string_field(7, airline))
        if filters.departure_start_hour is not None:
            encoded.extend(varint_field(8, filters.departure_start_hour))
        if filters.departure_end_hour is not None:
            encoded.extend(varint_field(9, filters.departure_end_hour))
        if filters.arrival_start_hour is not None:
            encoded.extend(varint_field(10, filters.arrival_start_hour))
        if filters.arrival_end_hour is not None:
            encoded.extend(varint_field(11, filters.arrival_end_hour))
        if filters.max_duration_minutes is not None:
            encoded.extend(varint_field(12, filters.max_duration_minutes))

    # Fields 13 and 14 store the origin and destination airport messages
    origin_airport: bytes = message_field(13, airport(origin))
    destination_airport: bytes = message_field(14, airport(destination))

    # Connection-airport filters are repeated strings in the leg message
    if filters is not None:
        encoded.extend(origin_airport)
        encoded.extend(destination_airport)
        for airport_code_value in filters.include_connecting_airports:
            encoded.extend(string_field(15, airport_code_value))
        for airport_code_value in filters.exclude_connecting_airports:
            encoded.extend(string_field(16, airport_code_value))
        if filters.less_emissions_only:
            # Repeated enum values are packed as a length-delimited field
            encoded.extend(bytes_field(19, varint(1)))
    else:
        # Keep the original no-filter wire layout byte-for-byte compatible
        encoded.extend(origin_airport)
        encoded.extend(destination_airport)

    return bytes(encoded)


def airport_code(value: str, name: str) -> str:
    """Validate and normalize a three-letter IATA airport code"""
    # Reject values that are not strings
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a three-letter IATA airport code")

    # Remove surrounding whitespace and normalize to uppercase
    code: str = value.strip().upper()

    # Ensure the code contains exactly three uppercase letters
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError(f"{name} must be a three-letter IATA airport code")

    return code


def airline_code(value: str, name: str) -> str:
    """Validate and normalize a two-character airline designator"""
    # Ensure the input is a string
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a two-character airline code")

    # Remove surrounding whitespace and convert the code to uppercase
    code: str = value.strip().upper()

    # Accept exactly two letters or digits, such as "AZ", "BA", or "4Y"
    if not re.fullmatch(r"[A-Z0-9]{2}", code):
        raise ValueError(f"{name} must be a two-character airline code")

    # Return the normalized airline code
    return code


def nonnegative_int(value: object, name: str) -> int:
    """Validate a non-negative integer while rejecting booleans"""
    # Reject booleans because bool is a subclass of int in Python
    # Also reject non-integers and negative values
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")

    # Return the validated integer
    return value


def normalize_codes(
    values: tuple[str, ...] | list[str], name: str, validator: object
) -> tuple[str, ...]:
    """Validate, normalize, and return airport or airline codes as a tuple"""
    # Reject a single string because the function expects a collection of codes
    # Otherwise, iterating over a string would process it character by character
    if isinstance(values, str):
        raise ValueError(f"{name} must be a sequence of codes")

    # Store the validation function in a local variable
    validate: object = validator

    # Collect each validated and normalized code
    normalized: list[str] = list()
    for value in values:
        normalized.append(validate(value, name))  # type: ignore[operator]

    # Return an immutable tuple of normalized codes
    return tuple(normalized)


def normalize_leg_filters(filters: LegFilters, name: str = "leg_filters") -> LegFilters:
    """Validate and normalize a leg's filter values before encoding"""
    # Read the maximum-stops filter
    max_stops: int | None = filters.max_stops

    if max_stops is not None:
        # Ensure the value is a non-negative integer
        max_stops = nonnegative_int(max_stops, f"{name}.max_stops")

        # Google Flights supports 0, 1, or 2 stops maximum
        if max_stops > 2:
            raise ValueError(f"{name}.max_stops must be 0, 1, or 2")

    # Group all time filters so they can share the same validation logic
    hours: tuple[tuple[str, int | None], ...] = (
        ("departure_start_hour", filters.departure_start_hour),
        ("departure_end_hour", filters.departure_end_hour),
        ("arrival_start_hour", filters.arrival_start_hour),
        ("arrival_end_hour", filters.arrival_end_hour),
    )

    # Validate every provided hour
    for hour_name, hour in hours:
        if hour is not None:
            nonnegative_int(hour, f"{name}.{hour_name}")

            # Hours must use the 24-hour clock
            if hour > 23:
                raise ValueError(f"{name}.{hour_name} must be between 0 and 23")

    # Ensure the departure time range is logically ordered
    if (
        filters.departure_start_hour is not None
        and filters.departure_end_hour is not None
        and filters.departure_start_hour > filters.departure_end_hour
    ):
        raise ValueError(f"{name} departure start cannot be after departure end")

    # Ensure the arrival time range is logically ordered
    if (
        filters.arrival_start_hour is not None
        and filters.arrival_end_hour is not None
        and filters.arrival_start_hour > filters.arrival_end_hour
    ):
        raise ValueError(f"{name} arrival start cannot be after arrival end")

    # Validate the maximum flight duration when provided
    max_duration_minutes: int | None = filters.max_duration_minutes
    if max_duration_minutes is not None:
        max_duration_minutes = nonnegative_int(
            max_duration_minutes,
            f"{name}.max_duration_minutes",
        )

    # Normalize and validate the included airline codes
    include_airlines: tuple[str, ...] = normalize_codes(
        filters.include_airlines,
        f"{name}.include_airlines",
        airline_code,
    )

    # Normalize and validate the excluded airline codes
    exclude_airlines: tuple[str, ...] = normalize_codes(
        filters.exclude_airlines,
        f"{name}.exclude_airlines",
        airline_code,
    )

    # Normalize and validate airports that must be used as connections
    include_connecting_airports: tuple[str, ...] = normalize_codes(
        filters.include_connecting_airports,
        f"{name}.include_connecting_airports",
        airport_code,
    )

    # Normalize and validate airports that must not be used as connections
    exclude_connecting_airports: tuple[str, ...] = normalize_codes(
        filters.exclude_connecting_airports,
        f"{name}.exclude_connecting_airports",
        airport_code,
    )

    # Explicitly require a boolean for the emissions filter
    if not isinstance(filters.less_emissions_only, bool):
        raise ValueError(f"{name}.less_emissions_only must be a boolean")

    # Return a new LegFilters object containing validated values
    return LegFilters(
        max_stops=max_stops,
        include_airlines=include_airlines,
        exclude_airlines=exclude_airlines,
        departure_start_hour=filters.departure_start_hour,
        departure_end_hour=filters.departure_end_hour,
        arrival_start_hour=filters.arrival_start_hour,
        arrival_end_hour=filters.arrival_end_hour,
        max_duration_minutes=max_duration_minutes,
        include_connecting_airports=include_connecting_airports,
        exclude_connecting_airports=exclude_connecting_airports,
        less_emissions_only=filters.less_emissions_only,
    )


def parse_date(value: str | date, name: str) -> date:
    """Parse a value as a strict YYYY-MM-DD date"""
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
    """Encode a FlightSearch as Google Flights' URL-safe ``tfs`` value"""
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

    # Normalize optional filters once so the wire encoder only receives
    # canonical airport, airline, hour, and duration values
    outbound_filters: LegFilters = normalize_leg_filters(search.leg_filters)
    return_filters: LegFilters | None = None
    if search.return_leg_filters is not None:
        if returning is None:
            raise ValueError("return_leg_filters requires a return_date")
        return_filters = normalize_leg_filters(
            search.return_leg_filters, "return_leg_filters"
        )
    elif returning is not None:
        # A single filter set is convenient for callers and applies to both
        # legs unless a separate return_leg_filters value is supplied
        return_filters = outbound_filters

    max_price: int | None = search.max_price
    if max_price is not None:
        max_price = nonnegative_int(max_price, "max_price")
    carry_on_bags: int = nonnegative_int(search.carry_on_bags, "carry_on_bags")
    checked_bags: int = nonnegative_int(search.checked_bags, "checked_bags")

    # Bag fees can be calculated for each traveler with a seat. Infants on lap
    # do not have their own bag allowance in Google's UI
    bag_eligible_passengers: int = (
        search.adults + search.children + search.infants_in_seat
    )
    if carry_on_bags > bag_eligible_passengers:
        raise ValueError("carry_on_bags cannot exceed passengers with a seat")
    if checked_bags > bag_eligible_passengers:
        raise ValueError("checked_bags cannot exceed passengers with a seat")

    # These envelope fields and the all-results sentinel appear in the
    # reference URL. Their meanings are not part of Google's public contract
    payload: bytearray = bytearray(varint_field(1, 28) + varint_field(2, 2))

    # Field 3 contains the outbound flight leg
    payload.extend(
        message_field(
            3,
            flight_leg(departure, origin, destination, outbound_filters),
        )
    )

    # A return leg is encoded as another field 3 message with the airports
    # reversed, representing the journey back to the origin
    if returning is not None:
        assert return_filters is not None
        payload.extend(
            message_field(
                3,
                flight_leg(returning, destination, origin, return_filters),
            )
        )

    # Encode each passenger as a repeated field 8 entry
    for name, count in passenger_counts:
        passenger_value: int = PASSENGER_VALUES[name]
        for _ in range(count):
            payload.extend(varint_field(8, passenger_value))

    # Encode the selected cabin
    payload.extend(varint_field(9, CABIN_VALUES[cabin]))

    # Search-wide price and baggage filters follow the same protobuf envelope
    # used by Google-generated URLs
    if max_price is not None:
        payload.extend(varint_field(12, max_price))
    if carry_on_bags or checked_bags:
        baggage: bytes = varint_field(2, carry_on_bags) + varint_field(3, checked_bags)
        payload.extend(message_field(13, baggage))

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
