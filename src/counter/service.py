from __future__ import annotations

import asyncio

from .errors import CounterConflictError, CounterNotFoundError
from .models import CounterRecord, CounterSnapshot
from .repository import CounterRepository


class CounterService:
    """封装计数器规则，并保证内存状态与磁盘提交的一致性。"""

    def __init__(
        self,
        repository: CounterRepository,
        counters: dict[str, CounterRecord] | None = None,
    ):
        self._repository = repository
        self._counters = self._clone(counters or {})
        self._lock = asyncio.Lock()

    async def add(self, name: str, aliases: list[str]) -> CounterSnapshot:
        name = name.strip()
        aliases = [alias.strip() for alias in aliases]

        async with self._lock:
            names, alias_index = self._build_indexes(self._counters)
            normalized_name = self.normalize(name)
            conflicts: list[str] = []
            if not normalized_name or normalized_name in names or normalized_name in alias_index:
                conflicts.append(f"计数器「{name}」已存在或被占用")

            normalized_request_aliases: set[str] = set()
            for alias in aliases:
                normalized_alias = self.normalize(alias)
                if not normalized_alias or normalized_alias == normalized_name:
                    conflicts.append(f"别名「{alias}」无效（为空或与主名相同）")
                elif normalized_alias in normalized_request_aliases:
                    conflicts.append(f"别名「{alias}」在本次请求中重复")
                elif normalized_alias in names:
                    conflicts.append(f"别名「{alias}」与已有主名冲突")
                elif normalized_alias in alias_index:
                    conflicts.append(f"别名「{alias}」已被其它计数器占用")
                normalized_request_aliases.add(normalized_alias)

            if conflicts:
                raise CounterConflictError(conflicts)

            updated = self._clone(self._counters)
            updated[name] = CounterRecord(name=name, aliases=aliases)
            await self._commit(updated)
            return self._counters[name].snapshot()

    async def delete(self, token: str) -> CounterSnapshot:
        async with self._lock:
            true_name = self._resolve_name(token, allow_alias=True)
            removed = self._counters[true_name].snapshot()
            updated = self._clone(self._counters)
            del updated[true_name]
            await self._commit(updated)
            return removed

    async def add_aliases(self, name: str, aliases: list[str]) -> CounterSnapshot:
        aliases = [alias.strip() for alias in aliases]
        async with self._lock:
            true_name = self._resolve_name(name, allow_alias=False)
            names, alias_index = self._build_indexes(self._counters)
            normalized_name = self.normalize(true_name)
            existing_aliases = {
                self.normalize(alias) for alias in self._counters[true_name].aliases
            }
            normalized_request_aliases: set[str] = set()
            conflicts: list[str] = []

            for alias in aliases:
                normalized_alias = self.normalize(alias)
                if not normalized_alias or normalized_alias == normalized_name:
                    conflicts.append(f"别名「{alias}」无效（为空或与主名相同）")
                elif normalized_alias in normalized_request_aliases:
                    conflicts.append(f"别名「{alias}」在本次请求中重复")
                elif normalized_alias in names:
                    conflicts.append(f"别名「{alias}」与已有主名冲突")
                elif normalized_alias in alias_index and alias_index[normalized_alias] != true_name:
                    conflicts.append(f"别名「{alias}」已被其它计数器占用")
                elif normalized_alias in existing_aliases:
                    conflicts.append(f"别名「{alias}」已存在于计数器「{true_name}」中")
                normalized_request_aliases.add(normalized_alias)

            if conflicts:
                raise CounterConflictError(conflicts)

            updated = self._clone(self._counters)
            updated[true_name].aliases.extend(aliases)
            await self._commit(updated)
            return self._counters[true_name].snapshot()

    async def delete_alias(self, alias: str) -> tuple[CounterSnapshot, str]:
        normalized_alias = self.normalize(alias)
        async with self._lock:
            _, alias_index = self._build_indexes(self._counters)
            true_name = alias_index.get(normalized_alias)
            if true_name is None:
                raise CounterNotFoundError(f"未找到别名「{alias}」")

            updated = self._clone(self._counters)
            updated[true_name].aliases = [
                item
                for item in updated[true_name].aliases
                if self.normalize(item) != normalized_alias
            ]
            await self._commit(updated)
            return self._counters[true_name].snapshot(), alias

    async def list_counters(self) -> tuple[CounterSnapshot, ...]:
        async with self._lock:
            ordered = sorted(
                self._counters.values(), key=lambda counter: counter.count, reverse=True
            )
            return tuple(counter.snapshot() for counter in ordered)

    async def increment_matching(self, text: str) -> tuple[CounterSnapshot, ...]:
        normalized_text = self.normalize(text)
        if not normalized_text:
            return ()

        async with self._lock:
            updated = self._clone(self._counters)
            hit_names: list[str] = []
            for name, counter in updated.items():
                patterns = (name, *counter.aliases)
                if any(
                    normalized_pattern and normalized_pattern in normalized_text
                    for normalized_pattern in map(self.normalize, patterns)
                ):
                    counter.count += 1
                    hit_names.append(name)

            if not hit_names:
                return ()

            await self._commit(updated)
            return tuple(self._counters[name].snapshot() for name in hit_names)

    async def flush(self) -> None:
        async with self._lock:
            await self._repository.save(self._counters)

    def _resolve_name(self, token: str, *, allow_alias: bool) -> str:
        names, aliases = self._build_indexes(self._counters)
        normalized_token = self.normalize(token)
        if normalized_token in names:
            return names[normalized_token]
        if allow_alias and normalized_token in aliases:
            return aliases[normalized_token]
        raise CounterNotFoundError(f"未找到计数器「{token}」")

    async def _commit(self, updated: dict[str, CounterRecord]) -> None:
        await self._repository.save(updated)
        self._counters = updated

    @staticmethod
    def normalize(value: str) -> str:
        return (value or "").strip().casefold()

    @classmethod
    def _build_indexes(
        cls, counters: dict[str, CounterRecord]
    ) -> tuple[dict[str, str], dict[str, str]]:
        names = {cls.normalize(name): name for name in counters}
        aliases = {
            cls.normalize(alias): name
            for name, counter in counters.items()
            for alias in counter.aliases
        }
        return names, aliases

    @staticmethod
    def _clone(counters: dict[str, CounterRecord]) -> dict[str, CounterRecord]:
        return {name: counter.clone() for name, counter in counters.items()}
