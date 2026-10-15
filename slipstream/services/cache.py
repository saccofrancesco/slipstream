"""Small thread-safe TTL cache for normalized provider results."""

from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from threading import Lock
from time import monotonic
from typing import Callable, Hashable, TypeVar, cast

T = TypeVar("T")


class TTLCache:
    """Cache normalized values with per-key single-flight loading.

    Cached values are copied on read and write so Reflex state cannot mutate a
    value that another visitor will receive. Concurrent misses for the same
    key share one loader call. The cache is process-local and bounded by its
    number of keys.
    """

    def __init__(self, maxsize: int = 512) -> None:
        """Create a cache that retains at most ``maxsize`` keys.

        Args:
            maxsize: Maximum number of cached keys.

        Raises:
            ValueError: If ``maxsize`` is less than one.
        """
        if maxsize < 1:
            raise ValueError("Cache maxsize must be at least one.")

        self._maxsize: int = maxsize
        self._entries: OrderedDict[Hashable, tuple[float, object]] = OrderedDict()
        self._inflight: dict[Hashable, Future[object]] = {}
        self._lock: Lock = Lock()

    def get_or_load(
        self,
        key: Hashable,
        ttl_seconds: float,
        loader: Callable[[], T],
    ) -> T:
        """Return a fresh cached value or load and cache a new one.

        Args:
            key: Hashable identity for the normalized result.
            ttl_seconds: How long a successful result remains fresh.
            loader: Synchronous provider function used on a cache miss.

        Returns:
            A deep copy of the cached or newly loaded value.
        """
        if ttl_seconds <= 0:
            return loader()

        cached_value: object | None = None
        has_cached_value: bool = False
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                expires_at, value = entry
                if expires_at > monotonic():
                    self._entries.move_to_end(key)
                    cached_value = value
                    has_cached_value = True
                else:
                    del self._entries[key]

            if has_cached_value:
                future = None
                owns_load = False
            else:
                future = self._inflight.get(key)
                owns_load = future is None
                if owns_load:
                    future = Future()
                    self._inflight[key] = future

        if has_cached_value:
            return cast(T, deepcopy(cached_value))

        assert future is not None
        if not owns_load:
            return cast(T, deepcopy(future.result()))

        try:
            value = loader()
            cached_copy = deepcopy(value)
        except BaseException as error:
            with self._lock:
                self._inflight.pop(key, None)
            future.set_exception(error)
            raise

        with self._lock:
            self._entries[key] = (monotonic() + ttl_seconds, cached_copy)
            self._entries.move_to_end(key)
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)
            self._inflight.pop(key, None)

        future.set_result(cached_copy)
        return cast(T, deepcopy(cached_copy))
