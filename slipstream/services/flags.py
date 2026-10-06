"""Turn Ergast nationality and host-country labels into flag emoji."""

# These names match the labels returned by the Ergast driver and circuit APIs.
# Historical nationalities without a present-day flag stay text-only.
NATIONALITY_COUNTRY_CODES: dict[str, str] = {
    "american": "US",
    "argentine": "AR",
    "australian": "AU",
    "austrian": "AT",
    "belgian": "BE",
    "brazilian": "BR",
    "british": "GB",
    "canadian": "CA",
    "chilean": "CL",
    "chinese": "CN",
    "colombian": "CO",
    "czech": "CZ",
    "danish": "DK",
    "dutch": "NL",
    "finnish": "FI",
    "french": "FR",
    "german": "DE",
    "hungarian": "HU",
    "indian": "IN",
    "indonesian": "ID",
    "irish": "IE",
    "italian": "IT",
    "japanese": "JP",
    "liechtensteiner": "LI",
    "malaysian": "MY",
    "mexican": "MX",
    "monegasque": "MC",
    "new zealander": "NZ",
    "polish": "PL",
    "portuguese": "PT",
    "russian": "RU",
    "south african": "ZA",
    "spanish": "ES",
    "swedish": "SE",
    "swiss": "CH",
    "thai": "TH",
    "uruguayan": "UY",
    "venezuelan": "VE",
}

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

# FastF1 uses its own three-letter driver country codes. Map common Formula 1
# codes to ISO alpha-2 values so the existing flag icon can render them.
DRIVER_COUNTRY_CODES: dict[str, str] = {
    "ARG": "AR",
    "AUS": "AU",
    "AUT": "AT",
    "BEL": "BE",
    "BRA": "BR",
    "CAN": "CA",
    "CHL": "CL",
    "CHN": "CN",
    "COL": "CO",
    "CRO": "HR",
    "CZE": "CZ",
    "DEN": "DK",
    "FIN": "FI",
    "FRA": "FR",
    "GBR": "GB",
    "GER": "DE",
    "HUN": "HU",
    "IND": "IN",
    "IRL": "IE",
    "ITA": "IT",
    "JPN": "JP",
    "MAL": "MY",
    "MEX": "MX",
    "MON": "MC",
    "NED": "NL",
    "NZL": "NZ",
    "POL": "PL",
    "POR": "PT",
    "RUS": "RU",
    "SAU": "SA",
    "SIN": "SG",
    "ESP": "ES",
    "SUI": "CH",
    "SWE": "SE",
    "THA": "TH",
    "TUR": "TR",
    "UAE": "AE",
    "USA": "US",
    "URU": "UY",
    "VEN": "VE",
    "ZAF": "ZA",
}


def _flag_for_code(country_code: str) -> str:
    """Encode a two-letter country code as Unicode regional indicators."""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in country_code)


def flag_for_nationality(nationality: str) -> str:
    """Return a driver's national flag, or empty text for unknown labels."""
    code = NATIONALITY_COUNTRY_CODES.get(nationality.strip().casefold())
    return _flag_for_code(code) if code else ""


def flag_for_driver_country_code(country_code: str) -> str:
    """Return a driver's flag from FastF1's three-letter country code."""
    code = DRIVER_COUNTRY_CODES.get(country_code.strip().upper())
    return _flag_for_code(code) if code else ""


def flag_for_circuit_country(country: str) -> str:
    """Return a circuit host's flag, or empty text for unknown countries."""
    code = CIRCUIT_COUNTRY_CODES.get(country.strip().casefold())
    return _flag_for_code(code) if code else ""
