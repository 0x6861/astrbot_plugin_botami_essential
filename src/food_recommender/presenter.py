from __future__ import annotations


EMPTY_LIST_MESSAGE = (
    "当前群食物库为空，请先通过 /今天吃什么 add <食物...> 添加食物。"
)


def format_recommendation(food: str) -> str:
    return f"今天吃 {food} ！"


def format_food_list(foods: tuple[str, ...]) -> str:
    if not foods:
        return EMPTY_LIST_MESSAGE
    lines = ["当前群的食物："]
    lines.extend(
        f"[{index}] {food}" for index, food in enumerate(foods, start=1)
    )
    return "\n".join(lines)
