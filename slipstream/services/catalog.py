"""Shared Formula 1 session and tyre presentation metadata."""

EVENT_SESSION_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("FirstPractice", "FP1", "Practice 1"),
    ("SecondPractice", "FP2", "Practice 2"),
    ("ThirdPractice", "FP3", "Practice 3"),
    ("SprintQualifying", "SQ", "Sprint Qualifying"),
    ("SprintShootout", "SS", "Sprint Qualifying"),
    ("Sprint", "S", "Sprint"),
    ("Qualifying", "Q", "Qualifying"),
)

SUPPORTED_SESSION_CODES: frozenset[str] = frozenset(
    {code for _, code, _ in EVENT_SESSION_FIELDS} | {"R"}
)

OPENF1_SESSION_NAMES: dict[str, tuple[str, ...]] = {
    "FP1": ("Practice 1",),
    "FP2": ("Practice 2",),
    "FP3": ("Practice 3",),
    "SQ": ("Sprint Qualifying", "Sprint Shootout"),
    "SS": ("Sprint Shootout", "Sprint Qualifying"),
    "S": ("Sprint",),
    "Q": ("Qualifying",),
    "R": ("Race",),
}

COMPOUND_COLORS: dict[str, str] = {
    "SOFT": "#E10600",
    "MEDIUM": "#F2CE22",
    "HARD": "#F2F2F2",
    "INTERMEDIATE": "#38B449",
    "WET": "#2D9CDB",
    "UNKNOWN": "#969BA5",
}

TYRE_ICON_PATHS: dict[str, str] = {
    "SOFT": "/tyres/soft.svg",
    "MEDIUM": "/tyres/medium.svg",
    "HARD": "/tyres/hard.svg",
    "INTERMEDIATE": "/tyres/intermediate.svg",
    "WET": "/tyres/wet.svg",
}
