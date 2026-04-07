import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
COMMAND_PATH = PROJECT_ROOT / "system" / "plugins" / "chat_control" / "command.json"
CACHE_PATH = PROJECT_ROOT / "core" / "temp" / "cache.json"
payload = sys.argv[1].strip()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def get_command_order_key(key):
    if key.startswith("command_"):
        suffix = key[len("command_") :]
        if suffix.isdigit():
            return int(suffix)
    return 10**9


def get_commands(command_data):
    commands = []
    for key in sorted(command_data.keys(), key=get_command_order_key):
        item = command_data[key]
        commands.append({
            "command": item["command"],
            "explain": item["explain"],
        })
    return commands


def build_help_text(commands):
    lines = []
    for item in commands:
        lines.append(f"{item['command']} {item['explain']}")
    return "\n".join(lines)


def build_empty_history():
    return {
        "zip_chat": "",
        "standard_chat": {}
    }


def clear_tool_log(tool_log):
    cleaned = {}
    if "tool_use" in tool_log:
        cleaned["tool_use"] = tool_log["tool_use"]
    if "tool_use_allow" in tool_log:
        cleaned["tool_use_allow"] = tool_log["tool_use_allow"]
    if "single_chat_tools_use_num" in tool_log:
        cleaned["single_chat_tools_use_num"] = tool_log["single_chat_tools_use_num"]
    if "tool_log_max" in tool_log:
        cleaned["tool_log_max"] = tool_log["tool_log_max"]
    if "tool_single_count" in tool_log:
        cleaned["tool_single_count"] = 0
    return cleaned


def run_help(command_data):
    commands = get_commands(command_data)
    print("type:continue")
    print("output:" + build_help_text(commands))


def run_clear():
    cache_data = load_json(CACHE_PATH)
    history_path = (
        PROJECT_ROOT
        / "users"
        / cache_data["name"]
        / "chat_history"
        / cache_data["memory"]["memory_path"]
    )
    save_json(history_path, build_empty_history())

    cache_data["history_date"] = {}
    cache_data["tool_log"] = clear_tool_log(cache_data.get("tool_log", {}))
    if "token_use" in cache_data:
        cache_data["token_use"] = 0
    if "token_used" in cache_data:
        cache_data["token_used"] = 0
    save_json(CACHE_PATH, cache_data)

    print("type:continue")
    print("output:已清除当前历史对话文件内容和工具调用日志，同时清除指定用户历史对话数据")


def run_exit():
    print("type:exit")
    print("output:已退出当前历史对话")


command_data = load_json(COMMAND_PATH)
EXIT_COMMAND = command_data.get("command_1", {}).get("command", "/退出")
CLEAR_COMMAND = command_data.get("command_2", {}).get("command", "/清除")
HELP_COMMAND = command_data.get("command_3", {}).get("command", "/帮助")

if payload == HELP_COMMAND:
    run_help(command_data)

if payload == CLEAR_COMMAND:
    run_clear()

if payload == EXIT_COMMAND:
    run_exit()

if payload not in [HELP_COMMAND, CLEAR_COMMAND, EXIT_COMMAND]:
    print("type:continue")
    print("output:未识别的指令")
