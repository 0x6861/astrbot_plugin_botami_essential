from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.sleep_tracker.models import GroupSleepState
from src.sleep_tracker.repository import SleepRepository
from src.sleep_tracker.service import SleepTrackerService


LOCAL_TIMEZONE = timezone(timedelta(hours=8))


class MutableClock:
    def __init__(self, current: datetime):
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class SleepTrackerServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_file = Path(self.temporary_directory.name) / "sleep.json"
        self.repository = SleepRepository(self.data_file)
        self.clock = MutableClock(
            datetime(2026, 8, 1, 22, 0, tzinfo=LOCAL_TIMEZONE)
        )
        self.service = SleepTrackerService(self.repository, clock=self.clock)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_groups_have_independent_daily_ranks(self) -> None:
        first = await self.service.good_night("group-a", "user-a")
        other_group = await self.service.good_night("group-b", "user-b")
        second = await self.service.good_night("group-a", "user-b")

        self.assertEqual(first.rank, 1)
        self.assertEqual(other_group.rank, 1)
        self.assertEqual(second.rank, 2)

    async def test_repeat_good_night_keeps_rank_and_overwrites_start(self) -> None:
        first = await self.service.good_night("group", "user")
        self.clock.current += timedelta(hours=1, minutes=15)
        repeated = await self.service.good_night("group", "user")
        self.clock.current += timedelta(hours=7, minutes=10)
        morning = await self.service.good_morning("group", "user")

        self.assertEqual(first.rank, 1)
        self.assertEqual(repeated.rank, 1)
        self.assertEqual(morning.slept_minutes, 430)

    async def test_rank_resets_at_local_midnight_and_active_sleep_survives(self) -> None:
        await self.service.good_night("group", "first")
        self.clock.current = datetime(
            2026, 8, 2, 0, 5, tzinfo=LOCAL_TIMEZONE
        )

        new_day_first = await self.service.good_night("group", "second")
        old_user_today = await self.service.good_night("group", "first")

        self.assertEqual(new_day_first.rank, 1)
        self.assertEqual(old_user_today.rank, 2)

    async def test_concurrent_registrations_get_unique_ranks(self) -> None:
        results = await asyncio.gather(
            *(
                self.service.good_night("group", f"user-{index}")
                for index in range(20)
            )
        )

        self.assertEqual(sorted(result.rank for result in results), list(range(1, 21)))
        reloaded = await self.repository.load()
        self.assertEqual(len(set(reloaded["group"].ranks.values())), 20)

    async def test_good_morning_floors_minutes_and_consumes_record(self) -> None:
        await self.service.good_night("group", "user")
        self.clock.current += timedelta(hours=8, minutes=9, seconds=59)

        first = await self.service.good_morning("group", "user")
        second = await self.service.good_morning("group", "user")

        self.assertEqual(first.slept_minutes, 489)
        self.assertIsNone(second.slept_minutes)

    async def test_zero_and_exactly_twenty_four_hours_are_valid(self) -> None:
        await self.service.good_night("group", "zero")
        zero = await self.service.good_morning("group", "zero")

        await self.service.good_night("group", "full-day")
        self.clock.current += timedelta(hours=24)
        full_day = await self.service.good_morning("group", "full-day")

        self.assertEqual(zero.slept_minutes, 0)
        self.assertEqual(full_day.slept_minutes, 24 * 60)

    async def test_expired_and_future_records_are_cleared(self) -> None:
        await self.service.good_night("group", "expired")
        self.clock.current += timedelta(hours=25)
        expired = await self.service.good_morning("group", "expired")

        self.clock.current += timedelta(hours=1)
        await self.service.good_night("group", "future")
        self.clock.current -= timedelta(hours=2)
        future = await self.service.good_morning("group", "future")
        reloaded = await self.repository.load()

        self.assertIsNone(expired.slept_minutes)
        self.assertIsNone(future.slept_minutes)
        self.assertEqual(reloaded["group"].active_sleeps, {})

    async def test_restart_restores_active_sleep(self) -> None:
        await self.service.good_night("group", "user")
        restored = SleepTrackerService(
            self.repository,
            await self.repository.load(),
            clock=self.clock,
        )
        self.clock.current += timedelta(hours=6)

        morning = await restored.good_morning("group", "user")

        self.assertEqual(morning.slept_minutes, 360)

    async def test_failed_save_does_not_pollute_memory(self) -> None:
        class ToggleRepository:
            should_fail = True

            async def save(self, groups: dict[str, GroupSleepState]) -> None:
                if self.should_fail:
                    raise OSError("disk full")

        repository = ToggleRepository()
        service = SleepTrackerService(
            repository,  # type: ignore[arg-type]
            clock=self.clock,
        )

        with self.assertRaises(OSError):
            await service.good_night("group", "first")
        repository.should_fail = False
        result = await service.good_night("group", "second")

        self.assertEqual(result.rank, 1)


if __name__ == "__main__":
    unittest.main()
