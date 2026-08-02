from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from src.counter.commands import CounterCommandProcessor, USAGE
from src.counter.errors import CounterConflictError
from src.counter.models import CounterRecord
from src.counter.presenter import format_increment_result
from src.counter.repository import CounterRepository
from src.counter.service import CounterService


class CounterServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_file = Path(self.temporary_directory.name) / "counters.json"
        self.repository = CounterRepository(self.data_file)
        self.service = CounterService(self.repository)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_add_list_alias_management_and_delete_by_alias(self) -> None:
        added = await self.service.add("Python", ["py", "蛇"])
        updated = await self.service.add_aliases("python", ["Python3"])
        counter, removed_alias = await self.service.delete_alias("PY")
        removed = await self.service.delete("python3")

        self.assertEqual(added.aliases, ("py", "蛇"))
        self.assertEqual(updated.aliases, ("py", "蛇", "Python3"))
        self.assertEqual(removed_alias, "PY")
        self.assertEqual(counter.aliases, ("蛇", "Python3"))
        self.assertEqual(removed.name, "Python")
        self.assertEqual(await self.service.list_counters(), ())

    async def test_name_and_alias_conflicts_are_case_insensitive(self) -> None:
        await self.service.add("Python", ["py"])

        with self.assertRaises(CounterConflictError):
            await self.service.add("PY", [])
        with self.assertRaises(CounterConflictError):
            await self.service.add("other", ["python"])
        with self.assertRaises(CounterConflictError):
            await self.service.add_aliases("Python", ["one", "ONE"])

    async def test_each_counter_increments_once_per_message(self) -> None:
        await self.service.add("cat", ["kitty"])
        await self.service.add("catalog", [])

        hits = await self.service.increment_matching("CAT cat kitty catalog")

        self.assertEqual([(item.name, item.count) for item in hits], [("cat", 1), ("catalog", 1)])

    async def test_concurrent_increments_are_not_lost(self) -> None:
        await self.service.add("hit", [])

        await asyncio.gather(
            *(self.service.increment_matching("hit") for _ in range(20))
        )

        counters = await self.service.list_counters()
        self.assertEqual(counters[0].count, 20)
        reloaded = (await self.repository.load()).counters
        self.assertEqual(reloaded["hit"].count, 20)

    async def test_failed_save_does_not_change_memory_state(self) -> None:
        class FailingRepository:
            async def save(self, counters: dict[str, CounterRecord]) -> None:
                raise OSError("disk full")

        service = CounterService(
            FailingRepository(),  # type: ignore[arg-type]
            {"hit": CounterRecord("hit", 4, [])},
        )

        with self.assertRaises(OSError):
            await service.increment_matching("hit")

        self.assertEqual((await service.list_counters())[0].count, 4)

    async def test_list_is_sorted_by_count_descending(self) -> None:
        service = CounterService(
            self.repository,
            {
                "low": CounterRecord("low", 1, []),
                "high": CounterRecord("high", 9, []),
            },
        )

        counters = await service.list_counters()

        self.assertEqual([counter.name for counter in counters], ["high", "low"])

    async def test_command_processor_preserves_public_commands(self) -> None:
        commands = CounterCommandProcessor(self.service)

        self.assertEqual(await commands.handle("/cnt"), USAGE)
        self.assertIn("已添加计数器", await commands.handle("/cnt add Python py"))
        self.assertIn("Python：0 次", await commands.handle("/cnt list"))
        self.assertIn("添加别名", await commands.handle("/cnt addname Python snake"))
        self.assertIn("已删除计数器", await commands.handle("/cnt del snake"))
        self.assertEqual(await commands.handle("/cnt unknown"), "未知子命令")

    async def test_special_and_multiple_hit_messages_are_preserved(self) -> None:
        special = format_increment_result(
            (CounterRecord("test", 6, []).snapshot(),)
        )
        multiple = format_increment_result(
            (
                CounterRecord("one", 1, []).snapshot(),
                CounterRecord("two", 2, []).snapshot(),
            )
        )

        self.assertEqual(special, "test, 6")
        self.assertEqual(
            multiple,
            "累计 one 1/114514\n累计 two 2/114514",
        )


if __name__ == "__main__":
    unittest.main()
