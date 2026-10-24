"""Rate-limited access to Jolpica's Ergast-compatible Formula 1 API."""

from collections import deque
from collections.abc import Mapping
from threading import Lock
from time import monotonic, sleep
from typing import Any

import requests
from requests import HTTPError

JOLPICA_BASE_URL: str = "https://api.jolpi.ca/ergast/f1"
_REQUEST_TIMEOUT_SECONDS: int = 30
_PAGE_SIZE: int = 100
_RATE_LIMIT_GRACE_SECONDS: float = 0.05
_HTTP_SESSION: requests.Session = requests.Session()
_HTTP_SESSION.headers.update(
    {
        "Accept": "application/json",
        "User-Agent": "Slipstream/1.0 (+https://github.com/saccofrancesco/slipstream)",
    }
)
_RATE_LIMIT_LOCK: Lock = Lock()
_HTTP_LOCK: Lock = Lock()
_REQUEST_TIMES: deque[float] = deque()


def _wait_for_rate_limit() -> None:
    """Keep this process below the API's unauthenticated burst limit."""
    with _RATE_LIMIT_LOCK:
        while True:
            now = monotonic()
            while _REQUEST_TIMES and now - _REQUEST_TIMES[0] >= 1:
                _REQUEST_TIMES.popleft()
            if len(_REQUEST_TIMES) < 4:
                _REQUEST_TIMES.append(now)
                return
            sleep(_REQUEST_TIMES[0] + 1 - now + _RATE_LIMIT_GRACE_SECONDS)


def _request_json(path: str, params: dict[str, int]) -> dict[str, Any]:
    """Fetch one JSON response and validate its top-level shape."""
    for attempt in range(2):
        _wait_for_rate_limit()
        with _HTTP_LOCK:
            response = _HTTP_SESSION.get(
                f"{JOLPICA_BASE_URL}/{path.lstrip('/')}",
                params=params,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        if response.status_code != 429 or attempt == 1:
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Jolpica returned an unexpected JSON payload")
            return payload

        retry_after = response.headers.get("Retry-After", "1")
        try:
            sleep(max(1.0, min(float(retry_after), 10.0)))
        except ValueError:
            sleep(1.0)
    return {}


def get_jolpica_rows(
    path: str,
    table_name: str,
    collection_name: str,
) -> list[dict[str, Any]]:
    """Return all rows in one Ergast-compatible API collection.

    Jolpica limits each response to 100 top-level rows. The app's usual
    collections fit in one page; pagination also covers longer lap archives.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        try:
            payload = _request_json(
                path,
                {"limit": _PAGE_SIZE, "offset": offset},
            )
        except HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                return rows
            raise
        mr_data = payload.get("MRData")
        if not isinstance(mr_data, Mapping):
            raise ValueError("Jolpica response is missing MRData")
        table = mr_data.get(table_name)
        if not isinstance(table, Mapping):
            return rows
        page = table.get(collection_name)
        if not isinstance(page, list):
            return rows

        page_rows = [row for row in page if isinstance(row, dict)]
        rows.extend(page_rows)
        try:
            total = int(mr_data.get("total", 0))
        except (TypeError, ValueError):
            total = 0
        offset += len(page_rows)
        if not page_rows or len(page_rows) < _PAGE_SIZE or offset >= total:
            return rows
