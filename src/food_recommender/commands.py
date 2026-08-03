from __future__ import annotations

import shlex

from .errors import FoodRecommenderError
from .presenter import format_food_list, format_recommendation
from .service import FoodRecommenderService


USAGE = (
    "用法：/今天吃什么；/今天吃什么 add <食物1> [食物2 ...]；"
    "/今天吃什么 rm <食物1> [食物2 ...]；/今天吃什么 list。"
    "名称包含空格时请使用引号。"
)


class FoodCommandProcessor:
    """解析 `/今天吃什么` 命令并委托给食物推荐服务。"""

    def __init__(self, service: FoodRecommenderService):
        self._service = service

    async def handle(self, message: str, group_id: str) -> str:
        try:
            args = self._extract_args(message)
        except ValueError:
            return "命令中的引号未正确闭合。\n" + USAGE

        try:
            if not args:
                return format_recommendation(
                    await self._service.recommend(group_id)
                )

            subcommand = args[0].casefold()
            if subcommand == "add":
                if len(args) < 2:
                    return "用法：/今天吃什么 add <食物1> [食物2 ...]"
                foods = await self._service.add(group_id, args[1:])
                return "已添加食物：" + "、".join(foods)
            if subcommand == "rm":
                if len(args) < 2:
                    return "用法：/今天吃什么 rm <食物1> [食物2 ...]"
                foods = await self._service.remove(group_id, args[1:])
                return "已删除食物：" + "、".join(foods)
            if subcommand == "list":
                if len(args) != 1:
                    return "用法：/今天吃什么 list"
                return format_food_list(await self._service.list_foods(group_id))
        except FoodRecommenderError as exc:
            return str(exc)
        return "未知子命令。\n" + USAGE

    @staticmethod
    def _extract_args(message: str) -> list[str]:
        parts = shlex.split((message or "").strip(), comments=False, posix=True)
        if not parts:
            return []
        command = parts[0].removeprefix("/")
        if command.casefold() != "今天吃什么":
            return []
        return parts[1:]
