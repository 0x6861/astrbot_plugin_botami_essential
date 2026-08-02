from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from src.minecraft.commands import MinecraftCommandProcessor
from src.minecraft.errors import MinecraftConflictError, MinecraftValidationError
from src.minecraft.models import MinecraftServer, MinecraftStatus
from src.minecraft.repository import MinecraftRepository
from src.minecraft.service import MinecraftService


class FakeStatusClient:
    async def query(self, server: MinecraftServer) -> MinecraftStatus:
        if server.name == "slow":
            await asyncio.sleep(0.01)
        hidden_players = server.name == "hidden"
        return MinecraftStatus(
            server=server,
            online=True,
            description=f"{server.name} 简介",
            online_players=0 if server.name == "empty" else 2,
            max_players=20,
            player_names=(
                () if server.name == "empty" or hidden_players else ("Alice", "Bob")
            ),
        )


class MinecraftServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_file = Path(self.temporary_directory.name) / "servers.json"
        self.repository = MinecraftRepository(self.data_file)
        self.service = MinecraftService(
            self.repository,
            status_client=FakeStatusClient(),  # type: ignore[arg-type]
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_group_isolation_add_list_and_remove(self) -> None:
        await self.service.add("group-a", "生存服", "mc.example.com")
        await self.service.add("group-b", "生存服", "other.example.com:25566")

        group_a = await self.service.list_servers("group-a")
        removed = await self.service.remove("group-a", "生存服")

        self.assertEqual(group_a[0].address, "mc.example.com")
        self.assertEqual(removed.name, "生存服")
        self.assertEqual(await self.service.list_servers("group-a"), ())
        self.assertEqual(len(await self.service.list_servers("group-b")), 1)

    async def test_name_and_endpoint_conflicts_are_rejected(self) -> None:
        await self.service.add("group", "One", "example.com")

        with self.assertRaises(MinecraftConflictError):
            await self.service.add("group", "ONE", "other.example.com")
        with self.assertRaises(MinecraftConflictError):
            await self.service.add("group", "two", "EXAMPLE.com")

    async def test_address_validation_and_ipv6_format(self) -> None:
        added = await self.service.add("group", "ipv6", "[::1]:25567")

        self.assertEqual(added.address, "[::1]:25567")
        with self.assertRaises(MinecraftValidationError):
            await self.service.add("group", "bad", "::1:25565")
        with self.assertRaises(MinecraftValidationError):
            await self.service.add("group", "bad-port", "example.com:70000")

    async def test_query_all_preserves_add_order_and_zero_player_copy(self) -> None:
        await self.service.add("group", "slow", "one.example.com")
        await self.service.add("group", "empty", "two.example.com")
        await self.service.add("group", "hidden", "three.example.com")
        commands = MinecraftCommandProcessor(self.service)

        response = await commands.handle("/mc", "group")

        self.assertLess(response.index("[1] slow"), response.index("[2] empty"))
        self.assertIn("在线玩家：Alice, Bob", response)
        self.assertIn("在线玩家：(无)", response)
        self.assertIn("在线玩家：服务器未提供名单（在线 2/20）", response)

    async def test_group_server_limit_is_enforced(self) -> None:
        for index in range(20):
            await self.service.add(
                "group", f"server-{index}", f"server-{index}.example.com"
            )

        with self.assertRaises(MinecraftConflictError):
            await self.service.add("group", "overflow", "overflow.example.com")

    async def test_quoted_command_add_list_and_remove(self) -> None:
        commands = MinecraftCommandProcessor(self.service)

        added = await commands.handle(
            '/mc add "生存服务器 一区" mc.example.com:25566', "group"
        )
        listed = await commands.handle("/mc list", "group")
        removed = await commands.handle('/mc rm "生存服务器 一区"', "group")

        self.assertIn("已添加", added)
        self.assertIn("[1] 生存服务器 一区 - mc.example.com:25566", listed)
        self.assertIn("已删除", removed)

    async def test_failed_save_does_not_pollute_memory(self) -> None:
        class ToggleRepository:
            should_fail = True

            async def save(self, _groups) -> None:
                if self.should_fail:
                    raise OSError("disk full")

        repository = ToggleRepository()
        service = MinecraftService(
            repository,  # type: ignore[arg-type]
            status_client=FakeStatusClient(),  # type: ignore[arg-type]
        )

        with self.assertRaises(OSError):
            await service.add("group", "one", "one.example.com")
        repository.should_fail = False
        await service.add("group", "two", "two.example.com")

        self.assertEqual(
            [server.name for server in await service.list_servers("group")],
            ["two"],
        )

    async def test_restart_restores_servers(self) -> None:
        await self.service.add("group", "one", "example.com")
        restored = MinecraftService(
            self.repository,
            await self.repository.load(),
            status_client=FakeStatusClient(),  # type: ignore[arg-type]
        )

        self.assertEqual(
            await restored.list_servers("group"),
            (MinecraftServer("one", "example.com"),),
        )


if __name__ == "__main__":
    unittest.main()
