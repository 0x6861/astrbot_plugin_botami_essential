from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MINECRAFT_PORT = 25565


@dataclass(frozen=True, slots=True)
class MinecraftServer:
    """用户登记的 Minecraft Java 版服务器。"""

    name: str
    host: str
    port: int | None = None

    @property
    def address(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        if self.port is None:
            return host
        return f"{host}:{self.port}"


@dataclass(frozen=True, slots=True)
class MinecraftEndpoint:
    """一次实际连接使用的主机和端口。"""

    host: str
    port: int


@dataclass(frozen=True, slots=True)
class MinecraftStatus:
    """服务器状态查询结果。"""

    server: MinecraftServer
    online: bool
    description: str = ""
    online_players: int = 0
    max_players: int = 0
    player_names: tuple[str, ...] = ()
    error: str | None = None

