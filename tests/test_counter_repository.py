from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.counter.errors import CounterDataError
from src.counter.models import CounterRecord
from src.counter.repository import CounterRepository, SCHEMA_VERSION


class CounterRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.data_file = self.root / "new" / "counter" / "counters.json"
        self.legacy_file = self.root / "legacy" / "counters.json"
        self.repository = CounterRepository(self.data_file, self.legacy_file)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_missing_files_load_empty_state_without_creating_file(self) -> None:
        result = await self.repository.load()

        self.assertEqual(result.counters, {})
        self.assertIsNone(result.migrated_from)
        self.assertFalse(self.data_file.exists())

    async def test_legacy_file_is_migrated_once_and_left_unchanged(self) -> None:
        legacy_payload = {
            "counters": {
                "Python": {
                    "count": 3,
                    "aliases": ["py", "PY", "", "Python"],
                }
            }
        }
        self.legacy_file.parent.mkdir(parents=True)
        original_text = json.dumps(legacy_payload, ensure_ascii=False)
        self.legacy_file.write_text(original_text, encoding="utf-8")

        first = await self.repository.load()
        second = await self.repository.load()

        self.assertEqual(first.migrated_from, self.legacy_file)
        self.assertIsNone(second.migrated_from)
        self.assertEqual(first.counters["Python"].count, 3)
        self.assertEqual(first.counters["Python"].aliases, ["py"])
        self.assertEqual(self.legacy_file.read_text(encoding="utf-8"), original_text)
        migrated = json.loads(self.data_file.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], SCHEMA_VERSION)

    async def test_existing_new_file_takes_precedence_over_legacy_file(self) -> None:
        await self.repository.save({"new": CounterRecord("new", 2, [])})
        self.legacy_file.parent.mkdir(parents=True)
        self.legacy_file.write_text(
            json.dumps({"counters": {"old": {"count": 9, "aliases": []}}}),
            encoding="utf-8",
        )

        result = await self.repository.load()

        self.assertEqual(list(result.counters), ["new"])
        self.assertIsNone(result.migrated_from)

    async def test_invalid_json_raises_without_overwriting_source(self) -> None:
        self.data_file.parent.mkdir(parents=True)
        self.data_file.write_text("{broken", encoding="utf-8")

        with self.assertRaises(CounterDataError):
            await self.repository.load()

        self.assertEqual(self.data_file.read_text(encoding="utf-8"), "{broken")

    async def test_conflicting_aliases_are_rejected(self) -> None:
        self.data_file.parent.mkdir(parents=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "counters": {
                "one": {"count": 0, "aliases": ["same"]},
                "two": {"count": 0, "aliases": ["SAME"]},
            },
        }
        self.data_file.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(CounterDataError):
            await self.repository.load()

    async def test_save_replaces_file_and_leaves_no_temporary_file(self) -> None:
        await self.repository.save({"name": CounterRecord("name", 7, ["alias"])})

        payload = json.loads(self.data_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["counters"]["name"]["count"], 7)
        self.assertEqual(payload["counters"]["name"]["aliases"], ["alias"])
        self.assertEqual(list(self.data_file.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
