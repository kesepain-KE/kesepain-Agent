# kesepain-Agent

一个基于本地 Python 脚本主链的轻量 Agent 框架。

当前仓库已经具备可运行的终端对话主链、历史读写、历史摘要压缩、任务型工具调用、工具结果回流，以及内置控制命令拦截。项目以文件和脚本为中心，结构直接，适合继续做个人 Agent、Prompt 实验、技能系统和工具编排。

## Current Features

- 主链清晰：`start.py -> core/date_analyze.py -> core/agent.py -> provider/provider.py`
- 运行时共享状态统一落在 `core/temp/cache.json`
- 支持三类模型调用：普通聊天、工具续推、历史压缩
- 支持 `tool_search` / `tool_use` 工具闭环
- 已接入插件命令：`/文件读取`、`/文件搜索`、`/框架查询`、`/查询时间`
- 已接入技能命令：`/创建技能`、`/查询天气`、`/网络查询`
- 支持控制命令：`/帮助`、`/清除`、`/退出`
- 主链当前只依赖 Python 标准库

## Repository Layout

```text
kesepain-Agent/
├─ start.py
├─ core/
│  ├─ action.py
│  ├─ agent.py
│  ├─ chat.py
│  ├─ config.json
│  ├─ date_analyze.py
│  ├─ memory.py
│  └─ temp/cache.json
├─ provider/
│  ├─ api.json
│  ├─ provider.py
│  └─ LLM/
│     ├─ openai_api.py
│     └─ google_api.py
├─ system/
│  ├─ start/
│  │  ├─ cache.json
│  │  └─ history.json
│  ├─ prompt/
│  │  └─ system_core/
│  │     ├─ task_create.txt
│  │     └─ zip_history.txt
│  ├─ plugins/
│  │  ├─ core_control/
│  │  ├─ file_read/
│  │  ├─ file_search/
│  │  └─ time/
│  └─ skills/
│     ├─ skill_create/
│     ├─ weather/
│     └─ web_search/
├─ users/
│  └─ <user>/
│     ├─ config.json
│     └─ chat_history/
└─ 开发文档/
```

## Main Flow

1. `start.py` 复制 `system/start/cache.json` 到 `core/temp/cache.json`，加载用户配置，并确保历史文件存在。
2. `core/date_analyze.py` 串起输入、历史读取、模型调用和下一轮继续。
3. `core/chat.py` 只负责终端读取用户输入并写入 `cache.json.user_input`。
4. `core/agent.py` 写入主链配置，并优先拦截 `/帮助`、`/清除`、`/退出` 这类控制命令。
5. `core/memory.py` 负责历史读取、历史写回和超长历史摘要压缩。
6. `provider/provider.py` 组装 LLM payload，处理 `type:message` 和 `type:task`。
7. `core/action.py` 执行 `tool_search` / `tool_use`，把结果写回 `tool_log` 后再回到 `provider type:tool`。

## Runtime Cache

主链运行状态集中保存在 `core/temp/cache.json`，当前稳定会读写这些核心字段：

- `name`
- `prompt`
- `API`
- `history`
- `memory`
- `user_input`
- `LLM_output`
- `history_date`
- `tool_log`
- `token_use`

`tool_log` 当前主链实际依赖的字段是：

- `tool_use`
- `single_chat_tools_use_num`
- `num_*`

说明：

- `single_chat_tools_use_num` 当前代码里实际被当作“保留最近多少条工具日志”的上限。
- 现在的 `tool_log` 是最近 N 条滑动窗口，不是按“当前轮”切分。
- `tool_call_count`、`current_turn_log_offset`、`tool_log_max` 目前属于兼容残留字段，不是当前主链核心逻辑。

## Built-in Commands

### Plugins

- `/文件读取 <工作区相对文件地址>`
- `/文件搜索 <关键词>`
- `/框架查询 <工作区相对文件地址>`
- `/查询时间`

### Skills

- `/创建技能 <skill目录名> | <指令名称> | <指令说明>`
- `/查询天气 <城市> <未来天数>`
- `/网络查询 <查询内容>`

### Control Commands

- `/帮助`
- `/清除`
- `/退出`

## Quick Start

### 1. Python

当前主链只使用 Python 标准库，直接运行即可：

```bash
python start.py
```

根目录 `requirements.txt` 当前只是说明文件，不包含主链必需的第三方依赖。

### 2. User Config

编辑 `users/<user>/config.json`：

```json
{
    "name": "kesepain",
    "API": {
        "provider": "deepseek",
        "key": "YOUR_API_KEY",
        "model": "deepseek-chat"
    },
    "history": {
        "memory_chat_num": 10
    },
    "memory": {
        "memory_path": "kesepain_1.json",
        "memory_use": true,
        "memory_save": true
    },
    "tool_use": true,
    "prompt": "猫猫.txt"
}
```

### 3. Core Config

编辑 `core/config.json`：

```json
{
    "history_max": 100,
    "history_zip_to_num": 50,
    "single_chat_tools_use_num": 20,
    "tool_log_max": 30,
    "zip_history": {
        "API": "deepseek",
        "API_KEY": "YOUR_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "prompt": "zip_history.txt"
    },
    "task_prompt": "task_create.txt"
}
```

### 4. Run

```bash
python start.py
```

启动后会列出 `users/` 目录里的可选用户，然后进入终端交互。

## Providers

当前 `provider/api.json` 已注册：

- `deepseek`
- `openai`

当前允许模型：

- `deepseek-chat`
- `deepseek-reasoner`
- `gpt-5.4-nano`

这两个 provider 当前都通过 `provider/LLM/openai_api.py` 以 OpenAI 兼容接口方式调用。

`provider/LLM/google_api.py` 目前仍未接入主链。

## Tool Loop

```text
provider type:start
-> LLM 返回 type:task
-> core/action.py 执行工具
-> tool_log 写回结果
-> provider type:tool
-> LLM 基于工具结果继续决策
-> 最终返回 type:message
```

当前实现细节：

- `tool_search` 会扫描 `system/plugins/*/plugin.json`、`system/skills/*/skill.json`、`system/mcp/*/mcp.json`
- `tool_search <具体指令>` 目前只支持精确匹配
- `tool_use` 也只按 command 精确匹配
- plugin 运行目录是 `plugin.run`
- skill 运行目录是 `skill_run`
- mcp 运行目录当前只认 `mcp_run`

## Prompt Structure

当前聊天时会向模型发送三部分信息：

- 主人格 prompt：来自 `users/<user>/config.json`
- 任务 prompt：来自 `system/prompt/system_core/task_create.txt`
- 用户上下文：由 `user_input`、`history_date`、`tool_log` 拼装

`task_create.txt` 当前是比较轻量的任务提示词，只规定了：

- 输出格式是 `type:task` 或 `type:message`
- 工具头只有 `tool_search` 和 `tool_use`
- 倾向少调用工具

它当前没有实现“首个动作必须无参 `tool_search`”这类更强的硬约束。

## Notes

- 控制命令的实际拦截位置在 `core/agent.py`，不是 `core/chat.py`。
- `core_control` 是内置控制目录，不带 `plugin.json`，不参与普通 `tool_search` 发现。
- 历史压缩当前只会生成 `zip_chat` 摘要，不会删除原始 `standard_chat.messages`。
- 如果工具未命中，`tool_use` 当前会返回空字符串，没有结构化错误包装。

## Limitations

- `provider/LLM/google_api.py` 仍不是可用主链实现。
- `system/mcp/` 当前没有实际接入可执行 MCP 工具。
- 工具发现和执行目前以精确匹配为主，能力较窄。
- `tool_log` 目前是最近 N 条滑动窗口，不是严格的按轮次上下文。
- 当前项目仍以单用户、本地脚本驱动为主，没有 Web UI、服务化部署或测试套件。

## Development Docs

仓库内还有一组中文开发文档，扩展功能时建议一起看：

- `开发文档/个人开发框架.txt`
- `开发文档/传参参考.txt`
- `开发文档/action开发文档.txt`
- `开发文档/provider开发文档.txt`
- `开发文档/LLM开发文档.txt`

## License

当前仓库未声明独立 `LICENSE` 文件。
