"""TTL-cached entry points for repeated external data requests."""

import logging
from collections.abc import Callable, Hashable
from datetime import date
from threading import BoundedSemaphore
from time import monotonic

from .api import (
    DriverClassification,
    EventDetails,
    PastEvent,
    RaceWeekend,
    SessionLaps,
    get_available_seasons,
    get_completed_races,
    get_constructor_standings,
    get_driver_standings,
    get_event_details,
    get_past_events,
    get_race_weekend,
    get_session_classification,
    get_session_laps,
    has_session_results,
    parse_integer,
)
from .cache import TTLCache

_PROVIDER_CACHE: TTLCache = TTLCache(maxsize=128)
_PROVIDER_SEMAPHORE: BoundedSemaphore = BoundedSemaphore(value=4)
_CURRENT_SEASON_TTL_SECONDS: int = 60
_HISTORICAL_TTL_SECONDS: int = 24 * 60 * 60
logger: logging.Logger = logging.getLogger(__name__)


def _cached_provider_call[T](
    key: Hashable,
    ttl_seconds: float,
    loader: Callable[[], T],
) -> T:
    """Coalesce identical calls and bound upstream concurrency per process."""

    def load_with_limit() -> T:
        started_at: float = monotonic()
        try:
            with _PROVIDER_SEMAPHORE:
                return loader()
        except Exception:
            key_parts: tuple[Hashable, ...] = key if isinstance(key, tuple) else (key,)
            operation: str = str(key_parts[0]) if key_parts else "provider"
            logger.exception(
                "External data request failed",
                extra={
                    "provider_operation": operation,
                    "provider_key": repr(key_parts[1:]),
                    "duration_ms": round((monotonic() - started_at) * 1000, 1),
                },
            )
            raise

    return _PROVIDER_CACHE.get_or_load(key, ttl_seconds, load_with_limit)


def _season_ttl(season: int | str, current_ttl: int) -> int:
    """Use short freshness for current/future seasons and longer history TTL."""
    parsed_season: int | None = parse_integer(season)
    if parsed_season is None or parsed_season >= date.today().year:
        return current_ttl
    return _HISTORICAL_TTL_SECONDS


def get_cached_available_seasons(start_year: int = 1950) -> list[str]:
    """Return a cached list of available seasons.

    Args:
        start_year: Earliest season to include.

    Returns:
        Available season years, newest first.
    """
    return _cached_provider_call(
        ("available_seasons", start_year),
        6 * 60 * 60,
        lambda: get_available_seasons(start_year),
    )


def get_cached_completed_races(season: int | str) -> list[dict[str, str]]:
    """Return cached completed races for one season."""
    season_key: str = str(season)
    return _cached_provider_call(
        ("completed_races", season_key),
        _season_ttl(season, 15 * 60),
        lambda: get_completed_races(season),
    )


def get_cached_driver_standings(
    season: int | str, round_number: int | str
) -> list[dict[str, str]]:
    """Return cached driver standings for a completed race."""
    return _cached_provider_call(
        ("driver_standings", str(season), str(round_number)),
        _season_ttl(season, 5 * 60),
        lambda: get_driver_standings(season, round_number),
    )


def get_cached_constructor_standings(
    season: int | str, round_number: int | str
) -> list[dict[str, str]]:
    """Return cached constructor standings for a completed race."""
    return _cached_provider_call(
        ("constructor_standings", str(season), str(round_number)),
        _season_ttl(season, 5 * 60),
        lambda: get_constructor_standings(season, round_number),
    )


def get_cached_race_weekend(today: date | None = None) -> RaceWeekend | None:
    """Return the current/upcoming race weekend with a short TTL."""
    current_date: date = today or date.today()
    return _cached_provider_call(
        ("race_weekend", current_date.isoformat()),
        5 * 60,
        lambda: get_race_weekend(current_date),
    )


def get_cached_session_results(
    season: int | str, round_number: int | str, session_code: str
) -> bool:
    """Check whether published session rows exist, refreshing every minute."""
    return _cached_provider_call(
        ("session_results", str(season), str(round_number), session_code),
        60,
        lambda: has_session_results(season, round_number, session_code),
    )


def get_cached_past_events(
    season: int | str, today: date | None = None
) -> list[PastEvent]:
    """Return the season archive with a one-hour TTL."""
    current_date: date = today or date.today()
    return _cached_provider_call(
        ("past_events", str(season), current_date.isoformat()),
        60 * 60,
        lambda: get_past_events(season, current_date),
    )


def get_cached_event_details(
    season: int | str, round_number: int | str
) -> EventDetails | None:
    """Return event metadata with freshness suited to its season."""
    return _cached_provider_call(
        ("event_details", str(season), str(round_number)),
        _season_ttl(season, 5 * 60),
        lambda: get_event_details(season, round_number),
    )


def get_cached_session_classification(
    season: int | str,
    round_number: int | str,
    session_code: str,
) -> list[DriverClassification]:
    """Return session classification rows with current-season refreshes."""
    return _cached_provider_call(
        ("session_classification", str(season), str(round_number), session_code),
        _season_ttl(season, _CURRENT_SEASON_TTL_SECONDS),
        lambda: get_session_classification(season, round_number, session_code),
    )


def get_cached_session_laps(
    season: int | str, round_number: int | str, session_code: str
) -> SessionLaps:
    """Return session laps with current-season refreshes."""
    return _cached_provider_call(
        ("session_laps", str(season), str(round_number), session_code),
        _season_ttl(season, 5 * 60),
        lambda: get_session_laps(season, round_number, session_code),
    )
