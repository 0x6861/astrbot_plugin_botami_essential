from __future__ import annotations

from .errors import CounterConflictError, CounterNotFoundError
from .presenter import format_counter_list
from .service import CounterService


USAGE = (
    "用法：/cnt add <计数器名> [别名…]；/cnt del <名称或别名>；"
    "/cnt list；/cnt addname <主名> <别名…>；/cnt delname <别名>"
)


class CounterCommandProcessor:
    """解析兼容的 `/cnt` 命令，并将调用委托给领域服务。"""

    def __init__(self, service: CounterService):
        self._service = service

    async def handle(self, message: str) -> str:
        args = self._extract_args(message)
        if not args:
            return USAGE

        subcommand = args[0].casefold()
        try:
            if subcommand == "add":
                return await self._add(args[1:])
            if subcommand == "del":
                return await self._delete(args[1:])
            if subcommand == "list":
                return await self._list(args[1:])
            if subcommand == "addname":
                return await self._add_aliases(args[1:])
            if subcommand == "delname":
                return await self._delete_alias(args[1:])
        except CounterConflictError as exc:
            return "添加失败：\n- " + "\n- ".join(exc.conflicts)
        except CounterNotFoundError as exc:
            return str(exc)
        return "未知子命令"

    async def _add(self, args: list[str]) -> str:
        if not args:
            return "用法：/cnt add <计数器名> [可选：<别名1> <别名2> ...]"
        counter = await self._service.add(args[0], args[1:])
        alias_text = "无" if not counter.aliases else "、".join(counter.aliases)
        return f"✅ 已添加计数器「{counter.name}」有别名：{alias_text}"

    async def _delete(self, args: list[str]) -> str:
        if len(args) != 1:
            return "用法：/cnt del <计数器名或其别名>"
        counter = await self._service.delete(args[0])
        return f"🗑️ 已删除计数器「{counter.name}」"

    async def _list(self, args: list[str]) -> str:
        if args:
            return "用法：/cnt list"
        return format_counter_list(await self._service.list_counters())

    async def _add_aliases(self, args: list[str]) -> str:
        if len(args) < 2:
            return "用法：/cnt addname <计数器的主名> <别名1> [别名2 ...]"
        counter = await self._service.add_aliases(args[0], args[1:])
        return f"✅ 已为计数器「{counter.name}」添加别名：{'、'.join(args[1:])}"

    async def _delete_alias(self, args: list[str]) -> str:
        if len(args) != 1:
            return "用法：/cnt delname <计数器的别名>"
        counter, alias = await self._service.delete_alias(args[0])
        return f"🗑️ 已删除计数器「{counter.name}」的别名「{alias}」"

    @staticmethod
    def _extract_args(message: str) -> list[str]:
        parts = (message or "").strip().split()
        if not parts:
            return []
        command = parts[0].removeprefix("/")
        if command.casefold() != "cnt":
            return []
        return parts[1:]
