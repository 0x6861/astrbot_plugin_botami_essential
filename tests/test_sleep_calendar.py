from __future__ import annotations

import unittest
from datetime import date, timedelta

from src.sleep_tracker.calendar import (
    ROOT_CALENDAR_EPOCH,
    RootCalendarDate,
    to_root_calendar,
)


def gregorian_date_for_root(year: int, month: int, day: int) -> date:
    root_ordinal = date(year, month, day).toordinal()
    return ROOT_CALENDAR_EPOCH + timedelta(days=root_ordinal - 1)


class RootCalendarTests(unittest.TestCase):
    def test_epoch_and_first_year_boundary(self) -> None:
        self.assertEqual(
            to_root_calendar(date(2022, 3, 26)),
            RootCalendarDate(1, 1, 1),
        )
        self.assertEqual(
            to_root_calendar(date(2023, 3, 25)),
            RootCalendarDate(1, 12, 31),
        )
        self.assertEqual(
            to_root_calendar(date(2023, 3, 26)),
            RootCalendarDate(2, 1, 1),
        )

    def test_month_lengths_and_cross_year_conversion(self) -> None:
        for expected in (
            RootCalendarDate(2, 2, 28),
            RootCalendarDate(2, 3, 1),
            RootCalendarDate(2, 4, 30),
            RootCalendarDate(2, 5, 1),
            RootCalendarDate(9, 12, 31),
            RootCalendarDate(10, 1, 1),
        ):
            source = gregorian_date_for_root(
                expected.year, expected.month, expected.day
            )
            self.assertEqual(to_root_calendar(source), expected)

    def test_four_year_and_four_hundred_year_leaps(self) -> None:
        for year in (4, 400):
            source = gregorian_date_for_root(year, 2, 29)
            self.assertEqual(
                to_root_calendar(source), RootCalendarDate(year, 2, 29)
            )

    def test_century_year_is_not_a_leap_year(self) -> None:
        february_end = gregorian_date_for_root(100, 2, 28)
        self.assertEqual(
            to_root_calendar(february_end + timedelta(days=1)),
            RootCalendarDate(100, 3, 1),
        )

    def test_date_before_epoch_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            to_root_calendar(ROOT_CALENDAR_EPOCH - timedelta(days=1))


if __name__ == "__main__":
    unittest.main()
