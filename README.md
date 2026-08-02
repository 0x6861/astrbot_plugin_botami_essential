# BotamiDragen AstrBot 扩展插件

一个面向长期扩展的 AstrBot 多功能插件。当前提供群聊睡眠记录，并已整合
[`astrbot_plugin_counter`](https://github.com/0x6861/astrbot_plugin_counter)
的计数器功能。

## 环境要求

- Python 3.13 或更高版本
- AstrBot 4.26.8 或更高版本

## 计数器

- `/cnt add <名称> [别名1 别名2 ...]`：新增计数器并设置可选别名。
- `/cnt del <名称或别名>`：删除计数器。
- `/cnt list`：按计数降序查看所有计数器。
- `/cnt addname <主名称> <别名1> [别名2 ...]`：增加别名。
- `/cnt delname <别名>`：删除别名，不能用于删除主名称。

任意非 `/cnt` 消息只要包含主名称或别名，对应计数器就会自动加一并回复。
匹配不区分大小写；一条消息可以命中多个计数器，但同一计数器每条消息最多增加一次。
计数器是插件实例内的全局数据，不按群聊或私聊隔离。

统一消息监听只处理群聊消息，因此私聊中的普通文本不会触发自动计数或睡眠回复；
`/cnt` 命令仍由独立命令处理器负责。

## 群聊睡眠记录

- 去除消息首尾空白后，以“晚安”开头即登记睡眠，例如“晚安”“晚安啦”。
- 每个群按服务器本地公历日期独立排名，同一用户当天首次登记时取得唯一名次。
- 同一用户当天重复发送“晚安”会保留首次名次，但睡眠起点更新为最后一次登记时间。
- 去除首尾空白后精确等于“早安”才会读取睡眠记录；“早安呀”等文本不会触发。
- 有效记录的时长范围为 0 至 24 小时，显示时按整分钟向下取整；回复成功后记录即被消费。
- 超过 24 小时或起点晚于当前时间的记录会被清理，此时只回复问候与当前时间。
- 睡眠排名和活动记录均按群隔离，私聊不会登记或查询睡眠。

睡眠数据使用版本化 JSON 保存到插件数据目录的
`sleep/sleep_records.json`。每天首次处理睡眠消息时会清理旧排名，但未超过
24 小时的活动睡眠记录会继续保留，因此跨午夜后仍可正常发送“早安”。

### 根号历

睡眠回复中的日期使用独立根号历：`2022-03-26` 定义为根号 1 年 1 月 1 日，
之后按日期序数连续推进。根号年采用与公历相同的大小月和闰年规则，即四年一闰、
百年不闰、四百年再闰。时间取服务器本地时区并显示为 `HH:mm:ss`；插件不做跨时区合并。

## 从独立 counter 插件升级

1. 安装并启用本插件。
2. 停用或卸载 `astrbot_plugin_counter`，避免 `/cnt` 命令和消息监听重复执行。
3. 当本插件尚无计数器数据时，会自动读取：
   `data/plugin_data/astrbot_plugin_counter/counters.json`。
4. 校验成功后，数据会复制到：
   `data/plugin_data/astrbot_plugin_botami_essential/counter/counters.json`。

迁移不会覆盖本插件已经存在的数据，也不会修改或删除旧文件，可以安全地重复启动。
若旧文件损坏或结构不合法，插件会拒绝初始化并记录具体错误，避免用空数据覆盖原文件。

## 开发与验证

计数器领域逻辑位于 `src/counter`，睡眠领域逻辑位于 `src/sleep_tracker`，共享的
原子 JSON 写入工具位于 `src/atomic_json.py`。`main.py` 只负责 AstrBot 生命周期、
命令和消息事件协调。
后续功能应放在独立的 `src/<feature>` 目录中，避免功能之间直接共享可变状态。

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q main.py src tests
```

## 许可证与来源

本项目采用 GNU Affero General Public License v3.0。
