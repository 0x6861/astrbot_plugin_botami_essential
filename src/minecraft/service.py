from __future__ import annotations

import asyncio

from .address import parse_server
from .errors import MinecraftConflictError, MinecraftNotFoundError
from .models import MinecraftServer, MinecraftStatus
from .protocol import MinecraftStatusClient
from .repository import MinecraftRepository


MAX_SERVERS_PER_GROUP = 20
MAX_CONCURRENT_QUERIES = 8


class MinecraftService:
    """管理群内服务器列表，并协调并发状态查询。"""

    def __init__(
        self,
        repository: MinecraftRepository,
        groups: dict[str, list[MinecraftServer]] | None = None,
        *,
        status_client: MinecraftStatusClient | None = None,
    ):
        self._repository = repository
        self._groups = self._clone(groups or {})
        self._status_client = status_client or MinecraftStatusClient()
        self._lock = asyncio.Lock()

    async def add(self, group_id: str, name: str, address: str) -> MinecraftServer:
        server = parse_server(name, address)
        async with self._lock:
            current = self._groups.get(group_id, [])
            if len(current) >= MAX_SERVERS_PER_GROUP:
                raise MinecraftConflictError("每个群最多添加 20 台服务器。")
            if any(item.name.casefold() == server.name.casefold() for item in current):
                raise MinecraftConflictError(f"服务器名称「{server.name}」已存在。")
            if any(
                item.host.casefold() == server.host.casefold()
                and item.port == server.port
                for item in current
            ):
                raise MinecraftConflictError(f"服务器地址「{server.address}」已存在。")

            updated = self._clone(self._groups)
            updated.setdefault(group_id, []).append(server)
            await self._commit(updated)
            return server

    async def remove(self, group_id: str, name: str) -> MinecraftServer:
        normalized_name = name.strip().casefold()
        async with self._lock:
            current = self._groups.get(group_id, [])
            removed = next(
                (
                    server
                    for server in current
                    if server.name.casefold() == normalized_name
                ),
                None,
            )
            if removed is None:
                raise MinecraftNotFoundError(f"未找到服务器「{name.strip()}」。")

            updated = self._clone(self._groups)
            updated[group_id] = [
                server
                for server in updated[group_id]
                if server.name.casefold() != normalized_name
            ]
            await self._commit(updated)
            return removed

    async def list_servers(self, group_id: str) -> tuple[MinecraftServer, ...]:
        async with self._lock:
            return tuple(self._groups.get(group_id, ()))

    async def query_all(self, group_id: str) -> tuple[MinecraftStatus, ...]:
        servers = await self.list_servers(group_id)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_QUERIES)

        async def query(server: MinecraftServer) -> MinecraftStatus:
            async with semaphore:
                return await self._status_client.query(server)

        return tuple(await asyncio.gather(*(query(server) for server in servers)))

    async def flush(self) -> None:
        async with self._lock:
            await self._repository.save(self._groups)

    async def _commit(self, updated: dict[str, list[MinecraftServer]]) -> None:
        await self._repository.save(updated)
        self._groups = updated

    @staticmethod
    def _clone(
        groups: dict[str, list[MinecraftServer]],
    ) -> dict[str, list[MinecraftServer]]:
        return {group_id: list(servers) for group_id, servers in groups.items()}

