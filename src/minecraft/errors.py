from __future__ import annotations


class MinecraftError(Exception):
    """Minecraft 模块可预期错误的基类。"""


class MinecraftDataError(MinecraftError):
    """服务器列表持久化数据无效。"""


class MinecraftConflictError(MinecraftError):
    """服务器名称或地址冲突。"""


class MinecraftNotFoundError(MinecraftError):
    """未找到指定服务器。"""


class MinecraftValidationError(MinecraftError):
    """服务器名称或地址不合法。"""


class MinecraftProtocolError(MinecraftError):
    """Minecraft 状态响应不符合协议。"""

