from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.minecraft.errors import MinecraftDataError
from src.minecraft.models import MinecraftServer
from src.minecraft.repository import SCHEMA_VERSION, MinecraftRepository


class MinecraftRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_file = Path(self.temporary_directory.name) / "minecraft" / "servers.json"
        self.repository = MinecraftRepository(self.data_file)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_missing_file_loads_empty_without_creating_file(self) -> None:
        self.assertEqual(await self.repository.load(), {})
        self.assertFalse(self.data_file.exists())

    async def test_versioned_state_round_trip_preserves_order(self) -> None:
        groups = {
            "group": [
                MinecraftServer("one", "example.com"),
                MinecraftServer("two", "127.0.0.1", 25566),
            ]
        }

        await self.repository.save(groups)
        loaded = await self.repository.load()
        raw = json.loads(self.data_file.read_text(encoding="utf-8"))

        self.assertEqual(raw["schema_version"], SCHEMA_VERSION)
        self.assertEqual(loaded, groups)
        self.assertEqual(list(self.data_file.parent.glob("*.tmp")), [])

    async def test_invalid_json_is_not_overwritten(self) -> None:
        self.data_file.parent.mkdir(parents=True)
        self.data_file.write_text("{broken", encoding="utf-8")

        with self.assertRaises(MinecraftDataError):
            await self.repository.load()

        self.assertEqual(self.data_file.read_text(encoding="utf-8"), "{broken")

    async def test_duplicate_names_and_addresses_are_rejected(self) -> None:
        self.data_file.parent.mkdir(parents=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "groups": {
                "group": [
                    {"name": "one", "host": "example.com", "port": None},
                    {"name": "ONE", "host": "other.example.com", "port": None},
                ]
            },
        }
        self.data_file.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(MinecraftDataError):
            await self.repository.load()


if __name__ == "__main__":
    unittest.main()
