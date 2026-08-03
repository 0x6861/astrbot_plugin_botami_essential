from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.food_recommender.errors import FoodDataError
from src.food_recommender.repository import SCHEMA_VERSION, FoodRepository


class FoodRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_file = (
            Path(self.temporary_directory.name)
            / "food_recommender"
            / "foods.json"
        )
        self.repository = FoodRepository(self.data_file)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_missing_file_loads_empty_without_creating_file(self) -> None:
        self.assertEqual(await self.repository.load(), {})
        self.assertFalse(self.data_file.exists())

    async def test_versioned_round_trip_preserves_group_and_add_order(self) -> None:
        groups = {"group-a": ["米饭", "牛肉 拉面"], "group-b": ["Pizza"]}

        await self.repository.save(groups)
        loaded = await self.repository.load()
        raw = json.loads(self.data_file.read_text(encoding="utf-8"))

        self.assertEqual(raw["schema_version"], SCHEMA_VERSION)
        self.assertEqual(raw["groups"], groups)
        self.assertEqual(loaded, groups)
        self.assertEqual(list(self.data_file.parent.glob("*.tmp")), [])

    async def test_invalid_json_is_not_overwritten(self) -> None:
        self.data_file.parent.mkdir(parents=True)
        self.data_file.write_text("{broken", encoding="utf-8")

        with self.assertRaises(FoodDataError):
            await self.repository.load()

        self.assertEqual(self.data_file.read_text(encoding="utf-8"), "{broken")

    async def test_invalid_version_duplicates_and_names_are_rejected(self) -> None:
        invalid_payloads = (
            {"schema_version": 999, "groups": {}},
            {"schema_version": SCHEMA_VERSION, "groups": {"g": ["Pizza", "PIZZA"]}},
            {"schema_version": SCHEMA_VERSION, "groups": {"g": [" 食物"]}},
            {"schema_version": SCHEMA_VERSION, "groups": {"g": ["食" * 65]}},
        )

        self.data_file.parent.mkdir(parents=True)
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.data_file.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                with self.assertRaises(FoodDataError):
                    await self.repository.load()


if __name__ == "__main__":
    unittest.main()
