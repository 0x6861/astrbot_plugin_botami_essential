from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_ASTRBOT_ROOT = tempfile.TemporaryDirectory()
_PREVIOUS_ASTRBOT_ROOT = os.environ.get("ASTRBOT_ROOT")
os.environ["ASTRBOT_ROOT"] = _ASTRBOT_ROOT.name

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY_ROOT.parent))
plugin_module = importlib.import_module(
    "astrbot_plugin_botami_essential.main"
)


def tearDownModule() -> None:
    if _PREVIOUS_ASTRBOT_ROOT is None:
        os.environ.pop("ASTRBOT_ROOT", None)
    else:
        os.environ["ASTRBOT_ROOT"] = _PREVIOUS_ASTRBOT_ROOT
    try:
        sys.path.remove(str(_REPOSITORY_ROOT.parent))
    except ValueError:
        pass
    _ASTRBOT_ROOT.cleanup()


class FakeEvent:
    def __init__(
        self,
        message: str,
        *,
        sender_id: str = "user",
        self_id: str = "bot",
    ):
        self.message_str = message
        self._sender_id = sender_id
        self._self_id = self_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_self_id(self) -> str:
        return self._self_id

    def plain_result(self, text: str) -> str:
        return text


async def collect_results(generator) -> list[str]:
    return [result async for result in generator]


class PluginAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.plugin_data_dir = Path(_ASTRBOT_ROOT.name) / self.id().split(".")[-1]
        self.plugin_data_dir.mkdir(parents=True)
        self.plugin = plugin_module.BotamiEssential(context=object())
        with patch.object(
            plugin_module.StarTools,
            "get_data_dir",
            return_value=self.plugin_data_dir,
        ):
            await self.plugin.initialize()

    async def asyncTearDown(self) -> None:
        await self.plugin.terminate()

    async def test_command_and_message_handlers_work_together(self) -> None:
        added = await collect_results(self.plugin.cnt(FakeEvent("/cnt add Python py")))
        incremented = await collect_results(
            self.plugin.on_any_message(FakeEvent("I use PY every day"))
        )
        listed = await collect_results(self.plugin.cnt(FakeEvent("/cnt list")))

        self.assertIn("已添加计数器", added[0])
        self.assertEqual(incremented, ["累计 Python 1/114514"])
        self.assertIn("Python：1 次", listed[0])

    async def test_own_messages_and_counter_commands_are_ignored(self) -> None:
        await collect_results(self.plugin.cnt(FakeEvent("/cnt add cnt")))

        own_results = await collect_results(
            self.plugin.on_any_message(
                FakeEvent("cnt", sender_id="bot", self_id="bot")
            )
        )
        command_results = await collect_results(
            self.plugin.on_any_message(FakeEvent("/cnt list"))
        )
        listed = await collect_results(self.plugin.cnt(FakeEvent("/cnt list")))

        self.assertEqual(own_results, [])
        self.assertEqual(command_results, [])
        self.assertIn("cnt：0 次", listed[0])


if __name__ == "__main__":
    unittest.main()
