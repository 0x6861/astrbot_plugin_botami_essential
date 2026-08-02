from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..atomic_json import write_json_atomic
from .errors import SleepDataError
from .models import GroupSleepState, SleepRecord


SCHEMA_VERSION = 1


class SleepRepository:
    """负责睡眠记录 JSON 的校验与原子写入。"""

    def __init__(self, data_file: Path):
        self.data_file = data_file

    async def load(self) -> dict[str, GroupSleepState]:
        return await asyncio.to_thread(self._load_sync)

    async def save(self, groups: dict[str, GroupSleepState]) -> None:
        snapshot = {
            group_id: state.clone() for group_id, state in groups.items()
        }
        await asyncio.to_thread(self._save_sync, snapshot)

    def _load_sync(self) -> dict[str, GroupSleepState]:
        if not self.data_file.exists():
            return {}
        try:
            raw = json.loads(self.data_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SleepDataError(
                f"无法读取睡眠记录文件 {self.data_file}: {exc}"
            ) from exc
        return self._decode(raw)

    def _decode(self, raw: Any) -> dict[str, GroupSleepState]:
        if not isinstance(raw, dict) or not isinstance(raw.get("groups"), dict):
            raise SleepDataError(
                f"睡眠记录文件 {self.data_file} 缺少 groups 对象。"
            )
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise SleepDataError(
                f"睡眠记录文件 {self.data_file} 的版本不受支持。"
            )

        groups: dict[str, GroupSleepState] = {}
        for group_id, metadata in raw["groups"].items():
            if not isinstance(group_id, str) or not group_id:
                raise SleepDataError("睡眠记录包含无效群 ID。")
            if not isinstance(metadata, dict):
                raise SleepDataError(f"群 {group_id!r} 的睡眠记录必须是对象。")

            active_sleeps = self._decode_active_sleeps(
                group_id, metadata.get("active_sleeps")
            )
            ranking_date, ranks = self._decode_ranking(
                group_id, metadata.get("daily_ranking")
            )
            groups[group_id] = GroupSleepState(
                active_sleeps=active_sleeps,
                ranking_date=ranking_date,
                ranks=ranks,
            )
        return groups

    @staticmethod
    def _decode_active_sleeps(
        group_id: str, raw: Any
    ) -> dict[str, SleepRecord]:
        if not isinstance(raw, dict):
            raise SleepDataError(f"群 {group_id!r} 缺少 active_sleeps 对象。")

        records: dict[str, SleepRecord] = {}
        for user_id, metadata in raw.items():
            if not isinstance(user_id, str) or not user_id:
                raise SleepDataError(f"群 {group_id!r} 包含无效用户 ID。")
            if not isinstance(metadata, dict) or not isinstance(
                metadata.get("started_at"), str
            ):
                raise SleepDataError(f"用户 {user_id!r} 的睡眠起点无效。")
            try:
                started_at = datetime.fromisoformat(metadata["started_at"])
            except ValueError as exc:
                raise SleepDataError(
                    f"用户 {user_id!r} 的睡眠起点格式无效。"
                ) from exc
            if started_at.utcoffset() is None:
                raise SleepDataError(f"用户 {user_id!r} 的睡眠起点缺少时区。")
            records[user_id] = SleepRecord(started_at)
        return records

    @staticmethod
    def _decode_ranking(
        group_id: str, raw: Any
    ) -> tuple[date | None, dict[str, int]]:
        if not isinstance(raw, dict):
            raise SleepDataError(f"群 {group_id!r} 缺少 daily_ranking 对象。")

        raw_date = raw.get("date")
        raw_ranks = raw.get("ranks")
        if raw_date is None:
            ranking_date = None
        elif isinstance(raw_date, str):
            try:
                ranking_date = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise SleepDataError(f"群 {group_id!r} 的排名日期无效。") from exc
        else:
            raise SleepDataError(f"群 {group_id!r} 的排名日期无效。")

        if not isinstance(raw_ranks, dict):
            raise SleepDataError(f"群 {group_id!r} 的 ranks 必须是对象。")
        ranks: dict[str, int] = {}
        for user_id, rank in raw_ranks.items():
            if (
                not isinstance(user_id, str)
                or not user_id
                or isinstance(rank, bool)
                or not isinstance(rank, int)
                or rank < 1
            ):
                raise SleepDataError(f"群 {group_id!r} 包含无效排名。")
            ranks[user_id] = rank

        if sorted(ranks.values()) != list(range(1, len(ranks) + 1)):
            raise SleepDataError(f"群 {group_id!r} 的排名不连续或存在重复。")
        if ranking_date is None and ranks:
            raise SleepDataError(f"群 {group_id!r} 的排名缺少日期。")
        return ranking_date, ranks

    def _save_sync(self, groups: dict[str, GroupSleepState]) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "groups": {
                group_id: {
                    "active_sleeps": {
                        user_id: {"started_at": record.started_at.isoformat()}
                        for user_id, record in state.active_sleeps.items()
                    },
                    "daily_ranking": {
                        "date": (
                            state.ranking_date.isoformat()
                            if state.ranking_date is not None
                            else None
                        ),
                        "ranks": dict(state.ranks),
                    },
                }
                for group_id, state in groups.items()
            },
        }
        write_json_atomic(self.data_file, payload)
