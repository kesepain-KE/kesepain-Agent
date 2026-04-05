import json
import subprocess
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parent.parent
cache_path = root_dir / "core" / "temp" / "cache.json"
provider_path = root_dir / "provider" / "provider.py"
payload = sys.argv[1]


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def read_text(path):
    with path.open("r", encoding="utf-8") as file:
        return file.read()


def get_command(text):
    lines = text.splitlines()
    return lines[1][len("command:") :]


def get_num_keys(tool_log):
    keys = [key for key in tool_log if key.startswith("num_")]
    keys.sort(key=lambda item: int(item.split("_")[1]))
    return keys


def get_tool_log_item_key(tool_log):
    keys = get_num_keys(tool_log)
    if len(keys) != 0 and tool_log[keys[-1]].get("result", "") == "":
        return keys[-1]
    return f"num_{len(keys) + 1}"


def trim_tool_log(tool_log):
    keys = get_num_keys(tool_log)
    limit = int(tool_log["single_chat_tools_use_num"])
    kept_keys = keys[-limit:]
    kept_items = [tool_log[key] for key in kept_keys]
    trimmed_tool_log = {}
    for key, value in tool_log.items():
        if key.startswith("num_") is False:
            trimmed_tool_log[key] = value
    for index, item in enumerate(kept_items, start=1):
        trimmed_tool_log[f"num_{index}"] = item
    return trimmed_tool_log


def write_action(cache_data, command):
    tool_log = cache_data["tool_log"]
    item_key = get_tool_log_item_key(tool_log)
    if item_key not in tool_log:
        tool_log[item_key] = {}
    tool_log[item_key]["action"] = command
    cache_data["tool_log"] = trim_tool_log(tool_log)
    save_json(cache_path, cache_data)
    return item_key


def write_result(cache_data, item_key, result):
    cache_data["tool_log"][item_key]["result"] = result
    cache_data["tool_log"] = trim_tool_log(cache_data["tool_log"])
    save_json(cache_path, cache_data)


def get_tool_specs():
    tools = []
    for category, spec_name in (("skills", "skill.json"), ("mcp", "mcp.json"), ("plugins", "plugin.json")):
        category_dir = root_dir / "system" / category
        if category_dir.exists():
            for tool_dir in category_dir.iterdir():
                if tool_dir.is_dir():
                    spec_path = tool_dir / spec_name
                    if spec_path.exists():
                        spec_data = load_json(spec_path)
                        keys = [key for key in spec_data if key.startswith("num_")]
                        keys.sort(key=lambda item: int(item.split("_")[1]))
                        for key in keys:
                            tools.append(
                                {
                                    "category": category,
                                    "tool_dir": tool_dir,
                                    "command": spec_data[key]["command"],
                                    "explain": spec_data[key]["explain"],
                                    "run_file": spec_data[key]["run_file"],
                                }
                            )
    return tools


def get_tool_search_result(command):
    tools = get_tool_specs()
    if command == "tool_search":
        lines = []
        for tool in tools:
            lines.append(f"{tool['command']} {tool['explain']}")
        return "\n".join(lines)

    if command == "tool_search tools":
        lines = []
        for category in ("plugins", "skills", "mcp"):
            names = []
            for tool in tools:
                if tool["category"] == category and tool["tool_dir"].name not in names:
                    names.append(tool["tool_dir"].name)
            lines.append(f"{category}:{'|'.join(names)}")
        return "\n".join(lines)

    query = command[len("tool_search ") :]
    for tool in tools:
        if tool["command"] == query or tool["command"].lstrip("/") == query.lstrip("/"):
            if tool["category"] == "plugins":
                return read_text(tool["tool_dir"] / "plugin_use.txt")
            if tool["category"] == "skills":
                return read_text(tool["tool_dir"] / "skill_use.txt")
            if tool["category"] == "mcp":
                return read_text(tool["tool_dir"] / "mcp_use.txt")
    return ""


def get_tool_use_result(command):
    tool_command = command[len("tool_use ") :]
    tool_name = tool_command.split()[0]
    tools = get_tool_specs()
    for tool in tools:
        if tool["command"] == tool_name or tool["command"].lstrip("/") == tool_name.lstrip("/"):
            if tool["category"] == "plugins":
                run_path = tool["tool_dir"] / "plugin.run" / tool["run_file"]
            if tool["category"] == "skills":
                run_path = tool["tool_dir"] / "skill_run" / tool["run_file"]
            if tool["category"] == "mcp":
                run_path = tool["tool_dir"] / "mcp_run" / tool["run_file"]
            return subprocess.run(
                [sys.executable, str(run_path), tool_command],
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
    return ""


if payload.startswith("type:task"):
    command = get_command(payload)
    cache_data = load_json(cache_path)
    item_key = write_action(cache_data, command)
    print(f"执行:{command}")

    if cache_data["tool_log"]["tool_use"] is False:
        result = f"{command}无法执行，请检查用户文件配置"
        cache_data = load_json(cache_path)
        write_result(cache_data, item_key, result)
        subprocess.run([sys.executable, str(provider_path), "type:tool"])

    if cache_data["tool_log"]["tool_use"] is True:
        if command.startswith("tool_search"):
            result = get_tool_search_result(command)
            cache_data = load_json(cache_path)
            write_result(cache_data, item_key, result)
            subprocess.run([sys.executable, str(provider_path), "type:tool"])

        if command.startswith("tool_use"):
            result = get_tool_use_result(command)
            cache_data = load_json(cache_path)
            write_result(cache_data, item_key, result)
            subprocess.run([sys.executable, str(provider_path), "type:tool"])
