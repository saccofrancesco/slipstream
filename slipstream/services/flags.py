"""Turn circuit host-country labels into flag emoji."""

CIRCUIT_COUNTRY_CODES: dict[str, str] = {
    "argentina": "AR",
    "australia": "AU",
    "austria": "AT",
    "azerbaijan": "AZ",
    "bahrain": "BH",
    "belgium": "BE",
    "brazil": "BR",
    "canada": "CA",
    "china": "CN",
    "france": "FR",
    "germany": "DE",
    "hungary": "HU",
    "india": "IN",
    "italy": "IT",
    "japan": "JP",
    "korea": "KR",
    "malaysia": "MY",
    "mexico": "MX",
    "monaco": "MC",
    "morocco": "MA",
    "netherlands": "NL",
    "portugal": "PT",
    "qatar": "QA",
    "russia": "RU",
    "saudi arabia": "SA",
    "singapore": "SG",
    "south africa": "ZA",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "turkey": "TR",
    "uae": "AE",
    "uk": "GB",
    "usa": "US",
    "united arab emirates": "AE",
    "united kingdom": "GB",
    "united states": "US",
}


def _flag_for_code(country_code: str) -> str:
    """Encode a two-letter country code as Unicode regional indicators."""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in country_code)


def flag_for_circuit_country(country: str) -> str:
    """Return a circuit host's flag, or empty text for unknown countries."""
    code = CIRCUIT_COUNTRY_CODES.get(country.strip().casefold())
    return _flag_for_code(code) if code else ""
