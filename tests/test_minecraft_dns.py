from __future__ import annotations

import unittest

from src.minecraft.dns_resolver import (
    DNS_SERVERS,
    MinecraftSrvResolver,
    SrvAnswer,
    SrvRecord,
)


class MutableClock:
    def __init__(self) -> None:
        self.current = 100.0

    def __call__(self) -> float:
        return self.current


class MinecraftSrvResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_dns_servers_are_queried_in_order_until_success(self) -> None:
        calls: list[tuple[str, str, float]] = []

        async def query(nameserver: str, name: str, timeout: float) -> SrvAnswer:
            calls.append((nameserver, name, timeout))
            if nameserver != DNS_SERVERS[-1]:
                raise TimeoutError
            return SrvAnswer(
                (SrvRecord(0, 10, 25566, "target.example.com"),),
                ttl=120,
            )

        resolver = MinecraftSrvResolver(query=query)
        result = await resolver.resolve("mc.example.com")

        self.assertEqual([item[0] for item in calls], list(DNS_SERVERS))
        self.assertTrue(
            all(item[1] == "_minecraft._tcp.mc.example.com." for item in calls)
        )
        self.assertEqual(result.endpoints[0].host, "target.example.com")
        self.assertEqual(result.endpoints[0].port, 25566)

    async def test_records_are_ordered_by_priority_then_weight(self) -> None:
        async def query(*_args) -> SrvAnswer:
            return SrvAnswer(
                (
                    SrvRecord(10, 100, 3, "third.example.com"),
                    SrvRecord(0, 1, 2, "second.example.com"),
                    SrvRecord(0, 20, 1, "first.example.com"),
                ),
                ttl=120,
            )

        result = await MinecraftSrvResolver(query=query).resolve("example.com")

        self.assertEqual(
            [endpoint.host for endpoint in result.endpoints],
            ["first.example.com", "second.example.com", "third.example.com"],
        )

    async def test_empty_answer_continues_with_next_dns_server(self) -> None:
        calls: list[str] = []

        async def query(nameserver: str, *_args) -> SrvAnswer:
            calls.append(nameserver)
            if nameserver == DNS_SERVERS[0]:
                return SrvAnswer((), ttl=60)
            return SrvAnswer(
                (SrvRecord(0, 0, 25565, "target.example.com"),),
                ttl=60,
            )

        result = await MinecraftSrvResolver(query=query).resolve("example.com")

        self.assertEqual(calls, list(DNS_SERVERS[:2]))
        self.assertEqual(result.endpoints[0].host, "target.example.com")

    async def test_positive_and_negative_results_are_cached(self) -> None:
        clock = MutableClock()
        calls = 0

        async def query(*_args) -> SrvAnswer:
            nonlocal calls
            calls += 1
            return SrvAnswer(
                (SrvRecord(0, 0, 25565, "target.example.com"),),
                ttl=5,
            )

        resolver = MinecraftSrvResolver(query=query, clock=clock)
        await resolver.resolve("example.com")
        await resolver.resolve("example.com")
        clock.current += 29
        await resolver.resolve("example.com")
        clock.current += 2
        await resolver.resolve("example.com")

        self.assertEqual(calls, 2)

    async def test_root_target_marks_service_unavailable(self) -> None:
        async def query(*_args) -> SrvAnswer:
            return SrvAnswer((SrvRecord(0, 0, 0, "."),), ttl=60)

        result = await MinecraftSrvResolver(query=query).resolve("example.com")

        self.assertTrue(result.service_unavailable)
        self.assertEqual(result.endpoints, ())

    async def test_all_failures_produce_negative_fallback_result(self) -> None:
        calls: list[str] = []

        async def query(nameserver: str, *_args) -> SrvAnswer:
            calls.append(nameserver)
            raise OSError("dns unavailable")

        result = await MinecraftSrvResolver(query=query).resolve("example.com")

        self.assertEqual(calls, list(DNS_SERVERS))
        self.assertFalse(result.service_unavailable)
        self.assertEqual(result.endpoints, ())


if __name__ == "__main__":
    unittest.main()
