from __future__ import annotations

import asyncio
import json
import re
import struct
from contextlib import suppress
from typing import Any

from .address import is_ip_address
from .dns_resolver import MinecraftSrvResolver
from .errors import MinecraftProtocolError
from .models import (
    DEFAULT_MINECRAFT_PORT,
    MinecraftEndpoint,
    MinecraftServer,
    MinecraftStatus,
)


QUERY_TIMEOUT_SECONDS = 3.0
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_VARINT_BYTES = 5
_FORMATTING_CODE = re.compile(r"§[0-9A-FK-ORa-fk-or]")


class MinecraftStatusClient:
    """通过 Java Server List Ping 协议直连查询服务器。"""

    def __init__(self, resolver: MinecraftSrvResolver | None = None):
        self._resolver = resolver or MinecraftSrvResolver()

    async def query(self, server: MinecraftServer) -> MinecraftStatus:
        endpoints, unavailable = await self._resolve_endpoints(server)
        if unavailable:
            return _offline(server, "SRV 记录声明服务不可用")

        last_error = "网络连接失败"
        for endpoint in endpoints:
            try:
                payload = await asyncio.wait_for(
                    self._query_endpoint(endpoint, server.host),
                    timeout=QUERY_TIMEOUT_SECONDS,
                )
                return _decode_status(server, payload)
            except TimeoutError:
                last_error = "查询超时"
            except ConnectionRefusedError:
                last_error = "连接被拒绝"
            except MinecraftProtocolError:
                last_error = "服务器响应格式无效"
            except (UnicodeError, json.JSONDecodeError):
                last_error = "服务器响应格式无效"
            except OSError:
                last_error = "网络连接失败"
        return _offline(server, last_error)

    async def _resolve_endpoints(
        self, server: MinecraftServer
    ) -> tuple[tuple[MinecraftEndpoint, ...], bool]:
        if server.port is not None:
            return (MinecraftEndpoint(server.host, server.port),), False
        if is_ip_address(server.host):
            return (
                MinecraftEndpoint(server.host, DEFAULT_MINECRAFT_PORT),
            ), False

        resolution = await self._resolver.resolve(server.host)
        if resolution.service_unavailable:
            return (), True
        if resolution.endpoints:
            return resolution.endpoints, False
        return (
            MinecraftEndpoint(server.host, DEFAULT_MINECRAFT_PORT),
        ), False

    @staticmethod
    async def _query_endpoint(
        endpoint: MinecraftEndpoint, handshake_host: str
    ) -> dict[str, Any]:
        reader: asyncio.StreamReader
        writer: asyncio.StreamWriter
        reader, writer = await asyncio.open_connection(endpoint.host, endpoint.port)
        try:
            handshake = (
                encode_varint(0)
                + encode_varint(-1)
                + _encode_string(handshake_host)
                + struct.pack(">H", endpoint.port)
                + encode_varint(1)
            )
            writer.write(_frame(handshake))
            writer.write(_frame(encode_varint(0)))
            await writer.drain()

            packet_length = await read_varint(reader)
            if not 0 < packet_length <= MAX_RESPONSE_BYTES:
                raise MinecraftProtocolError("状态响应长度无效。")
            packet = await reader.readexactly(packet_length)
            packet_id, offset = decode_varint(packet)
            if packet_id != 0:
                raise MinecraftProtocolError("状态响应包 ID 无效。")
            text_length, consumed = decode_varint(packet[offset:])
            offset += consumed
            if text_length < 0 or text_length > MAX_RESPONSE_BYTES:
                raise MinecraftProtocolError("状态 JSON 长度无效。")
            if offset + text_length != len(packet):
                raise MinecraftProtocolError("状态 JSON 长度与响应不一致。")
            decoded = json.loads(packet[offset:].decode("utf-8"))
            if not isinstance(decoded, dict):
                raise MinecraftProtocolError("状态 JSON 必须是对象。")
            return decoded
        except asyncio.IncompleteReadError as exc:
            raise MinecraftProtocolError("状态响应不完整。") from exc
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


def encode_varint(value: int) -> bytes:
    value &= 0xFFFFFFFF
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            byte |= 0x80
        encoded.append(byte)
        if not value:
            return bytes(encoded)


async def read_varint(reader: asyncio.StreamReader) -> int:
    result = 0
    for index in range(MAX_VARINT_BYTES):
        byte = (await reader.readexactly(1))[0]
        result |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return result
    raise MinecraftProtocolError("VarInt 超过 5 字节。")


def decode_varint(data: bytes) -> tuple[int, int]:
    result = 0
    for index, byte in enumerate(data[:MAX_VARINT_BYTES]):
        result |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return result, index + 1
    raise MinecraftProtocolError("VarInt 不完整或超过 5 字节。")


def _frame(payload: bytes) -> bytes:
    return encode_varint(len(payload)) + payload


def _encode_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return encode_varint(len(encoded)) + encoded


def _decode_status(
    server: MinecraftServer, payload: dict[str, Any]
) -> MinecraftStatus:
    players = payload.get("players", {})
    if not isinstance(players, dict):
        raise MinecraftProtocolError("players 必须是对象。")
    online = players.get("online", 0)
    maximum = players.get("max", 0)
    if (
        isinstance(online, bool)
        or not isinstance(online, int)
        or online < 0
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum < 0
    ):
        raise MinecraftProtocolError("玩家数量无效。")

    sample = players.get("sample", [])
    names: list[str] = []
    if isinstance(sample, list):
        for item in sample[:100]:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                name = _clean_text(item["name"])
                if name:
                    names.append(name[:64])

    return MinecraftStatus(
        server=server,
        online=True,
        description=_flatten_chat_component(payload.get("description"))[:512],
        online_players=online,
        max_players=maximum,
        player_names=tuple(names),
    )


def _flatten_chat_component(value: Any) -> str:
    return _clean_text(_flatten_raw_chat_component(value))


def _flatten_raw_chat_component(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_flatten_raw_chat_component(item) for item in value)
    if not isinstance(value, dict):
        return ""

    parts: list[str] = []
    text = value.get("text")
    if isinstance(text, str):
        parts.append(text)
    elif isinstance(value.get("translate"), str):
        parts.append(value["translate"])
    extra = value.get("extra")
    if isinstance(extra, list):
        parts.extend(_flatten_raw_chat_component(item) for item in extra)
    return "".join(parts)


def _clean_text(value: str) -> str:
    cleaned = _FORMATTING_CODE.sub("", value)
    return " ".join(cleaned.replace("\x00", "").split())


def _offline(server: MinecraftServer, error: str) -> MinecraftStatus:
    return MinecraftStatus(server=server, online=False, error=error)
