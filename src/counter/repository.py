from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..atomic_json import write_json_atomic
from .errors import CounterDataError
from .models import CounterRecord


SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CounterLoadResult:
    """仓储加载结果及可选的迁移来源。"""

    counters: dict[str, CounterRecord]
    migrated_from: Path | None = None


class CounterRepository:
    """负责计数器 JSON 的校验、迁移与原子写入。"""

    def __init__(self, data_file: Path, legacy_data_file: Path | None = None):
        self.data_file = data_file
        self.legacy_data_file = legacy_data_file

    async def load(self) -> CounterLoadResult:
        return await asyncio.to_thread(self._load_sync)

    async def save(self, counters: dict[str, CounterRecord]) -> None:
        snapshot = {name: record.clone() for name, record in counters.items()}
        await asyncio.to_thread(self._save_sync, snapshot)

    def _load_sync(self) -> CounterLoadResult:
        if self.data_file.exists():
            return CounterLoadResult(self._read_file(self.data_file))

        legacy_file = self.legacy_data_file
        if legacy_file is not None and legacy_file.exists():
            counters = self._read_file(legacy_file)
            self._save_sync(counters)
            return CounterLoadResult(counters, legacy_file)

        return CounterLoadResult({})

    def _read_file(self, path: Path) -> dict[str, CounterRecord]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CounterDataError(f"无法读取计数器数据文件 {path}: {exc}") from exc
        return self._decode(raw, path)

    @staticmethod
    def _decode(raw: Any, path: Path) -> dict[str, CounterRecord]:
        if not isinstance(raw, dict) or not isinstance(raw.get("counters"), dict):
            raise CounterDataError(f"计数器数据文件 {path} 缺少 counters 对象。")

        version = raw.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise CounterDataError(
                f"计数器数据文件 {path} 的版本 {version!r} 不受支持。"
            )

        raw_counters: dict[Any, Any] = raw["counters"]
        counters: dict[str, CounterRecord] = {}
        name_index: dict[str, str] = {}

        for name, metadata in raw_counters.items():
            if not isinstance(name, str) or not name.strip():
                raise CounterDataError(f"计数器数据文件 {path} 包含无效主名称。")
            normalized_name = _normalize(name)
            if normalized_name in name_index:
                raise CounterDataError(f"计数器数据文件 {path} 包含重复主名称 {name!r}。")
            if not isinstance(metadata, dict):
                raise CounterDataError(f"计数器 {name!r} 的数据必须是对象。")

            count = metadata.get("count", 0)
            aliases = metadata.get("aliases", [])
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise CounterDataError(f"计数器 {name!r} 的 count 必须是非负整数。")
            if not isinstance(aliases, list) or not all(
                isinstance(alias, str) for alias in aliases
            ):
                raise CounterDataError(f"计数器 {name!r} 的 aliases 必须是字符串数组。")

            name_index[normalized_name] = name
            counters[name] = CounterRecord(name=name, count=count, aliases=[])

        alias_index: dict[str, str] = {}
        for name, metadata in raw_counters.items():
            aliases = metadata.get("aliases", [])
            normalized_name = _normalize(name)
            for alias in aliases:
                normalized_alias = _normalize(alias)
                # 兼容旧版本可能写入的空别名、同名别名及同一计数器的重复别名。
                if not normalized_alias or normalized_alias == normalized_name:
                    continue
                if normalized_alias in name_index:
                    raise CounterDataError(
                        f"计数器 {name!r} 的别名 {alias!r} 与主名称冲突。"
                    )
                owner = alias_index.get(normalized_alias)
                if owner is not None and owner != name:
                    raise CounterDataError(
                        f"别名 {alias!r} 同时属于计数器 {owner!r} 和 {name!r}。"
                    )
                if owner is None:
                    alias_index[normalized_alias] = name
                    counters[name].aliases.append(alias.strip())

        return counters

    def _save_sync(self, counters: dict[str, CounterRecord]) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "counters": {
                name: {"count": record.count, "aliases": list(record.aliases)}
                for name, record in counters.items()
            },
        }
        write_json_atomic(self.data_file, payload)


def _normalize(value: str) -> str:
    return value.strip().casefold()
