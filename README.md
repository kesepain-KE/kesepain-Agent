# kesepain-Agent

一个基于 Python 的本地 Agent 项目，支持：

- 多用户配置加载
- 历史对话压缩与记忆管理
- 技能调用（天气、网络检索等）
- MCP/插件式扩展

## 1. 环境要求

- Python 3.10 及以上（推荐 3.11）
- Windows / Linux / macOS

说明：当前主链路仅使用标准库运行，根目录 [requirements.txt](requirements.txt) 暂无第三方依赖强制要求。

## 2. 快速启动

在项目根目录执行：

```bash
python start.py
```

启动后会：

1. 读取用户列表并要求选择用户
2. 将用户配置合并到运行缓存
3. 进入主流程

主入口文件：

- [start.py](start.py)

## 3. 目录结构

核心目录：

- [core](core)：主流程、任务分发、记忆处理、运行缓存
- [provider](provider)：模型提供方路由与 LLM 适配
- [system](system)：提示词、技能、插件、系统缓存
- [users](users)：用户配置与历史记录
- [开发文档](开发文档)：项目内部开发与传参文档

## 4. 配置文件说明

全局配置：

- [core/config.json](core/config.json)
  - history_max: 最大历史条数
  - history_zip_to_num: 压缩后保留条数阈值
  - single_chat_tools_use_num: 单轮工具调用上限
  - zip_history: 历史压缩模型配置

运行缓存：

- [core/temp/cache.json](core/temp/cache.json)
  - 当前用户会话运行态（每次启动会重建）

用户配置：

- [users/kesepain/config.json](users/kesepain/config.json)
  - 用户级 API、记忆策略、提示词、工具开关

技能配置：

- [system/skills/weather/skill_run/config.json](system/skills/weather/skill_run/config.json)
- [system/skills/web_search/skill_run/config.json](system/skills/web_search/skill_run/config.json)

## 5. 密钥配置（已标准化清空）

仓库中的真实密钥应保持为空，按需在本地填写：

1. [core/config.json](core/config.json)
   - zip_history.API_KEY
2. [core/temp/cache.json](core/temp/cache.json)
   - API.key
3. [users/kesepain/config.json](users/kesepain/config.json)
   - API.key
4. [system/skills/weather/skill_run/config.json](system/skills/weather/skill_run/config.json)
   - public_key
   - private_key
5. [system/skills/web_search/skill_run/config.json](system/skills/web_search/skill_run/config.json)
   - key

详细说明见：

- [开发文档/密钥配置说明.txt](开发文档/密钥配置说明.txt)

## 6. 安全建议

- 不要将真实密钥提交到仓库。
- 建议通过环境变量或本地未跟踪配置注入密钥。
- 提交前检查上述配置文件是否含敏感值。

## 7. 开发文档索引

常用文档：

- [开发文档/传参参考.txt](开发文档/传参参考.txt)
- [开发文档/provider开发文档.txt](开发文档/provider开发文档.txt)
- [开发文档/LLM开发文档.txt](开发文档/LLM开发文档.txt)
- [开发文档/agent开发文档.txt](开发文档/agent开发文档.txt)
- [开发文档/action开发文档.txt](开发文档/action开发文档.txt)

## 8. 维护约定

- 新增技能时，将技能密钥仅保留占位，不写真实值。
- 新增运行主链依赖时，再更新 [requirements.txt](requirements.txt)。
- 修改配置字段时，需同步更新对应开发文档与本 README。
