import json
import locale
import subprocess
import sys
from pathlib import Path


payload = sys.argv[1]
root_dir = Path(__file__).resolve().parent.parent
cache_path = Path(__file__).resolve().parent / "temp" / "cache.json"
plugin_config_path = root_dir / "system" / "plugins" / "core_control" / "core_chat.json"

def _safe_reconfigure_output(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


def _safe_reconfigure_input(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    encoding = "utf-8"
    try:
        if stream.isatty():
            encoding = locale.getpreferredencoding(False) or "utf-8"
    except Exception:
        pass
    reconfigure(encoding=encoding)


_safe_reconfigure_output(sys.stdout)
_safe_reconfigure_output(sys.stderr)
_safe_reconfigure_input(sys.stdin)


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def tool_log_keys(tool_log):
    keys = [key for key in tool_log if key.startswith("num_")]
    keys.sort(key=lambda item: int(item.split("_")[1]))
    return keys


def build_next_turn_tool_log(tool_log):
    next_tool_log = {
        "tool_use": tool_log["tool_use"],
        "single_chat_tools_use_num": tool_log["single_chat_tools_use_num"],
        "tool_call_count": 0,
        "current_turn_log_offset": len(tool_log_keys(tool_log)),
    }
    for index, key in enumerate(tool_log_keys(tool_log), start=1):
        next_tool_log[f"num_{index}"] = tool_log[key]
    return next_tool_log


def prompt_input():
    if payload == "type:start":
        print("请输入文本：", end="", file=sys.stderr)
    if payload == "type:continue":
        print("请继续输入文本：", end="", file=sys.stderr)
    return input().strip()


def run_core_command(command):
    result = subprocess.run(
        [sys.executable, str(root_dir / "system" / "plugins" / "core_control" / "core_chat.py"), command],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def handle_core_command(command_output):
    lines = command_output.splitlines()
    command_type = lines[0]
    output = ""
    if len(lines) > 1:
        output = "\n".join(lines[1:])[len("output:") :]
    if output != "":
        print(output, file=sys.stderr)
    return command_type


commands = load_json(plugin_config_path)["exit_commands"]
user_input = prompt_input()

while user_input in commands:
    command_type = handle_core_command(run_core_command(user_input))
    if command_type == "type:exit":
        print("type:exit")
        sys.exit(0)
    user_input = prompt_input()

cache_data = load_json(cache_path)
cache_data["user_input"] = user_input
cache_data["tool_log"] = build_next_turn_tool_log(cache_data["tool_log"])
save_json(cache_path, cache_data)

print("type:runed")
