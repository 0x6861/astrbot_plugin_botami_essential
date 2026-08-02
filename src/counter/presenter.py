from __future__ import annotations

from .models import CounterSnapshot


def format_counter_list(counters: tuple[CounterSnapshot, ...]) -> str:
    if not counters:
        return "当前没有任何计数器。可用：/cnt add <计数器名> [别名…]"

    lines = ["📊 当前计数器列表："]
    for counter in counters:
        alias_text = "无" if not counter.aliases else "、".join(counter.aliases)
        lines.append(f"  {counter.name}：{counter.count} 次；别名：{alias_text}")
    return "\n".join(lines)


def format_increment_result(counters: tuple[CounterSnapshot, ...]) -> str | None:
    if not counters:
        return None
    if len(counters) == 1:
        counter = counters[0]
        return _special_message(counter) or (
            f"累计 {counter.name} {counter.count}/114514"
        )
    return "\n".join(
        f"累计 {counter.name} {counter.count}/114514" for counter in counters
    )


def _special_message(counter: CounterSnapshot) -> str | None:
    name = counter.name
    count = counter.count
    if count in {114, 1145, 11451, 114514}:
        return f"恶臭的计数器就是「{name}」啦~~~"
    if count in {1919, 19191, 191919}:
        return f"就这？————「{name}」"
    if count in {520, 1314}:
        return f"💗💗💗我爱你! 一生一世! ————「{name}」"
    if count in {6, 66, 666, 6666}:
        return f"{name}, 6"
    if count in {233, 2333, 23333}:
        return "23333————"
    if count in {100, 1000, 10000, 100000}:
        return f"🎉🎉🎉恭喜！计数器「{name}」达成 {count} 次！"
    return None
