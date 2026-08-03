from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from src.food_recommender.commands import FoodCommandProcessor
from src.food_recommender.errors import (
    FoodConflictError,
    FoodNotFoundError,
    FoodValidationError,
)
from src.food_recommender.repository import FoodRepository
from src.food_recommender.service import FoodRecommenderService


class FoodRecommenderServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_file = Path(self.temporary_directory.name) / "foods.json"
        self.repository = FoodRepository(self.data_file)
        self.service = FoodRecommenderService(
            self.repository, selector=lambda foods: foods[-1]
        )
        self.commands = FoodCommandProcessor(self.service)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_empty_list_and_recommendation_explain_how_to_add(self) -> None:
        recommendation = await self.commands.handle("/今天吃什么", "group")
        listed = await self.commands.handle("/今天吃什么 list", "group")

        self.assertIn("/今天吃什么 add <食物...>", recommendation)
        self.assertIn("食物库为空", listed)

    async def test_quoted_batch_add_list_and_fixed_recommendation(self) -> None:
        added = await self.commands.handle(
            '/今天吃什么 add "番茄牛腩" "牛肉 拉面"', "group"
        )
        listed = await self.commands.handle("/今天吃什么 list", "group")
        recommended = await self.commands.handle("/今天吃什么", "group")

        self.assertEqual(added, "已添加食物：番茄牛腩、牛肉 拉面")
        self.assertEqual(
            listed, "当前群的食物：\n[1] 番茄牛腩\n[2] 牛肉 拉面"
        )
        self.assertEqual(recommended, "今天吃 牛肉 拉面 ！")

    async def test_batch_remove_preserves_input_order_and_is_atomic(self) -> None:
        await self.service.add("group", ["米饭", "面条", "饺子"])

        with self.assertRaises(FoodNotFoundError):
            await self.service.remove("group", ["米饭", "不存在"])
        self.assertEqual(
            await self.service.list_foods("group"), ("米饭", "面条", "饺子")
        )

        removed = await self.service.remove("group", ["饺子", "米饭"])
        self.assertEqual(removed, ("饺子", "米饭"))
        self.assertEqual(await self.service.list_foods("group"), ("面条",))

    async def test_duplicates_and_invalid_names_reject_whole_batch(self) -> None:
        await self.service.add("group", ["Pizza"])

        with self.assertRaises(FoodConflictError):
            await self.service.add("group", ["披萨", "PIZZA"])
        with self.assertRaises(FoodConflictError):
            await self.service.add("group", ["拉面", "拉面"])
        with self.assertRaises(FoodConflictError):
            await self.service.remove("group", ["Pizza", "pizza"])
        for invalid in ("   ", "含\t制表符", "含\n换行", "食" * 65):
            with self.assertRaises(FoodValidationError):
                await self.service.add("group", ["合法食物", invalid])

        self.assertEqual(await self.service.list_foods("group"), ("Pizza",))

    async def test_group_limit_is_enforced_without_partial_add(self) -> None:
        foods = [f"食物-{index}" for index in range(199)]
        service = FoodRecommenderService(
            self.repository, {"group": foods}, selector=lambda items: items[0]
        )

        with self.assertRaises(FoodConflictError):
            await service.add("group", ["第200项", "溢出项"])

        self.assertEqual(await service.list_foods("group"), tuple(foods))

    async def test_group_isolation_and_concurrent_adds(self) -> None:
        await self.service.add("group-b", ["另一群食物"])
        await asyncio.gather(
            *(self.service.add("group-a", [f"食物-{index}"]) for index in range(20))
        )

        group_a = await self.service.list_foods("group-a")
        self.assertEqual(set(group_a), {f"食物-{index}" for index in range(20)})
        self.assertEqual(await self.service.list_foods("group-b"), ("另一群食物",))
        self.assertEqual(set((await self.repository.load())["group-a"]), set(group_a))

    async def test_failed_save_does_not_pollute_memory(self) -> None:
        class ToggleRepository:
            should_fail = True

            async def save(self, _groups) -> None:
                if self.should_fail:
                    raise OSError("disk full")

        repository = ToggleRepository()
        service = FoodRecommenderService(
            repository,  # type: ignore[arg-type]
            {"group": ["已有食物"]},
        )

        with self.assertRaises(OSError):
            await service.add("group", ["未保存食物"])
        repository.should_fail = False
        await service.add("group", ["后来食物"])

        self.assertEqual(
            await service.list_foods("group"), ("已有食物", "后来食物")
        )

    async def test_restart_restores_foods(self) -> None:
        await self.service.add("group", ["米饭", "面条"])
        restored = FoodRecommenderService(
            self.repository,
            await self.repository.load(),
            selector=lambda foods: foods[0],
        )

        self.assertEqual(await restored.list_foods("group"), ("米饭", "面条"))
        self.assertEqual(await restored.recommend("group"), "米饭")


if __name__ == "__main__":
    unittest.main()
