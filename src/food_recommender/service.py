from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Sequence

from .errors import (
    FoodConflictError,
    FoodListEmptyError,
    FoodNotFoundError,
    FoodValidationError,
)
from .repository import FoodRepository
from .validation import (
    MAX_FOODS_PER_GROUP,
    normalize_food_name,
    validate_food_name,
)


FoodSelector = Callable[[Sequence[str]], str]


class FoodRecommenderService:
    """管理群食物库，并保证内存状态与磁盘提交一致。"""

    def __init__(
        self,
        repository: FoodRepository,
        groups: dict[str, list[str]] | None = None,
        *,
        selector: FoodSelector | None = None,
    ):
        self._repository = repository
        self._groups = self._clone(groups or {})
        self._selector = selector or random.choice
        self._lock = asyncio.Lock()

    async def add(self, group_id: str, foods: Sequence[str]) -> tuple[str, ...]:
        self._validate_group_id(group_id)
        cleaned = self._validate_batch(foods)

        async with self._lock:
            current = self._groups.get(group_id, [])
            current_names = {normalize_food_name(food) for food in current}
            for food in cleaned:
                if normalize_food_name(food) in current_names:
                    raise FoodConflictError(f"食物「{food}」已存在。")
            if len(current) + len(cleaned) > MAX_FOODS_PER_GROUP:
                raise FoodConflictError(
                    f"每个群最多保存 {MAX_FOODS_PER_GROUP} 项食物。"
                )

            updated = self._clone(self._groups)
            updated.setdefault(group_id, []).extend(cleaned)
            await self._commit(updated)
            return tuple(cleaned)

    async def remove(
        self, group_id: str, foods: Sequence[str]
    ) -> tuple[str, ...]:
        self._validate_group_id(group_id)
        cleaned = self._validate_batch(foods)

        async with self._lock:
            current = self._groups.get(group_id, [])
            index = {normalize_food_name(food): food for food in current}
            missing = [
                food for food in cleaned if normalize_food_name(food) not in index
            ]
            if missing:
                raise FoodNotFoundError(
                    "未找到食物：" + "、".join(f"「{food}」" for food in missing)
                )

            removed = tuple(index[normalize_food_name(food)] for food in cleaned)
            removed_names = {normalize_food_name(food) for food in cleaned}
            updated = self._clone(self._groups)
            updated[group_id] = [
                food
                for food in updated[group_id]
                if normalize_food_name(food) not in removed_names
            ]
            await self._commit(updated)
            return removed

    async def list_foods(self, group_id: str) -> tuple[str, ...]:
        self._validate_group_id(group_id)
        async with self._lock:
            return tuple(self._groups.get(group_id, ()))

    async def recommend(self, group_id: str) -> str:
        self._validate_group_id(group_id)
        async with self._lock:
            foods = self._groups.get(group_id, [])
            if not foods:
                raise FoodListEmptyError(
                    "当前群食物库为空，请先通过 "
                    "/今天吃什么 add <食物...> 添加食物。"
                )
            return self._selector(tuple(foods))

    async def flush(self) -> None:
        async with self._lock:
            await self._repository.save(self._groups)

    async def _commit(self, updated: dict[str, list[str]]) -> None:
        await self._repository.save(updated)
        self._groups = updated

    @staticmethod
    def _validate_batch(foods: Sequence[str]) -> list[str]:
        if not foods:
            raise FoodValidationError("请至少提供一项食物。")

        cleaned: list[str] = []
        names: set[str] = set()
        for raw_food in foods:
            food = validate_food_name(raw_food)
            normalized = normalize_food_name(food)
            if normalized in names:
                raise FoodConflictError(f"食物「{food}」在本次请求中重复。")
            names.add(normalized)
            cleaned.append(food)
        return cleaned

    @staticmethod
    def _validate_group_id(group_id: str) -> None:
        if not isinstance(group_id, str) or not group_id:
            raise FoodValidationError("群 ID 不能为空。")

    @staticmethod
    def _clone(groups: dict[str, list[str]]) -> dict[str, list[str]]:
        return {group_id: list(foods) for group_id, foods in groups.items()}
