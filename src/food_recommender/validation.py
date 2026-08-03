from __future__ import annotations

from .errors import FoodValidationError


MAX_FOOD_NAME_LENGTH = 64
MAX_FOODS_PER_GROUP = 200


def normalize_food_name(name: str) -> str:
    """生成仅用于重复判断和查找的名称。"""
    return name.strip().casefold()


def validate_food_name(name: str) -> str:
    """校验并返回去除首尾空白后的食物名称。"""
    if not isinstance(name, str):
        raise FoodValidationError("食物名称必须是文本。")

    cleaned = name.strip()
    if not cleaned:
        raise FoodValidationError("食物名称不能为空。")
    if len(cleaned) > MAX_FOOD_NAME_LENGTH:
        raise FoodValidationError(
            f"食物名称「{cleaned}」不能超过 {MAX_FOOD_NAME_LENGTH} 个字符。"
        )
    if any(character in cleaned for character in "\r\n\t"):
        raise FoodValidationError(
            f"食物名称「{cleaned}」不能包含换行符或制表符。"
        )
    return cleaned
