import json
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parents[3]
plugin_path = Path(__file__).resolve().parent / "core_chat.json"
cache_path = root_dir / "core" / "temp" / "cache.json"
payload = sys.argv[1]

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


def build_empty_history():
    return {
        "zip_chat": "",
        "standard_chat": {
            "messages": {}
        }
    }


def build_empty_tool_log(tool_log):
    return {
        "tool_use": tool_log["tool_use"],
        "single_chat_tools_use_num": tool_log["single_chat_tools_use_num"],
        "tool_call_count": 0,
        "current_turn_log_offset": 0,
    }


plugin_data = load_json(plugin_path)

if payload == "/帮助":
    help_lines = []
    for command, description in plugin_data["exit_commands"].items():
        help_lines.append(f"{command} {description}")
    print("type:continue")
    print("output:" + "\n".join(help_lines))

if payload == "/清除":
    cache_data = load_json(cache_path)
    history_path = root_dir / "users" / cache_data["name"] / "chat_history" / cache_data["memory"]["memory_path"]
    save_json(history_path, build_empty_history())
    cache_data["history_date"] = {}
    cache_data["tool_log"] = build_empty_tool_log(cache_data["tool_log"])
    cache_data["token_use"] = 0
    save_json(cache_path, cache_data)
    print("type:continue")
    print("output:已清除当前历史对话文件内容和工具调用日志")

if payload == "/退出":
    print("type:exit")
    print("output:已退出当前历史对话")
