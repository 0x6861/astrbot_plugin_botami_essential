from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CounterRecord:
    """计数器的可持久化状态。"""

    name: str
    count: int = 0
    aliases: list[str] = field(default_factory=list)

    def clone(self) -> CounterRecord:
        return CounterRecord(self.name, self.count, list(self.aliases))

    def snapshot(self) -> CounterSnapshot:
        return CounterSnapshot(self.name, self.count, tuple(self.aliases))


@dataclass(frozen=True, slots=True)
class CounterSnapshot:
    """返回给命令与消息适配层的只读计数器快照。"""

    name: str
    count: int
    aliases: tuple[str, ...]
