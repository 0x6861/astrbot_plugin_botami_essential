from __future__ import annotations

import ipaddress
import re

from .errors import MinecraftValidationError
from .models import MinecraftServer


MAX_NAME_LENGTH = 64
MAX_HOST_LENGTH = 253
_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_BRACKETED_ADDRESS = re.compile(r"^\[([^\]]+)](?::([0-9]+))?$")


def parse_server(name: str, address: str) -> MinecraftServer:
    """校验用户输入并拆分服务器名称、主机和可选端口。"""
    normalized_name = name.strip()
    if not normalized_name or len(normalized_name) > MAX_NAME_LENGTH:
        raise MinecraftValidationError("服务器名称必须为 1 至 64 个字符。")
    if any(character in normalized_name for character in "\r\n\t"):
        raise MinecraftValidationError("服务器名称不能包含换行或制表符。")

    host, port = _split_address(address.strip())
    return MinecraftServer(
        name=normalized_name,
        host=_normalize_host(host),
        port=port,
    )


def _split_address(address: str) -> tuple[str, int | None]:
    if not address:
        raise MinecraftValidationError("服务器地址不能为空。")

    if address.startswith("["):
        match = _BRACKETED_ADDRESS.fullmatch(address)
        if match is None:
            raise MinecraftValidationError("IPv6 地址必须使用 [地址]:端口 格式。")
        return match.group(1), _parse_port(match.group(2))

    colon_count = address.count(":")
    if colon_count == 0:
        return address, None
    if colon_count == 1:
        host, raw_port = address.rsplit(":", 1)
        if not host or not raw_port:
            raise MinecraftValidationError("服务器地址格式无效。")
        return host, _parse_port(raw_port)
    raise MinecraftValidationError("IPv6 地址必须放在方括号中。")


def _parse_port(raw_port: str | None) -> int | None:
    if raw_port is None:
        return None
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise MinecraftValidationError("服务器端口必须是整数。") from exc
    if not 1 <= port <= 65535:
        raise MinecraftValidationError("服务器端口必须在 1 至 65535 之间。")
    return port


def _normalize_host(host: str) -> str:
    value = host.strip().rstrip(".")
    if not value:
        raise MinecraftValidationError("服务器主机不能为空。")

    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        pass

    try:
        ascii_host = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise MinecraftValidationError("服务器域名格式无效。") from exc
    if len(ascii_host) > MAX_HOST_LENGTH:
        raise MinecraftValidationError("服务器域名过长。")
    if not all(_HOST_LABEL.fullmatch(label) for label in ascii_host.split(".")):
        raise MinecraftValidationError("服务器域名格式无效。")
    return ascii_host.casefold()


def is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True

