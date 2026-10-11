"""Regression checks for failed, unpublished, and partial data loads."""

import asyncio
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from slipstream.pages.results import _set_result_status
from slipstream.pages.results import ResultsState
from slipstream.pages.event import EventState
from slipstream.services import api


class AsyncStateStub:
    """Provide the state-lock interface for isolated background load checks."""

    async def __aenter__(self) -> "AsyncStateStub":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class DataLoadingTests(unittest.TestCase):
    """Keep upstream failures distinct from valid empty session responses."""

    def test_transient_failure_is_retried_once(self) -> None:
        attempts = 0

        def load() -> str:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise api.UpstreamDataError("partial load")
            return "loaded"

        with patch.object(api.clock_time, "sleep"):
            self.assertEqual(api.call_data_source(load), "loaded")
        self.assertEqual(attempts, 2)

    def test_repeated_failure_is_raised(self) -> None:
        attempts = 0

        def load() -> None:
            nonlocal attempts
            attempts += 1
            raise ConnectionError("timing source unavailable")

        with patch.object(api.clock_time, "sleep"):
            with self.assertRaises(ConnectionError):
                api.call_data_source(load)
        self.assertEqual(attempts, 2)

    def test_empty_completed_classification_is_a_load_error(self) -> None:
        session = SimpleNamespace(results=pd.DataFrame(), load=lambda **_: None)
        with patch.object(api.fastf1, "get_session", return_value=session):
            with self.assertRaises(api.UpstreamDataError):
                api.get_session_classification(2026, 16, "R", completed=True)
            self.assertEqual(api.get_session_classification(2026, 16, "R"), [])

    def test_partial_practice_load_is_a_load_error(self) -> None:
        session = SimpleNamespace(
            results=pd.DataFrame([{"DriverId": "driver"}]),
            laps=pd.DataFrame(),
            f1_api_support=True,
            load=lambda **_: None,
        )
        with patch.object(api.fastf1, "get_session", return_value=session):
            with patch.object(api, "get_driver_nationalities", return_value={}):
                with self.assertRaises(api.UpstreamDataError):
                    api.get_session_classification(2026, 16, "FP1", completed=True)

    def test_unpublished_and_failed_availability_are_distinct(self) -> None:
        session = SimpleNamespace(results=pd.DataFrame(), load=lambda **_: None)
        with patch.object(api.fastf1, "get_session", return_value=session):
            self.assertFalse(api.has_session_results(2026, 16, "FP1"))
            with self.assertRaises(api.UpstreamDataError):
                api.has_session_results(2026, 16, "FP1", completed=True)
            session.results = pd.DataFrame([{"DriverNumber": "1"}])
            self.assertTrue(api.has_session_results(2026, 16, "FP1", completed=True))

    def test_empty_completed_laps_are_a_load_error(self) -> None:
        session = SimpleNamespace(
            laps=pd.DataFrame(), f1_api_support=True, load=lambda **_: None
        )
        with patch.object(api.fastf1, "get_session", return_value=session):
            with self.assertRaises(api.UpstreamDataError):
                api.get_session_laps(2026, 16, "FP1", completed=True)
            self.assertEqual(
                api.get_session_laps(2026, 16, "FP1"),
                {"drivers": [], "laps": []},
            )

    def test_timing_retry_uses_mirror_and_restores_fastf1_mode(self) -> None:
        seen: list[tuple[str, bool]] = []
        session = SimpleNamespace(
            laps=pd.DataFrame(), f1_api_support=True, load=lambda **_: None
        )

        def get_session(*_: object) -> SimpleNamespace:
            seen.append((api.f1_api.base_url, api.f1_logger.LoggingManager.debug))
            return session

        original_url = api.f1_api.base_url
        original_debug = api.f1_logger.LoggingManager.debug
        with patch.object(api.fastf1, "get_session", side_effect=get_session):
            with patch.object(api.clock_time, "sleep"):
                with self.assertRaises(api.UpstreamDataError):
                    api.call_data_source(
                        api.get_session_laps, 2026, 16, "FP1", True
                    )
        self.assertEqual(seen[0], (original_url, original_debug))
        self.assertEqual(seen[1], (api.f1_api.base_url_mirror, True))
        self.assertEqual(api.f1_api.base_url, original_url)
        self.assertEqual(api.f1_logger.LoggingManager.debug, original_debug)

    def test_empty_archive_schedule_is_an_error(self) -> None:
        with patch.object(api.ergast, "get_race_schedule", return_value=[]):
            with self.assertRaises(api.UpstreamDataError):
                api.get_past_events(2026, today=date(2026, 10, 11))

    def test_session_status_update_preserves_other_data(self) -> None:
        session = {
            "code": "FP1", "name": "Practice 1", "result_status": "pending",
            "track_offset_minutes": 120,
        }
        days = [{"day": "FRIDAY", "date": "9 Oct", "date_iso": "2026-10-09", "sessions": [session]}]
        updated = _set_result_status(days, "FP1", "error")
        self.assertEqual(updated[0]["sessions"][0]["result_status"], "error")
        self.assertEqual(updated[0]["sessions"][0]["track_offset_minutes"], 120)
        self.assertEqual(session["result_status"], "pending")

    def test_optional_track_failure_preserves_weekend(self) -> None:
        state = AsyncStateStub()
        state.load_id = 1
        state.schedule_days = [{"sessions": [{"code": "FP1"}]}]
        original_days = state.schedule_days
        with patch(
            "slipstream.pages.results.call_data_source",
            side_effect=ConnectionError("optional timing unavailable"),
        ):
            asyncio.run(
                ResultsState._load_track_details(
                    state, 1, {"season": "2026", "round": "17"}
                )
            )
        self.assertIs(state.schedule_days, original_days)

    def test_old_lap_response_cannot_replace_new_selection(self) -> None:
        state = AsyncStateStub()
        state.load_id = 2
        state.selected_session = "FP2"
        state.lap_drivers = [{"code": "NEW"}]
        state.lap_points = []
        with patch(
            "slipstream.pages.event.call_data_source",
            return_value={"drivers": [{"code": "OLD"}], "laps": []},
        ):
            asyncio.run(
                EventState._fetch_laps(
                    state, 1, "2026", "16", "FP1", True, False
                )
            )
        self.assertEqual(state.lap_drivers, [{"code": "NEW"}])


if __name__ == "__main__":
    unittest.main()
