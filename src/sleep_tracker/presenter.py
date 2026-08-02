from __future__ import annotations

from .calendar import to_root_calendar
from .models import GoodMorningResult, GoodNightResult


def format_good_night(display_name: str, result: GoodNightResult) -> str:
    current_date = to_root_calendar(result.current_at.date())
    current_time = result.current_at.strftime("%H:%M:%S")
    return (
        f"晚安，{display_name}！\n"
        f"现在是{current_date} {current_time}，"
        f"你是本群今天第{result.rank}个睡觉的 ~"
    )


def format_good_morning(display_name: str, result: GoodMorningResult) -> str:
    current_date = to_root_calendar(result.current_at.date())
    current_time = result.current_at.strftime("%H:%M:%S")
    lines = [
        f"早安，{display_name}！",
        f"现在是{current_date} {current_time}。",
    ]
    if result.slept_minutes is not None:
        hours, minutes = divmod(result.slept_minutes, 60)
        lines.append(f"昨晚你睡了 {hours}小时{minutes}分 ~")
    return "\n".join(lines)
