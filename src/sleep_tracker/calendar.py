from __future__ import annotations

from dataclasses import dataclass
from datetime import date


ROOT_CALENDAR_EPOCH = date(2022, 3, 26)


@dataclass(frozen=True, slots=True)
class RootCalendarDate:
    """根号历日期。"""

    year: int
    month: int
    day: int

    def __str__(self) -> str:
        return f"根号{self.year}年{self.month}月{self.day}日"


def to_root_calendar(value: date) -> RootCalendarDate:
    """以根号历元日为序数 1，按公历闰年规则换算日期。"""
    ordinal = value.toordinal() - ROOT_CALENDAR_EPOCH.toordinal() + 1
    if ordinal < 1:
        raise ValueError("根号历暂不支持元日之前的日期。")

    converted = date.fromordinal(ordinal)
    return RootCalendarDate(converted.year, converted.month, converted.day)
