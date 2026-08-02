from __future__ import annotations

from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from .src.counter.commands import CounterCommandProcessor
from .src.counter.presenter import format_increment_result
from .src.counter.repository import CounterRepository
from .src.counter.service import CounterService
from .src.sleep_tracker.presenter import format_good_morning, format_good_night
from .src.sleep_tracker.repository import SleepRepository
from .src.sleep_tracker.service import SleepTrackerService


PLUGIN_NAME = "astrbot_plugin_botami_essential"
LEGACY_COUNTER_PLUGIN_NAME = "astrbot_plugin_counter"
COUNTER_DATA_FILE_NAME = "counters.json"
SLEEP_DATA_FILE_NAME = "sleep_records.json"


class BotamiEssential(Star):
    """BotamiDragen 多功能插件。"""

    def __init__(self, context: Context):
        super().__init__(context)
        self._counter_service: CounterService | None = None
        self._counter_commands: CounterCommandProcessor | None = None
        self._sleep_service: SleepTrackerService | None = None

    async def initialize(self) -> None:
        """初始化各功能模块。"""
        plugin_data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        counter_data_file = plugin_data_dir / "counter" / COUNTER_DATA_FILE_NAME
        legacy_data_file = (
            plugin_data_dir.parent
            / LEGACY_COUNTER_PLUGIN_NAME
            / COUNTER_DATA_FILE_NAME
        )

        try:
            repository = CounterRepository(counter_data_file, legacy_data_file)
            load_result = await repository.load()
            self._counter_service = CounterService(repository, load_result.counters)
            self._counter_commands = CounterCommandProcessor(self._counter_service)

            if load_result.migrated_from is not None:
                self.logger.info(
                    "已从旧 counter 插件迁移数据：%s -> %s",
                    load_result.migrated_from,
                    counter_data_file,
                )
            self.logger.info(
                "计数器模块已加载，共 %d 个计数器。", len(load_result.counters)
            )
        except Exception as e:
            self.logger.exception("计数器模块加载失败，原因：%s", e)

        sleep_data_file = plugin_data_dir / "sleep" / SLEEP_DATA_FILE_NAME
        try:
            sleep_repository = SleepRepository(sleep_data_file)
            sleep_groups = await sleep_repository.load()
            self._sleep_service = SleepTrackerService(
                sleep_repository, sleep_groups
            )
            await self._sleep_service.cleanup()
            self.logger.info("睡眠记录模块已加载，共 %d 个群。", len(sleep_groups))
        except Exception as e:
            self.logger.exception("睡眠记录模块加载失败，原因：%s", e)

    @filter.command("cnt")
    async def cnt(self, event: AstrMessageEvent):
        """计数器命令：/cnt add|del|list|addname|delname。"""
        if self._counter_commands is None:
            yield event.plain_result("计数器模块尚未完成初始化，请稍后重试。")
            return

        response = await self._counter_commands.handle(event.message_str)
        yield event.plain_result(response)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_any_message(self, event: AstrMessageEvent):
        """协调群聊睡眠回复与计数器自增。"""
        if self._counter_service is None and self._sleep_service is None:
            return

        try:
            if event.get_sender_id() == event.get_self_id():
                return
        except AttributeError:
            # 部分平台适配器未提供机器人自身 ID。
            pass

        try:
            group_id = event.get_group_id()
        except AttributeError:
            group_id = ""
        if not group_id:
            return

        text = (event.message_str or "").strip()
        if not text or self._is_counter_command(text):
            return

        if self._sleep_service is not None:
            try:
                sender_id = event.get_sender_id()
                if sender_id:
                    display_name = self._sender_display_name(event, sender_id)
                    if text.startswith("晚安"):
                        result = await self._sleep_service.good_night(
                            str(group_id), sender_id
                        )
                        yield event.plain_result(
                            format_good_night(display_name, result)
                        )
                    elif text == "早安":
                        result = await self._sleep_service.good_morning(
                            str(group_id), sender_id
                        )
                        yield event.plain_result(
                            format_good_morning(display_name, result)
                        )
            except Exception as e:
                self.logger.exception("处理睡眠消息失败，原因：%s", e)

        if self._counter_service is not None:
            try:
                hits = await self._counter_service.increment_matching(text)
                response = format_increment_result(hits)
                if response is not None:
                    yield event.plain_result(response)
            except Exception as e:
                self.logger.exception("处理计数器消息失败，原因：%s", e)

    async def terminate(self) -> None:
        """插件停用时再次落盘，确保内存状态已持久化。"""
        if self._counter_service is not None:
            try:
                await self._counter_service.flush()
            except Exception as e:
                self.logger.exception("计数器模块在插件停用时保存失败，原因：%s", e)
        if self._sleep_service is not None:
            try:
                await self._sleep_service.flush()
            except Exception as e:
                self.logger.exception("睡眠模块在插件停用时保存失败，原因：%s", e)

    @staticmethod
    def _is_counter_command(text: str) -> bool:
        first_part = text.split(maxsplit=1)[0]
        return first_part.removeprefix("/").casefold() == "cnt"

    @staticmethod
    def _sender_display_name(event: AstrMessageEvent, sender_id: str) -> str:
        try:
            sender_name = event.get_sender_name()
        except AttributeError:
            sender_name = ""
        if sender_name is None:
            return sender_id
        return str(sender_name).strip() or sender_id
