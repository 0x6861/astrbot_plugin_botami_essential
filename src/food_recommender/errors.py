from __future__ import annotations


class FoodRecommenderError(Exception):
    """食物推荐模块可预期错误的基类。"""


class FoodDataError(FoodRecommenderError):
    """持久化的食物数据无效。"""


class FoodValidationError(FoodRecommenderError):
    """输入的食物名称不合法。"""


class FoodConflictError(FoodRecommenderError):
    """食物名称重复或群食物数量超过限制。"""


class FoodNotFoundError(FoodRecommenderError):
    """待删除的食物不存在。"""


class FoodListEmptyError(FoodRecommenderError):
    """当前群的食物库为空。"""
