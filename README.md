已帮你整理为**工程级 README（结构清晰 + GitHub友好）**，同时修复层级、命令分区和说明一致性：

---

# kesepain-Agent

一个以本地 Python 脚本为主链的终端 Agent 框架。
当前架构为 **单进程入口 + 多脚本调度**，已具备完整的对话、任务、工具与技能执行能力。

---

## 一、核心架构

主执行链：

```text
start.py
→ core/date_analyze.py
→ core/chat.py / core/memory.py / core/agent.py
→ provider/provider.py
→ core/action.py
```

架构特点：

* 单入口调度（start.py）
* 核心逻辑分层（chat / memory / agent）
* 工具与技能模块化（plugins / skills）
* Provider 抽象统一接口

---

## 二、当前能力

### 1. 对话与记忆

* 终端多轮对话
* 用户级隔离（配置 + 历史）
* 历史摘要压缩（自动裁剪上下文）

### 2. 控制系统

* 控制命令拦截
* 指令目录查询机制
* 命令统一解析入口（action.py）

### 3. 工具系统（Plugins）

* 文件系统操作
* 任务链执行
* 时间查询

### 4. 技能系统（Skills）

* 天气查询
* 网络搜索

### 5. LLM 能力

* OpenAI 兼容接口
* 支持：

  * `deepseek`
  * `openai`

---

## 三、项目结构

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
```

---

## 四、命令体系

### 1. 控制命令

```text
/帮助
/清除
/退出
```

---

### 2. 插件命令

```text
/查询全部指令
/查看指令说明 <指令>

# 文件
/文件查找 <文件名>
/文件夹内部框架查看 <文件名>
/文件读取 <路径>

# 任务
/任务创建 <描述>|<步骤1>|<步骤2>|...
/任务进度查看
/任务标注 <序号>

# 工具
/查询时间
```

---

### 3. 技能命令

```text
/天气查询 <城市> <时间>
/网络搜索 <关键词>
```

---

### 4. 兼容旧指令

```text
/任务查询
/任务完成
/文件搜索
/框架查询
/查询天气
/网络查询
```

---

## 五、快速开始

### 1. 运行环境

```bash
python start.py
```

说明：

* 无第三方依赖（requirements.txt 为空）
* 推荐环境：Windows
* 部分能力依赖系统组件：

  * PowerShell（天气查询）
  * 网络 API（搜索能力）

---

### 2. 用户配置

路径：

```text
users/<user>/config.json
```

示例：

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

* `name` 会被用户目录名覆盖
* memory路径会映射到缓存系统
* tool_use_allow 控制工具调用权限

---

### 3. 核心配置

路径：

```text
core/config.json
```

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

---

### 4. 启动流程

```bash
python start.py
```

启动后：

1. 自动扫描 `users/`
2. 选择用户
3. 进入终端交互

---

## 六、运行时数据

```text
缓存：core/temp/cache.json
任务：core/temp/task.json
历史：users/<user>/chat_history/
人格：system/prompt/soul_prompt/
任务提示词：system/prompt/system_core/task.txt
历史压缩：system/prompt/system_core/zip_history.txt
```

---

## 七、Provider

已注册：

```text
deepseek
openai
```

支持模型：

```text
deepseek-chat
deepseek-reasoner
gpt-5.4-mini
```

实现方式：

* 统一通过：

```text
provider/LLM/openai_api.py
```

说明：

* 使用 OpenAI 兼容接口
* `google_api.py` 尚未接入主链
