"""Interactive collection of Google Flights search parameters"""

from __future__ import annotations

from .flights import (
    CABIN_VALUES,
    FlightSearch,
    LegFilters,
    airport_code,
    airline_code,
    encode_tfs,
    parse_date,
)


def prompt_airport(label: str) -> str:
    """Read and validate an IATA airport code"""
    while True:
        # Keep asking until the user enters a valid three-letter airport code
        value: str = input(f"{label} airport (IATA code): ").strip()
        try:
            return airport_code(value, label.lower())
        except ValueError as exc:
            print(f"Invalid airport: {exc}")


def prompt_date_value(label: str, *, optional: bool = False) -> str | None:
    """Read a date in strict YYYY-MM-DD format"""
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
    """Read a passenger count with a default and lower bound"""
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


def prompt_optional_nonnegative_int(label: str) -> int | None:
    """Read an optional non-negative integer; blank disables the filter"""
    # Keep asking until the user provides valid input
    while True:
        # Display the prompt and remove surrounding whitespace
        value: str = input(f"{label} [none]: ").strip()

        # An empty response means that this filter is disabled
        if not value:
            return None

        try:
            # Convert the input text into an integer
            number: int = int(value)
        except ValueError:
            # Handle text or other values that cannot be converted to an integer
            print("Please enter a whole number or leave it blank.")
            continue

        # Negative numbers are not allowed
        if number < 0:
            print("Please enter a non-negative number.")
            continue

        # Return the validated non-negative integer
        return number


def prompt_optional_hour(label: str) -> int | None:
    """Read an optional local-time hour between 0 and 23"""
    # Keep asking until the user provides a valid hour or leaves it blank
    while True:
        # Reuse the helper that handles blank and negative values
        hour: int | None = prompt_optional_nonnegative_int(label)

        # None disables the filter; otherwise accept hours from 0 to 23
        if hour is None or hour <= 23:
            return hour

        # Reject values outside the 24-hour clock range
        print("Please enter an hour from 0 through 23.")


def prompt_code_list(label: str, *, airport_codes: bool = False) -> tuple[str, ...]:
    """Read a comma-separated list of IATA airport or airline codes"""
    # Keep asking until all entered codes are valid
    while True:
        # Read the user's input and remove surrounding whitespace
        value: str = input(f"{label} [none]: ").strip()

        # An empty response means that no codes were selected
        if not value:
            return ()

        # Split on commas, trim each item, and normalize to uppercase
        codes: tuple[str, ...] = tuple(
            part.strip().upper() for part in value.split(",") if part.strip()
        )

        try:
            if airport_codes:
                # Validate every item as a three-letter airport code
                for code in codes:
                    airport_code(code, label)
            else:
                # Validate every item as a two-character airline code
                for code in codes:
                    airline_code(code, label)

        except ValueError as exc:
            # Display the validation error and ask for the input again
            print(f"Invalid code: {exc}")
            continue

        # Return the validated, normalized codes
        return codes


def prompt_leg_filters() -> LegFilters:
    """Collect the filters stored by Google inside each flight leg"""
    # Ask for the maximum number of stops
    # A blank response means that no stops filter is applied
    while True:
        max_stops: int | None = prompt_optional_nonnegative_int(
            "Maximum stops (0=nonstop, 1, or 2)"
        )

        # Accept no filter or a maximum of two stops
        if max_stops is None or max_stops <= 2:
            break

        # Ask again when the value is outside the supported range
        print("Please enter 0, 1, 2, or leave it blank.")

    # Read the allowed departure and arrival time ranges
    departure_start_hour: int | None = prompt_optional_hour(
        "Earliest departure hour, local time (0-23)"
    )
    departure_end_hour: int | None = prompt_optional_hour(
        "Latest departure hour, local time (0-23)"
    )
    arrival_start_hour: int | None = prompt_optional_hour(
        "Earliest arrival hour, local time (0-23)"
    )
    arrival_end_hour: int | None = prompt_optional_hour(
        "Latest arrival hour, local time (0-23)"
    )

    # Ensure the departure start is not later than the departure end
    while (
        departure_start_hour is not None
        and departure_end_hour is not None
        and departure_start_hour > departure_end_hour
    ):
        print(
            "Departure start cannot be after departure end; " "please enter them again."
        )

        departure_start_hour = prompt_optional_hour(
            "Earliest departure hour, local time (0-23)"
        )
        departure_end_hour = prompt_optional_hour(
            "Latest departure hour, local time (0-23)"
        )

    # Ensure the arrival start is not later than the arrival end
    while (
        arrival_start_hour is not None
        and arrival_end_hour is not None
        and arrival_start_hour > arrival_end_hour
    ):
        print("Arrival start cannot be after arrival end; " "please enter them again.")

        arrival_start_hour = prompt_optional_hour(
            "Earliest arrival hour, local time (0-23)"
        )
        arrival_end_hour = prompt_optional_hour(
            "Latest arrival hour, local time (0-23)"
        )

    # Ask whether the user wants to restrict results to lower-emission flights
    emissions_value: str = input("Only lower-emission flights? [y/N]: ").strip().lower()

    # Treat "y" and "yes" as enabling the emissions filter
    less_emissions_only: bool = emissions_value in {"y", "yes"}

    # Build and return the completed LegFilters object
    return LegFilters(
        max_stops=max_stops,
        # Ask which airlines should be included or excluded
        include_airlines=prompt_code_list("Include airlines (2-letter codes)"),
        exclude_airlines=prompt_code_list("Exclude airlines (2-letter codes)"),
        # Store the departure and arrival time ranges
        departure_start_hour=departure_start_hour,
        departure_end_hour=departure_end_hour,
        arrival_start_hour=arrival_start_hour,
        arrival_end_hour=arrival_end_hour,
        # Ask for the maximum allowed flight duration
        max_duration_minutes=prompt_optional_nonnegative_int(
            "Maximum flight duration in minutes"
        ),
        # Ask which connecting airports should be included or excluded
        include_connecting_airports=prompt_code_list(
            "Include connecting airports (IATA codes)",
            airport_codes=True,
        ),
        exclude_connecting_airports=prompt_code_list(
            "Exclude connecting airports (IATA codes)",
            airport_codes=True,
        ),
        # Store the lower-emissions preference
        less_emissions_only=less_emissions_only,
    )


def prompt_cabin() -> str:
    """Read one of the cabin names supported by the encoder"""
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
    """Collect the fields needed to create a FlightSearch from the terminal"""
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
        # Empty filter answers retain the original broad-search behavior
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
            leg_filters=prompt_leg_filters(),
            max_price=prompt_optional_nonnegative_int("Maximum price"),
            carry_on_bags=prompt_nonnegative_int("Carry-on bags", 0),
            checked_bags=prompt_nonnegative_int("Checked bags", 0),
        )
        try:
            # Validate the complete combination, including passenger limits
            encode_tfs(search)
        except ValueError as exc:
            # Ask for the passenger counts again if the combination is invalid
            print(f"Invalid passenger setup: {exc}")
            continue
        return search
