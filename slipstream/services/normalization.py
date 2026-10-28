"""Small normalizers shared by external Formula 1 providers."""

import re
import unicodedata


def normalize_event_name(value: str) -> str:
    """Return an accent- and punctuation-insensitive event name."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.decode().lower()).strip()
