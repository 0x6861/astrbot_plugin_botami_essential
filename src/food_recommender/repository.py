from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..atomic_json import write_json_atomic
from .errors import FoodDataError, FoodValidationError
from .validation import (
    MAX_FOODS_PER_GROUP,
    normalize_food_name,
    validate_food_name,
)


SCHEMA_VERSION = 1


class FoodRepository:
    """负责按群保存版本化食物列表。"""

    def __init__(self, data_file: Path):
        self.data_file = data_file

    async def load(self) -> dict[str, list[str]]:
        return await asyncio.to_thread(self._load_sync)

    async def save(self, groups: dict[str, list[str]]) -> None:
        snapshot = {
            group_id: list(foods) for group_id, foods in groups.items()
        }
        await asyncio.to_thread(self._save_sync, snapshot)

    def _load_sync(self) -> dict[str, list[str]]:
        if not self.data_file.exists():
            return {}
        try:
            raw = json.loads(self.data_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FoodDataError(
                f"无法读取食物数据文件 {self.data_file}: {exc}"
            ) from exc
        return self._decode(raw)

    def _decode(self, raw: Any) -> dict[str, list[str]]:
        if not isinstance(raw, dict) or not isinstance(raw.get("groups"), dict):
            raise FoodDataError(f"食物数据文件 {self.data_file} 缺少 groups 对象。")
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise FoodDataError(f"食物数据文件 {self.data_file} 的版本不受支持。")

        groups: dict[str, list[str]] = {}
        for group_id, raw_foods in raw["groups"].items():
            if not isinstance(group_id, str) or not group_id:
                raise FoodDataError("食物数据文件包含无效群 ID。")
            if not isinstance(raw_foods, list):
                raise FoodDataError(f"群 {group_id!r} 的食物列表必须是数组。")
            if len(raw_foods) > MAX_FOODS_PER_GROUP:
                raise FoodDataError(
                    f"群 {group_id!r} 的食物数量超过 {MAX_FOODS_PER_GROUP} 项。"
                )

            foods: list[str] = []
            names: set[str] = set()
            for raw_food in raw_foods:
                try:
                    food = validate_food_name(raw_food)
                except FoodValidationError as exc:
                    raise FoodDataError(
                        f"群 {group_id!r} 包含无效食物名称：{exc}"
                    ) from exc
                if food != raw_food:
                    raise FoodDataError(
                        f"群 {group_id!r} 的食物名称不能包含首尾空白。"
                    )
                normalized = normalize_food_name(food)
                if normalized in names:
                    raise FoodDataError(
                        f"群 {group_id!r} 包含重复食物「{food}」。"
                    )
                names.add(normalized)
                foods.append(food)
            groups[group_id] = foods
        return groups

    def _save_sync(self, groups: dict[str, list[str]]) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "groups": {
                group_id: list(foods) for group_id, foods in groups.items()
            },
        }
        write_json_atomic(self.data_file, payload)
