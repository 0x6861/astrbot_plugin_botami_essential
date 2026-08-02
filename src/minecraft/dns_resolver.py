from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import dns.asyncresolver

from .models import MinecraftEndpoint


DNS_SERVERS = ("223.5.5.5", "223.6.6.6", "1.1.1.1")
DNS_TIMEOUT_SECONDS = 1.0
NEGATIVE_CACHE_SECONDS = 60
MIN_CACHE_SECONDS = 30
MAX_CACHE_SECONDS = 600


@dataclass(frozen=True, slots=True)
class SrvRecord:
    priority: int
    weight: int
    port: int
    target: str


@dataclass(frozen=True, slots=True)
class SrvAnswer:
    records: tuple[SrvRecord, ...]
    ttl: int


@dataclass(frozen=True, slots=True)
class SrvResolution:
    endpoints: tuple[MinecraftEndpoint, ...] = ()
    service_unavailable: bool = False


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    resolution: SrvResolution
    expires_at: float


class DnsSrvQuery:
    """使用指定 DNS 服务器发起单次异步 SRV 查询。"""

    async def __call__(
        self, nameserver: str, query_name: str, timeout: float
    ) -> SrvAnswer:
        resolver = dns.asyncresolver.Resolver(configure=False)
        resolver.nameservers = [nameserver]
        resolver.timeout = timeout
        resolver.lifetime = timeout
        answer = await resolver.resolve(
            query_name,
            "SRV",
            search=False,
            lifetime=timeout,
            raise_on_no_answer=False,
        )
        if answer.rrset is None:
            return SrvAnswer((), NEGATIVE_CACHE_SECONDS)

        records = tuple(
            SrvRecord(
                priority=int(record.priority),
                weight=int(record.weight),
                port=int(record.port),
                target=record.target.to_text(omit_final_dot=True),
            )
            for record in answer
        )
        return SrvAnswer(records, int(answer.rrset.ttl))


class MinecraftSrvResolver:
    """依次查询固定 DNS，并缓存 Minecraft SRV 解析结果。"""

    def __init__(
        self,
        *,
        query: Callable[[str, str, float], Awaitable[SrvAnswer]] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._query = query or DnsSrvQuery()
        self._clock = clock or time.monotonic
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def resolve(self, host: str) -> SrvResolution:
        cache_key = host.casefold()
        now = self._clock()
        cached = self._cache.get(cache_key)
        if cached is not None and cached.expires_at > now:
            return cached.resolution

        async with self._lock:
            now = self._clock()
            cached = self._cache.get(cache_key)
            if cached is not None and cached.expires_at > now:
                return cached.resolution

            query_name = f"_minecraft._tcp.{host}."
            answer: SrvAnswer | None = None
            for nameserver in DNS_SERVERS:
                try:
                    current = await self._query(
                        nameserver, query_name, DNS_TIMEOUT_SECONDS
                    )
                except Exception:
                    continue
                if current.records:
                    answer = current
                    break

            resolution = self._to_resolution(answer)
            ttl = (
                _bounded_ttl(answer.ttl)
                if answer is not None
                else NEGATIVE_CACHE_SECONDS
            )
            self._cache[cache_key] = _CacheEntry(
                resolution=resolution,
                expires_at=now + ttl,
            )
            return resolution

    @staticmethod
    def _to_resolution(answer: SrvAnswer | None) -> SrvResolution:
        if answer is None:
            return SrvResolution()
        if any(record.target in {"", "."} for record in answer.records):
            return SrvResolution(service_unavailable=True)

        ordered = sorted(
            answer.records,
            key=lambda record: (record.priority, -record.weight, record.target),
        )
        return SrvResolution(
            endpoints=tuple(
                MinecraftEndpoint(record.target.rstrip("."), record.port)
                for record in ordered
            )
        )


def _bounded_ttl(ttl: int) -> int:
    return max(MIN_CACHE_SECONDS, min(ttl, MAX_CACHE_SECONDS))

