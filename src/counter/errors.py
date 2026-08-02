from __future__ import annotations


class CounterError(Exception):
    """计数器模块可预期业务错误的基类。"""


class CounterConflictError(CounterError):
    """名称或别名存在冲突。"""

    def __init__(self, conflicts: list[str]):
        super().__init__("；".join(conflicts))
        self.conflicts = tuple(conflicts)


class CounterNotFoundError(CounterError):
    """计数器或别名不存在。"""


class CounterDataError(CounterError):
    """持久化数据格式不合法。"""
