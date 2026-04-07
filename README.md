# kesepain-Agent

一个以本地 Python 脚本为主链的终端 Agent 框架。当前仓库已经具备用户选择、历史读写、历史摘要压缩、控制命令拦截、指令目录、任务链、文件工具、时间查询、天气查询和网络搜索能力。

项目现在是“单进程入口 + 多脚本调度”的形态，核心路径是：

```text
start.py
-> core/date_analyze.py
-> core/chat.py / core/memory.py / core/agent.py
-> provider/provider.py
-> core/action.py
```

## 当前能力

- 终端多轮对话
- 用户级配置与历史文件隔离
- 历史摘要压缩
- 本地控制命令：`/帮助`、`/清除`、`/退出`
- 指令目录：`/查询全部指令`、`/查看指令说明 <指令>`
- 任务链：`/任务创建`、`/任务进度查看`、`/任务标注`
- 文件工具：`/文件查找`、`/文件夹内部框架查看`、`/文件读取`
- 实用技能：`/查询时间`、`/天气查询`、`/网络搜索`
- OpenAI 兼容接口调用，当前可走 `deepseek` 和 `openai`

## 当前目录

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
│  └─ temp/
├─ provider/
│  ├─ api.json
│  ├─ provider.py
│  └─ LLM/
├─ system/
│  ├─ mcp/
│  ├─ plugins/
│  │  ├─ chat_control/
│  │  ├─ command_control/
│  │  ├─ file/
│  │  ├─ task/
│  │  └─ time/
│  ├─ prompt/
│  │  ├─ soul_prompt/
│  │  └─ system_core/
│  ├─ skills/
│  │  ├─ weather/
│  │  └─ web_search/
│  └─ start/
└─ users/

## 当前命令

### 控制命令

- `/帮助`
- `/清除`
- `/退出`

### 插件命令

- `/查询全部指令`
- `/查看指令说明 <特定指令>`
- `/文件查找 <具体的文件名，支持文件夹>`
- `/文件夹内部框架查看 <具体的文件名>`
- `/文件读取 <相对路径>`
- `/任务创建 <任务描述>|<任务步骤1>|<任务步骤2>|...`
- `/任务进度查看`
- `/任务标注 <任务序号>`
- `/查询时间`

### 技能命令

- `/天气查询 <城市> <具体时间，一般是前后3天>`
- `/网络搜索 <多个关键词>`

### 当前兼容的旧指令

- `/任务查询`
- `/任务完成`
- `/文件搜索`
- `/框架查询`
- `/查询天气`
- `/网络查询`

## 快速开始

### 1. 依赖

当前根主链没有 Python 第三方依赖，`requirements.txt` 为空说明文件。直接使用本机 Python 即可运行。

```bash
python start.py
```

说明：

- 当前项目更偏向 Windows 终端环境
- `weather` 技能依赖 PowerShell 的 `Invoke-WebRequest`
- 网络功能依赖外部 API 和网络连接，不依赖 Python 第三方包

### 2. 用户配置

编辑 `users/<user>/config.json`：

```json
{
    "name": "user",
    "API": {
        "provider": "deepseek",
        "key": "YOUR_API_KEY",
        "model": "deepseek-chat"
    },
    "history": {
        "memory_chat_num": 25
    },
    "memory": {
        "user_memory_path": "user_1.json"
    },
    "tool_use_allow": true,
    "soul_prompt": "猫猫.txt"
}
```

说明：

- 实际运行时会以用户目录名覆盖 `name`
- `memory.user_memory_path` 会桥接到缓存里的 `memory.memory_path`
- `tool_use_allow` 会桥接到缓存里的 `tool_log.tool_use`

### 3. 核心配置

编辑 `core/config.json`：

```json
{
    "history_max": 100,
    "history_zip_to_num": 50,
    "single_chat_tools_use_num": 20,
    "tool_log_max": 30,
    "history_zip": {
        "API": "deepseek",
        "API_KEY": "YOUR_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "prompt": "zip_history.txt"
    },
    "task_prompt": "task.txt"
}
```

### 4. 启动

```bash
python start.py
```

启动后会列出 `users/` 目录下的用户，选择后进入终端交互。

## 运行时事实

- 运行共享缓存是 `core/temp/cache.json`
- 当前任务状态文件是 `core/temp/task.json`
- 用户历史文件位于 `users/<user>/chat_history/<memory_path>`
- 主人格 prompt 位于 `system/prompt/soul_prompt/`
- 任务 prompt 位于 `system/prompt/system_core/task.txt`
- 历史压缩 prompt 位于 `system/prompt/system_core/zip_history.txt`

## Provider

当前 `provider/api.json` 已注册：

- `deepseek`
- `openai`

当前允许模型：

- `deepseek-chat`
- `deepseek-reasoner`
- `gpt-5.4-mini`

当前 `deepseek` 和 `openai` 都通过 `provider/LLM/openai_api.py` 以 OpenAI 兼容接口方式调用。`provider/LLM/google_api.py` 目前还没有接入主链。

## 已知限制

- `system/mcp/` 目录存在，但当前没有实际可执行的 MCP 工具
- `tool_log` 当前是最近 N 条滑动窗口，不是严格按轮次切分
- `provider.py` 和 `action.py` 使用的日志裁剪字段不完全一致
- `system/prompt/system_core/task.txt` 里仍残留 `/任务进度查询` 的旧文案，真实命令是 `/任务进度查看`
- 当前没有自动化测试套件
