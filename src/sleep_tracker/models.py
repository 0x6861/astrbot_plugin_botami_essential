from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class SleepRecord:
    """用户当前尚未消费的睡眠起点。"""

    started_at: datetime

    def clone(self) -> SleepRecord:
        return SleepRecord(self.started_at)


@dataclass(slots=True)
class GroupSleepState:
    """一个群的活动睡眠和当日排名。"""

    active_sleeps: dict[str, SleepRecord] = field(default_factory=dict)
    ranking_date: date | None = None
    ranks: dict[str, int] = field(default_factory=dict)

    def clone(self) -> GroupSleepState:
        return GroupSleepState(
            active_sleeps={
                user_id: record.clone()
                for user_id, record in self.active_sleeps.items()
            },
            ranking_date=self.ranking_date,
            ranks=dict(self.ranks),
        )


@dataclass(frozen=True, slots=True)
class GoodNightResult:
    """晚安登记结果。"""

    current_at: datetime
    rank: int


@dataclass(frozen=True, slots=True)
class GoodMorningResult:
    """早安处理结果；无有效睡眠时长时 slept_minutes 为 None。"""

    current_at: datetime
    slept_minutes: int | None
