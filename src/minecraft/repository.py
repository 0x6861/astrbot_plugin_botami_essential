from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..atomic_json import write_json_atomic
from .address import parse_server
from .errors import MinecraftDataError, MinecraftValidationError
from .models import MinecraftServer


SCHEMA_VERSION = 1


class MinecraftRepository:
    """负责按群保存 Minecraft 服务器列表。"""

    def __init__(self, data_file: Path):
        self.data_file = data_file

    async def load(self) -> dict[str, list[MinecraftServer]]:
        return await asyncio.to_thread(self._load_sync)

    async def save(self, groups: dict[str, list[MinecraftServer]]) -> None:
        snapshot = {
            group_id: list(servers) for group_id, servers in groups.items()
        }
        await asyncio.to_thread(self._save_sync, snapshot)

    def _load_sync(self) -> dict[str, list[MinecraftServer]]:
        if not self.data_file.exists():
            return {}
        try:
            raw = json.loads(self.data_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MinecraftDataError(
                f"无法读取 Minecraft 服务器文件 {self.data_file}: {exc}"
            ) from exc
        return self._decode(raw)

    def _decode(self, raw: Any) -> dict[str, list[MinecraftServer]]:
        if not isinstance(raw, dict) or not isinstance(raw.get("groups"), dict):
            raise MinecraftDataError(
                f"Minecraft 服务器文件 {self.data_file} 缺少 groups 对象。"
            )
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise MinecraftDataError(
                f"Minecraft 服务器文件 {self.data_file} 的版本不受支持。"
            )

        groups: dict[str, list[MinecraftServer]] = {}
        for group_id, raw_servers in raw["groups"].items():
            if not isinstance(group_id, str) or not group_id:
                raise MinecraftDataError("Minecraft 服务器文件包含无效群 ID。")
            if not isinstance(raw_servers, list):
                raise MinecraftDataError(f"群 {group_id!r} 的服务器列表必须是数组。")

            servers: list[MinecraftServer] = []
            names: set[str] = set()
            endpoints: set[tuple[str, int | None]] = set()
            for metadata in raw_servers:
                if not isinstance(metadata, dict):
                    raise MinecraftDataError("服务器记录必须是对象。")
                name = metadata.get("name")
                host = metadata.get("host")
                port = metadata.get("port")
                if not isinstance(name, str) or not isinstance(host, str):
                    raise MinecraftDataError("服务器记录缺少有效名称或主机。")
                if port is not None and (
                    isinstance(port, bool) or not isinstance(port, int)
                ):
                    raise MinecraftDataError("服务器端口必须是整数或 null。")
                address = f"[{host}]" if ":" in host else host
                if port is not None:
                    address += f":{port}"
                try:
                    server = parse_server(name, address)
                except MinecraftValidationError as exc:
                    raise MinecraftDataError(f"服务器记录无效：{exc}") from exc

                normalized_name = server.name.casefold()
                endpoint = (server.host.casefold(), server.port)
                if normalized_name in names or endpoint in endpoints:
                    raise MinecraftDataError("服务器文件包含重复名称或地址。")
                names.add(normalized_name)
                endpoints.add(endpoint)
                servers.append(server)
            groups[group_id] = servers
        return groups

    def _save_sync(self, groups: dict[str, list[MinecraftServer]]) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "groups": {
                group_id: [
                    {"name": server.name, "host": server.host, "port": server.port}
                    for server in servers
                ]
                for group_id, servers in groups.items()
            },
        }
        write_json_atomic(self.data_file, payload)

