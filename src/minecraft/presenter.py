from __future__ import annotations

from .models import MinecraftServer, MinecraftStatus


def format_server_list(servers: tuple[MinecraftServer, ...]) -> str:
    if not servers:
        return "当前群尚未添加 Minecraft 服务器。"
    lines = ["当前群的 Minecraft 服务器："]
    lines.extend(
        f"[{index}] {server.name} - {server.address}"
        for index, server in enumerate(servers, start=1)
    )
    return "\n".join(lines)


def format_statuses(statuses: tuple[MinecraftStatus, ...]) -> str:
    if not statuses:
        return "当前群尚未添加 Minecraft 服务器。"
    return "\n\n".join(
        _format_status(index, status)
        for index, status in enumerate(statuses, start=1)
    )


def _format_status(index: int, status: MinecraftStatus) -> str:
    if not status.online:
        return f"🔴 [{index}] {status.server.name}\n无法连接：{status.error or '未知错误'}"

    description = status.description or "(无服务器简介)"
    if status.online_players == 0:
        players = "在线玩家：(无)"
    elif status.player_names:
        players = f"在线玩家：{', '.join(status.player_names)}"
    else:
        players = (
            "在线玩家：服务器未提供名单"
            f"（在线 {status.online_players}/{status.max_players}）"
        )
    return f"🟢 [{index}] {status.server.name}\n{description}\n{players}"

