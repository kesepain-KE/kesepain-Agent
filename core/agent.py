import json
import subprocess
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parent.parent
config_path = Path(__file__).resolve().parent / "config.json"
cache_path = Path(__file__).resolve().parent / "temp" / "cache.json"
core_control_json_path = root_dir / "system" / "plugins" / "core_control" / "core_chat.json"
core_control_run_path = root_dir / "system" / "plugins" / "core_control" / "core_chat.py"
payload = sys.argv[1]


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def get_core_control_commands():
    core_control_data = load_json(core_control_json_path)
    return core_control_data["exit_commands"]


def parse_core_control_result(text):
    lines = text.splitlines()
    result_type = lines[0]
    output = "\n".join(lines[1:])[len("output:") :]
    return result_type, output


def run_core_control():
    cache_data = load_json(cache_path)
    user_input = cache_data["user_input"]
    if user_input not in get_core_control_commands():
        return False

    core_control_output = subprocess.run(
        [sys.executable, str(core_control_run_path), user_input],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    result_type, output = parse_core_control_result(core_control_output)
    print(output)

    if result_type == "type:continue":
        chat_output = subprocess.run(
            [sys.executable, str(root_dir / "core" / "chat.py"), "type:continue"],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        if chat_output == "type:runed":
            memory_output = subprocess.run(
                [sys.executable, str(root_dir / "core" / "memory.py"), "type:read"],
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
            if memory_output == "type:runed":
                subprocess.run([sys.executable, str(root_dir / "core" / "agent.py"), "type:continue"])
    return True


if payload == "type:start":
    config_data = load_json(config_path)
    cache_data = load_json(cache_path)
    cache_data["history"]["history_max"] = config_data["history_max"]
    cache_data["history"]["history_zip_to_num"] = config_data["history_zip_to_num"]
    cache_data["tool_log"]["single_chat_tools_use_num"] = config_data["single_chat_tools_use_num"]
    save_json(cache_path, cache_data)
    if run_core_control() is False:
        subprocess.run([sys.executable, str(root_dir / "provider" / "provider.py"), "type:start"])


if payload == "type:continue":
    if run_core_control() is False:
        subprocess.run([sys.executable, str(root_dir / "provider" / "provider.py"), "type:start"])
