from __future__ import annotations

import shlex

from .errors import MinecraftError
from .presenter import format_server_list, format_statuses
from .service import MinecraftService


USAGE = (
    "用法：/mc；/mc add <名称> <主机[:端口]>；"
    "/mc rm <名称>；/mc list。名称包含空格时请使用引号。"
)


class MinecraftCommandProcessor:
    """解析 `/mc` 命令并委托给 Minecraft 领域服务。"""

    def __init__(self, service: MinecraftService):
        self._service = service

    async def handle(self, message: str, group_id: str) -> str:
        try:
            args = self._extract_args(message)
        except ValueError:
            return "命令中的引号未正确闭合。\n" + USAGE

        if not args:
            return format_statuses(await self._service.query_all(group_id))

        subcommand = args[0].casefold()
        try:
            if subcommand == "add":
                if len(args) != 3:
                    return "用法：/mc add <名称> <主机[:端口]>"
                server = await self._service.add(group_id, args[1], args[2])
                return f"已添加 Minecraft 服务器「{server.name}」：{server.address}"
            if subcommand == "rm":
                if len(args) != 2:
                    return "用法：/mc rm <名称>"
                server = await self._service.remove(group_id, args[1])
                return f"已删除 Minecraft 服务器「{server.name}」"
            if subcommand == "list":
                if len(args) != 1:
                    return "用法：/mc list"
                return format_server_list(
                    await self._service.list_servers(group_id)
                )
        except MinecraftError as exc:
            return str(exc)
        return "未知子命令。\n" + USAGE

    @staticmethod
    def _extract_args(message: str) -> list[str]:
        parts = shlex.split((message or "").strip(), comments=False, posix=True)
        if not parts:
            return []
        command = parts[0].removeprefix("/")
        if command.casefold() != "mc":
            return []
        return parts[1:]

