from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta

from .models import (
    GoodMorningResult,
    GoodNightResult,
    GroupSleepState,
    SleepRecord,
)
from .repository import SleepRepository


MAX_SLEEP_DURATION = timedelta(hours=24)


class SleepTrackerService:
    """封装睡眠登记、排名和消费规则，并串行提交持久化状态。"""

    def __init__(
        self,
        repository: SleepRepository,
        groups: dict[str, GroupSleepState] | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository = repository
        self._groups = self._clone(groups or {})
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._lock = asyncio.Lock()

    async def good_night(self, group_id: str, user_id: str) -> GoodNightResult:
        current_at = self._current_time()
        async with self._lock:
            updated = self._clone(self._groups)
            self._cleanup(updated, current_at)
            state = updated.setdefault(group_id, GroupSleepState())

            if state.ranking_date != current_at.date():
                state.ranking_date = current_at.date()
                state.ranks.clear()
            rank = state.ranks.get(user_id)
            if rank is None:
                rank = len(state.ranks) + 1
                state.ranks[user_id] = rank
            state.active_sleeps[user_id] = SleepRecord(current_at)

            await self._commit(updated)
            return GoodNightResult(current_at=current_at, rank=rank)

    async def good_morning(
        self, group_id: str, user_id: str
    ) -> GoodMorningResult:
        current_at = self._current_time()
        async with self._lock:
            updated = self._clone(self._groups)
            changed = self._cleanup(updated, current_at)
            state = updated.get(group_id)
            record = state.active_sleeps.get(user_id) if state is not None else None

            slept_minutes: int | None = None
            if record is not None:
                duration = current_at - record.started_at
                slept_minutes = int(duration.total_seconds() // 60)
                del state.active_sleeps[user_id]
                changed = True

            if changed:
                await self._commit(updated)
            return GoodMorningResult(
                current_at=current_at,
                slept_minutes=slept_minutes,
            )

    async def cleanup(self) -> None:
        """启动时清理跨日排名及无效活动记录。"""
        current_at = self._current_time()
        async with self._lock:
            updated = self._clone(self._groups)
            if self._cleanup(updated, current_at):
                await self._commit(updated)

    async def flush(self) -> None:
        async with self._lock:
            await self._repository.save(self._groups)

    async def _commit(self, updated: dict[str, GroupSleepState]) -> None:
        await self._repository.save(updated)
        self._groups = updated

    @staticmethod
    def _cleanup(
        groups: dict[str, GroupSleepState], current_at: datetime
    ) -> bool:
        changed = False
        for state in groups.values():
            if (
                state.ranking_date is not None
                and state.ranking_date != current_at.date()
            ):
                state.ranking_date = None
                state.ranks.clear()
                changed = True

            invalid_users = [
                user_id
                for user_id, record in state.active_sleeps.items()
                if not timedelta(0)
                <= current_at - record.started_at
                <= MAX_SLEEP_DURATION
            ]
            for user_id in invalid_users:
                del state.active_sleeps[user_id]
                changed = True
        return changed

    def _current_time(self) -> datetime:
        current_at = self._clock()
        if current_at.utcoffset() is None:
            current_at = current_at.astimezone()
        return current_at

    @staticmethod
    def _clone(
        groups: dict[str, GroupSleepState]
    ) -> dict[str, GroupSleepState]:
        return {group_id: state.clone() for group_id, state in groups.items()}
