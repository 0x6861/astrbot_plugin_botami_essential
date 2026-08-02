from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from src.sleep_tracker.errors import SleepDataError
from src.sleep_tracker.models import GroupSleepState, SleepRecord
from src.sleep_tracker.repository import SCHEMA_VERSION, SleepRepository


class SleepRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_file = (
            Path(self.temporary_directory.name) / "sleep" / "sleep_records.json"
        )
        self.repository = SleepRepository(self.data_file)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_missing_file_loads_empty_without_creating_file(self) -> None:
        self.assertEqual(await self.repository.load(), {})
        self.assertFalse(self.data_file.exists())

    async def test_state_round_trip_uses_versioned_structure(self) -> None:
        started_at = datetime(2026, 8, 1, 23, 5, tzinfo=timezone.utc)
        state = GroupSleepState(
            active_sleeps={"user": SleepRecord(started_at)},
            ranking_date=date(2026, 8, 2),
            ranks={"user": 1},
        )

        await self.repository.save({"group": state})
        loaded = await self.repository.load()
        payload = json.loads(self.data_file.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertEqual(loaded["group"].active_sleeps["user"].started_at, started_at)
        self.assertEqual(loaded["group"].ranks, {"user": 1})
        self.assertEqual(list(self.data_file.parent.glob("*.tmp")), [])

    async def test_invalid_json_is_not_overwritten(self) -> None:
        self.data_file.parent.mkdir(parents=True)
        self.data_file.write_text("{broken", encoding="utf-8")

        with self.assertRaises(SleepDataError):
            await self.repository.load()

        self.assertEqual(self.data_file.read_text(encoding="utf-8"), "{broken")

    async def test_duplicate_or_non_contiguous_ranks_are_rejected(self) -> None:
        self.data_file.parent.mkdir(parents=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "groups": {
                "group": {
                    "active_sleeps": {},
                    "daily_ranking": {
                        "date": "2026-08-02",
                        "ranks": {"one": 1, "two": 1},
                    },
                }
            },
        }
        self.data_file.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(SleepDataError):
            await self.repository.load()


if __name__ == "__main__":
    unittest.main()
