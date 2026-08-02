from __future__ import annotations

import asyncio
import json
import unittest
from contextlib import suppress
from unittest.mock import patch

from src.minecraft.dns_resolver import SrvResolution
from src.minecraft.models import MinecraftEndpoint, MinecraftServer
from src.minecraft.protocol import (
    MAX_RESPONSE_BYTES,
    MinecraftStatusClient,
    decode_varint,
    encode_varint,
    read_varint,
)


def frame(payload: bytes) -> bytes:
    return encode_varint(len(payload)) + payload


def status_packet(payload: dict) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    body = encode_varint(0) + encode_varint(len(encoded)) + encoded
    return frame(body)


class MinecraftProtocolTests(unittest.IsolatedAsyncioTestCase):
    def test_varint_round_trip_including_negative_protocol_version(self) -> None:
        for value in (0, 1, 127, 128, 25565, 2**31 - 1, -1):
            encoded = encode_varint(value)
            decoded, consumed = decode_varint(encoded)
            expected = value & 0xFFFFFFFF
            self.assertEqual(decoded, expected)
            self.assertEqual(consumed, len(encoded))

    async def test_local_server_status_and_fragmented_response(self) -> None:
        payload = {
            "description": {
                "text": "§a本地服",
                "extra": [{"text": " - 生存"}],
            },
            "players": {
                "online": 2,
                "max": 20,
                "sample": [{"name": "Alice"}, {"name": "Bob"}],
            },
        }

        async def handler(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                handshake_length = await read_varint(reader)
                await reader.readexactly(handshake_length)
                request_length = await read_varint(reader)
                await reader.readexactly(request_length)
                response = status_packet(payload)
                for offset in range(0, len(response), 3):
                    writer.write(response[offset : offset + 3])
                    await writer.drain()
                    await asyncio.sleep(0)
            finally:
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            result = await MinecraftStatusClient().query(
                MinecraftServer("测试服", "127.0.0.1", port)
            )
        finally:
            server.close()
            await server.wait_closed()

        self.assertTrue(result.online)
        self.assertEqual(result.description, "本地服 - 生存")
        self.assertEqual(result.player_names, ("Alice", "Bob"))
        self.assertEqual(result.online_players, 2)

    async def test_invalid_and_oversized_responses_are_offline(self) -> None:
        invalid_json = b"{broken"
        responses = (
            frame(encode_varint(1)),
            encode_varint(MAX_RESPONSE_BYTES + 1),
            frame(
                encode_varint(0)
                + encode_varint(len(invalid_json))
                + invalid_json
            ),
        )
        for response in responses:
            async def handler(_reader, writer, data=response) -> None:
                writer.write(data)
                await writer.drain()
                writer.close()

            local_server = await asyncio.start_server(handler, "127.0.0.1", 0)
            port = local_server.sockets[0].getsockname()[1]
            try:
                result = await MinecraftStatusClient().query(
                    MinecraftServer("测试服", "127.0.0.1", port)
                )
            finally:
                local_server.close()
                await local_server.wait_closed()

            self.assertFalse(result.online)
            self.assertEqual(result.error, "服务器响应格式无效")

    async def test_explicit_port_and_ip_skip_srv_resolution(self) -> None:
        class FailingResolver:
            async def resolve(self, _host: str) -> SrvResolution:
                raise AssertionError("不应查询 SRV")

        client = MinecraftStatusClient(FailingResolver())  # type: ignore[arg-type]

        explicit, _ = await client._resolve_endpoints(
            MinecraftServer("one", "example.com", 25570)
        )
        ip_address, _ = await client._resolve_endpoints(
            MinecraftServer("two", "127.0.0.1")
        )

        self.assertEqual(explicit, (MinecraftEndpoint("example.com", 25570),))
        self.assertEqual(ip_address, (MinecraftEndpoint("127.0.0.1", 25565),))

    async def test_srv_fallback_and_service_unavailable(self) -> None:
        class Resolver:
            def __init__(self, result: SrvResolution):
                self.result = result

            async def resolve(self, _host: str) -> SrvResolution:
                return self.result

        fallback_client = MinecraftStatusClient(Resolver(SrvResolution()))  # type: ignore[arg-type]
        unavailable_client = MinecraftStatusClient(
            Resolver(SrvResolution(service_unavailable=True))  # type: ignore[arg-type]
        )

        fallback, unavailable = await fallback_client._resolve_endpoints(
            MinecraftServer("one", "example.com")
        )
        result = await unavailable_client.query(
            MinecraftServer("two", "example.com")
        )

        self.assertEqual(fallback, (MinecraftEndpoint("example.com", 25565),))
        self.assertFalse(unavailable)
        self.assertFalse(result.online)
        self.assertIn("服务不可用", result.error or "")

    async def test_failed_srv_target_falls_through_to_next_target(self) -> None:
        payload = {"description": "备用节点", "players": {"online": 0, "max": 20}}

        async def handler(reader, writer) -> None:
            handshake_length = await read_varint(reader)
            await reader.readexactly(handshake_length)
            request_length = await read_varint(reader)
            await reader.readexactly(request_length)
            writer.write(status_packet(payload))
            await writer.drain()
            writer.close()

        local_server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = local_server.sockets[0].getsockname()[1]

        class Resolver:
            async def resolve(self, _host: str) -> SrvResolution:
                return SrvResolution(
                    endpoints=(
                        MinecraftEndpoint("127.0.0.1", 1),
                        MinecraftEndpoint("127.0.0.1", port),
                    )
                )

        try:
            result = await MinecraftStatusClient(Resolver()).query(  # type: ignore[arg-type]
                MinecraftServer("测试服", "mc.example.com")
            )
        finally:
            local_server.close()
            await local_server.wait_closed()

        self.assertTrue(result.online)
        self.assertEqual(result.description, "备用节点")

    async def test_timeout_is_reported_without_raising(self) -> None:
        async def handler(_reader, writer) -> None:
            await asyncio.sleep(1)
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with patch("src.minecraft.protocol.QUERY_TIMEOUT_SECONDS", 0.01):
                result = await MinecraftStatusClient().query(
                    MinecraftServer("测试服", "127.0.0.1", port)
                )
        finally:
            server.close()
            await server.wait_closed()

        self.assertFalse(result.online)
        self.assertEqual(result.error, "查询超时")


if __name__ == "__main__":
    unittest.main()
