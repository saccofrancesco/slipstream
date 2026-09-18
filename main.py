# Importing libraries
from src.cli import collect_flight_search
from src.flights import FlightSearch, build_google_flights_url


def main() -> None:
    """Collect a search and print its generated Google Flights URL"""
    # Gather the user's search criteria and create a FlightSearch instance
    search: FlightSearch = collect_flight_search()

    # Encode the search and generate the final link for manual testing
    link: str = build_google_flights_url(search)

    # Print the URL so the user can compare the result
    print("\nGenerated Google Flights link:")
    print(link)


if __name__ == "__main__":
    main()
