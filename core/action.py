import json
import subprocess
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parent.parent
cache_path = root_dir / "core" / "temp" / "cache.json"
provider_path = root_dir / "provider" / "provider.py"
payload = sys.argv[1]

REUSED_TOOL_RESULT_PREFIX = "本轮已执行过该工具，请直接基于已有结果回复："

stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(stdout_reconfigure):
    stdout_reconfigure(encoding="utf-8")

stderr_reconfigure = getattr(sys.stderr, "reconfigure", None)
if callable(stderr_reconfigure):
    stderr_reconfigure(encoding="utf-8")


TOOL_CATEGORIES = {
    "plugins": {
        "spec_file": "plugin.json",
        "use_file": "plugin_use.txt",
        "run_dirs": ("plugin.run",),
    },
    "skills": {
        "spec_file": "skill.json",
        "use_file": "skill_use.txt",
        "run_dirs": ("skill_run",),
    },
    "mcp": {
        "spec_file": "mcp.json",
        "use_file": "mcp_use.txt",
        "run_dirs": ("mcp_run", "mcp.run"),
    },
}


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def read_text(path):
    with path.open("r", encoding="utf-8") as file:
        return file.read()


def parse_task_payload(text):
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return ""
    body_lines = lines[1:]
    if not body_lines[0].startswith("command:"):
        return ""
    body_lines[0] = body_lines[0][len("command:") :]
    return "\n".join(body_lines).strip()


def tool_log_keys(tool_log):
    keys = []
    for key in tool_log:
        if key.startswith("num_") and is_placeholder_tool_item(tool_log[key]) is False:
            keys.append(key)
    keys.sort(key=lambda item: int(item.split("_")[1]))
    return keys


def is_placeholder_tool_item(tool_item):
    return tool_item.get("action") == "input" and tool_item.get("result") == "output"


def get_pending_tool_key(tool_log):
    keys = tool_log_keys(tool_log)
    for key in reversed(keys):
        if tool_log[key].get("result", "") == "":
            return key
    return None


def find_recent_successful_result(tool_log, command):
    for key in reversed(get_current_turn_tool_log_keys(tool_log)):
        tool_item = tool_log[key]
        if tool_item.get("action", "") != command:
            continue
        result_text = tool_item.get("result", "")
        if result_text == "":
            continue
        if result_text.startswith(REUSED_TOOL_RESULT_PREFIX):
            continue
        if "无法执行" in result_text:
            continue
        if "未找到工具" in result_text:
            continue
        if "工具调用次数已达上限" in result_text:
            continue
        if "工具执行失败" in result_text:
            continue
        return result_text
    return None


def is_tool_enabled(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def get_tool_limit(tool_log):
    limit_value = tool_log.get("single_chat_tools_use_num", 0)
    try:
        return int(limit_value)
    except (TypeError, ValueError):
        return 0


def get_tool_call_count(tool_log):
    count_value = tool_log.get("tool_call_count")
    try:
        if count_value is not None:
            return int(count_value)
    except (TypeError, ValueError):
        pass
    return len(get_current_turn_tool_log_keys(tool_log))


def get_current_turn_log_offset(tool_log):
    offset_value = tool_log.get("current_turn_log_offset", 0)
    try:
        offset = int(offset_value)
    except (TypeError, ValueError):
        offset = 0
    total_logs = len(tool_log_keys(tool_log))
    if offset < 0:
        return 0
    if offset > total_logs:
        return total_logs
    return offset


def get_current_turn_tool_log_keys(tool_log):
    keys = tool_log_keys(tool_log)
    return keys[get_current_turn_log_offset(tool_log) :]


def trim_tool_log(tool_log):
    limit = get_tool_limit(tool_log)
    if limit <= 0:
        return tool_log

    keys = tool_log_keys(tool_log)
    kept_keys = keys[-limit:]
    removed_count = len(keys) - len(kept_keys)
    kept_items = [tool_log[key] for key in kept_keys]
    trimmed_tool_log = {
        "tool_use": tool_log["tool_use"],
        "single_chat_tools_use_num": tool_log["single_chat_tools_use_num"],
        "tool_call_count": get_tool_call_count(tool_log),
        "current_turn_log_offset": max(get_current_turn_log_offset(tool_log) - removed_count, 0),
    }
    for index, item in enumerate(kept_items, start=1):
        trimmed_tool_log[f"num_{index}"] = item
    return trimmed_tool_log


def get_category_dir(category):
    return root_dir / "system" / category


def category_directories(category):
    category_dir = get_category_dir(category)
    if category_dir.exists() is False:
        return []
    directories = [item.name for item in category_dir.iterdir() if item.is_dir()]
    directories.sort()
    return directories


def discover_tools():
    tools = []
    for category in ("plugins", "skills", "mcp"):
        config = TOOL_CATEGORIES[category]
        category_dir = get_category_dir(category)
        if category_dir.exists() is False:
            continue
        for tool_dir in sorted([item for item in category_dir.iterdir() if item.is_dir()], key=lambda item: item.name):
            spec_path = tool_dir / config["spec_file"]
            if spec_path.exists() is False:
                continue
            spec_data = load_json(spec_path)
            entries = [key for key in spec_data if key.startswith("num_")]
            entries.sort(key=lambda item: int(item.split("_")[1]))
            for entry_key in entries:
                entry_data = spec_data[entry_key]
                command = entry_data.get("command", "").strip()
                if command == "":
                    continue
                tools.append(
                    {
                        "category": category,
                        "name": tool_dir.name,
                        "command": command,
                        "explain": entry_data.get("explain", "").strip(),
                        "run_file": entry_data.get("run_file", "").strip(),
                        "directory": tool_dir,
                        "use_path": tool_dir / config["use_file"],
                        "run_paths": [tool_dir / run_dir / entry_data.get("run_file", "") for run_dir in config["run_dirs"]],
                    }
                )
    return tools


def format_directory_overview():
    lines = []
    for category in ("plugins", "skills", "mcp"):
        names = category_directories(category)
        lines.append(f"{category}:{'|'.join(names)}")
    return "\n".join(lines)


def format_tool_list(tools):
    if len(tools) == 0:
        return "未发现可用工具"
    lines = []
    for tool in tools:
        line = tool["command"]
        if tool["explain"] != "":
            line = f"{line} {tool['explain']}"
        lines.append(line)
    return "\n".join(lines)


def find_tool_by_directory_name(tools, query):
    normalized_query = normalize_tool_token(query)
    for tool in tools:
        if normalize_tool_token(tool["name"]) == normalized_query:
            return tool
    return None


def normalize_tool_token(text):
    normalized = text.strip().casefold()
    while normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized


def build_tool_aliases(tool):
    command = tool["command"].strip()
    aliases = {
        tool["name"].strip(),
        command,
        command.lstrip("/"),
        f"/{tool['name'].strip()}",
        tool["explain"].strip(),
    }
    return {normalize_tool_token(alias) for alias in aliases if alias.strip() != ""}


def find_tool_by_command(tools, command_name):
    normalized_command = normalize_tool_token(command_name)
    for tool in tools:
        if normalized_command in build_tool_aliases(tool):
            return tool
    return None


def find_tool_for_search(tools, query):
    tool = find_tool_by_directory_name(tools, query)
    if tool is not None:
        return tool
    tool = find_tool_by_command(tools, query)
    if tool is not None:
        return tool

    normalized_query = normalize_tool_token(query)
    if normalized_query == "":
        return None

    for tool in tools:
        search_texts = [
            tool["name"],
            tool["command"],
            tool["command"].lstrip("/"),
            tool["explain"],
        ]
        for text in search_texts:
            if normalized_query in normalize_tool_token(text):
                return tool
    return None


def read_use_file(tool):
    if tool["use_path"].exists() is False:
        return "未提供说明文件"
    content = read_text(tool["use_path"]).strip()
    if content == "":
        return "未提供说明文件"
    return content


def handle_tool_search(command, tools):
    query = command[len("tool_search") :].strip()
    if query == "":
        return format_tool_list(tools)
    if query == "tools":
        return format_directory_overview()
    tool = find_tool_for_search(tools, query)
    if tool is None:
        return f"未找到工具说明：{query}"
    return read_use_file(tool)


def resolve_run_path(tool):
    for run_path in tool["run_paths"]:
        if run_path.exists():
            return run_path
    return None


def execute_tool_command(tool_command, tools):
    if tool_command == "":
        return "tool_use 缺少具体指令"
    command_name = tool_command.split()[0]
    tool = find_tool_by_command(tools, command_name)
    if tool is None:
        return f"未找到工具：{command_name}"
    if tool["category"] == "mcp":
        return "当前 mcp 未实现本地执行"

    run_path = resolve_run_path(tool)
    if run_path is None:
        return f"工具运行文件不存在：{tool['run_file']}"

    try:
        result = subprocess.run(
            [sys.executable, str(run_path), tool_command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except Exception as error:
        return f"工具执行失败：{error}"

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if result.returncode != 0:
        if stderr != "":
            return f"工具执行失败：{stderr}"
        if stdout != "":
            return stdout
        return f"工具执行失败：返回码 {result.returncode}"

    if stdout != "":
        return stdout
    if stderr != "":
        return stderr
    return "工具未返回任何结果"


def handle_tool_use(command, tools):
    tool_command = command[len("tool_use") :].strip()
    return execute_tool_command(tool_command, tools)


def run_command(command):
    tools = discover_tools()
    if command == "tool_search" or command.startswith("tool_search "):
        return handle_tool_search(command, tools)
    if command == "tool_use" or command.startswith("tool_use "):
        return handle_tool_use(command, tools)
    return f"不支持的指令：{command}"


def write_pending_result(cache_data, pending_key, result_text):
    cache_data["tool_log"][pending_key]["result"] = result_text
    cache_data["tool_log"] = trim_tool_log(cache_data["tool_log"])
    save_json(cache_path, cache_data)


def sync_pending_action(cache_data, pending_key, command, announce):
    cache_data["tool_log"][pending_key]["action"] = command
    cache_data["tool_log"] = trim_tool_log(cache_data["tool_log"])
    save_json(cache_path, cache_data)
    if announce:
        print(f"执行:{command}", flush=True)


def increment_tool_call_count(cache_data):
    cache_data["tool_log"]["tool_call_count"] = get_tool_call_count(cache_data["tool_log"]) + 1
    cache_data["tool_log"] = trim_tool_log(cache_data["tool_log"])
    save_json(cache_path, cache_data)


def continue_tool_loop():
    subprocess.run([sys.executable, str(provider_path), "type:tool"])


def handle_task(command):
    cache_data = load_json(cache_path)
    pending_key = get_pending_tool_key(cache_data["tool_log"])
    if pending_key is None:
        return
    sync_pending_action(cache_data, pending_key, command, announce=False)

    recent_result = find_recent_successful_result(cache_data["tool_log"], command)
    if recent_result is not None:
        write_pending_result(cache_data, pending_key, f"{REUSED_TOOL_RESULT_PREFIX}\n{recent_result}")
        continue_tool_loop()
        return

    if is_tool_enabled(cache_data["tool_log"].get("tool_use")) is False:
        write_pending_result(cache_data, pending_key, f"{command}无法执行，请检查用户文件配置")
        continue_tool_loop()
        return

    tool_count = get_tool_call_count(cache_data["tool_log"])
    tool_limit = get_tool_limit(cache_data["tool_log"])
    if tool_limit > 0 and tool_count > tool_limit:
        write_pending_result(cache_data, pending_key, "工具调用次数已达上限")
        continue_tool_loop()
        return

    sync_pending_action(cache_data, pending_key, command, announce=True)
    increment_tool_call_count(cache_data)
    result_text = run_command(command)
    write_pending_result(cache_data, pending_key, result_text)
    continue_tool_loop()


if payload.startswith("type:task"):
    task_command = parse_task_payload(payload)
    if task_command != "":
        handle_task(task_command)
