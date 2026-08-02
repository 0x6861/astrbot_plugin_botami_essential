# BotamiDragen AstrBot 扩展插件

一个面向长期扩展的 AstrBot 多功能插件。当前已整合
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

计数器领域逻辑位于 `src/counter`，`main.py` 只负责 AstrBot 生命周期、命令和消息事件适配。
后续功能应放在独立的 `src/<feature>` 目录中，避免功能之间直接共享可变状态。

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q main.py src tests
```

## 许可证与来源

本项目采用 GNU Affero General Public License v3.0。
