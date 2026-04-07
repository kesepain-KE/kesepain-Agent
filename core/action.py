import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# action.py 是工具执行链的调度节点：
# 1. 从 provider 写入的 type:task 载荷里解析要执行的指令。
# 2. 记录本轮工具调用日志与计数。
# 3. 运行具体插件/技能脚本，或处理内置的 tool_search / tool_use 指令。
# 4. 将结果写回 cache.json，再把控制权交还给 provider 继续生成回复。
root_dir = Path(__file__).resolve().parent.parent
cache_path = root_dir / "core" / "temp" / "cache.json"
provider_path = root_dir / "provider" / "provider.py"


def safe_reconfigure_text_stream(stream):
    # 统一当前进程的标准流编码，避免工具输出中的中文在 Windows 控制台下乱码。
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


def load_payload():
    # action.py 既支持直接把 payload 放在 argv，也支持通过 stdin 读取长文本。
    if len(sys.argv) > 1 and sys.argv[1] == "--payload-stdin":
        return sys.stdin.buffer.read().decode("utf-8")
    if len(sys.argv) > 1:
        return sys.argv[1]
    return ""


payload = load_payload()
safe_reconfigure_text_stream(sys.stdout)
safe_reconfigure_text_stream(sys.stderr)


def has_usable_fileno(stream):
    """判断一个标准流对象是否能安全地提供 fileno。"""
    try:
        fileno_method = stream.fileno
    except AttributeError:
        return False

    if not callable(fileno_method):
        return False
    try:
        fileno_method()
    except (OSError, ValueError):
        return False
    return True


def get_console_run_kwargs():
    # 透传 stdin / stderr，让被拉起的 provider 或工具脚本继续共用当前控制台。
    kwargs = {}
    for name, stream in (("stdin", sys.stdin), ("stderr", sys.stderr)):
        if has_usable_fileno(stream) is False:
            continue
        kwargs[name] = stream
    return kwargs


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def read_text(path):
    with path.open("r", encoding="utf-8") as file:
        return file.read()

    # type:task 的协议中，真正的待执行指令放在后续的 command: 行里。
def get_command(text):
    prefix = "command:"
    lines = text.splitlines()
    for line in lines[1:]:
        if line.startswith(prefix):
            return line.partition(prefix)[2].strip()
    return ""


def get_num_keys(tool_log):
    keys = [key for key in tool_log if key.startswith("num_")]
    keys.sort(key=lambda item: int(item.split("_")[1]))
    return keys


def get_tool_log_item_key(tool_log):
    # 如果上一条工具日志只有 action 还没写 result，就继续复用那一格。
    keys = get_num_keys(tool_log)
    if len(keys) != 0 and tool_log[keys[-1]].get("result", "") == "":
        return keys[-1]
    return f"num_{len(keys) + 1}"


def trim_tool_log(tool_log):
    # tool_log 既有配置项，也有 num_* 的历史记录。
    # 这里只裁剪历史记录条数，并在裁剪后重新编号，避免日志无限增长。
    keys = get_num_keys(tool_log)
    limit = int(tool_log.get("tool_log_max", 0))
    if limit <= 0:
        limit = len(keys)
    kept_keys = keys[-limit:]
    kept_items = [tool_log[key] for key in kept_keys]

    trimmed_tool_log = {}
    for key, value in tool_log.items():
        if key.startswith("num_") is False:
            trimmed_tool_log[key] = value

    for index, item in enumerate(kept_items, start=1):
        trimmed_tool_log[f"num_{index}"] = item
    return trimmed_tool_log


def get_tool_use_allow(cache_data):
    # 兼容旧字段 tool_use，新字段优先使用 tool_use_allow。
    tool_log = cache_data.get("tool_log", {})
    value = tool_log.get("tool_use_allow")
    if isinstance(value, bool):
        return value

    fallback = tool_log.get("tool_use")
    if isinstance(fallback, bool):
        return fallback
    return False


def increment_tool_single_count(cache_data):
    # 记录当前一轮对话里已经调了多少次工具。
    # 达到上限后，后面的调度会直接返回限制提示，不再真正执行工具。
    tool_log = cache_data.get("tool_log", {})
    current = int(tool_log.get("tool_single_count", 0)) + 1

    tool_log_max = int(tool_log.get("tool_log_max", 0))
    if tool_log_max > 0 and current > tool_log_max:
        current = tool_log_max

    tool_log["tool_single_count"] = current
    cache_data["tool_log"] = trim_tool_log(tool_log)
    save_json(cache_path, cache_data)
    return current


def write_action(cache_data, command):
    # 先落 action，再执行工具。这样即使工具执行异常，日志里也能看到本次尝试。
    tool_log = cache_data.get("tool_log", {})
    item_key = get_tool_log_item_key(tool_log)
    if item_key not in tool_log:
        tool_log[item_key] = {}

    if "time" not in tool_log[item_key] or str(tool_log[item_key].get("time", "")).strip() == "":
        tool_log[item_key]["time"] = datetime.now().strftime("%Y.%m.%d.%H:%M:%S")
    tool_log[item_key]["action"] = command

    cache_data["tool_log"] = trim_tool_log(tool_log)
    save_json(cache_path, cache_data)

    keys = get_num_keys(cache_data["tool_log"])
    if len(keys) == 0:
        return item_key
    return keys[-1]


def write_result(cache_data, item_key, result):
    # 正常情况下 result 会写回 write_action 对应的那一项。
    # 这里保留兜底，避免异常流程下 tool_log 缺少目标项时直接丢结果。
    tool_log = cache_data.get("tool_log", {})
    if item_key not in tool_log:
        keys = get_num_keys(tool_log)
        if len(keys) != 0:
            item_key = keys[-1]
        else:
            item_key = "num_1"
            tool_log[item_key] = {
                "time": datetime.now().strftime("%Y.%m.%d.%H:%M:%S"),
                "action": "",
                "result": "",
            }

    tool_log[item_key]["result"] = result
    cache_data["tool_log"] = trim_tool_log(tool_log)
    save_json(cache_path, cache_data)


def is_tool_search_command(command):
    return command == "tool_search" or command.startswith("tool_search ")


def is_tool_use_command(command):
    return command == "tool_use" or command.startswith("tool_use ")


def normalize_tool_command(command):
    # 注册命令和运行时命令都允许带或不带 "/"，匹配前统一归一化。
    return command.strip().lstrip("/")


def match_tool_command(spec_command, runtime_command):
    left = normalize_tool_command(spec_command)
    right = normalize_tool_command(runtime_command)
    if right == left:
        return True
    return right.startswith(left + " ")


def get_command_order_key(key):
    if key.startswith("num_"):
        suffix = key[len("num_") :]
        if suffix.isdigit():
            return int(suffix)
    if key.startswith("command_"):
        suffix = key[len("command_") :]
        if suffix.isdigit():
            return int(suffix)
    return 10**9


def get_tool_by_command(tools, command):
    if command == "":
        return None
    for tool in tools:
        if match_tool_command(tool["command"], command):
            return tool
    return None


def get_tool_specs():
    # 动态扫描 system/plugins、system/skills、system/mcp 下的 command.json。
    # 这里不直接缓存，目的是让新工具或命令改动能在下一次执行时立即生效。
    tools = []
    for category in ("plugins", "skills", "mcp"):
        category_dir = root_dir / "system" / category
        if category_dir.exists() is False:
            continue

        for tool_dir in category_dir.iterdir():
            if tool_dir.is_dir() is False:
                continue

            spec_path = tool_dir / "command.json"
            if spec_path.exists() is False:
                continue

            try:
                spec_data = load_json(spec_path)
            except (OSError, json.JSONDecodeError):
                continue

            if isinstance(spec_data, dict) is False:
                continue

            for key in sorted(spec_data.keys(), key=get_command_order_key):
                item = spec_data[key]
                if isinstance(item, dict) is False:
                    continue

                command = str(item.get("command", "")).strip()
                explain = str(item.get("explain", "")).strip()
                run_file = str(item.get("run_file", "")).strip()
                if command == "" or run_file == "":
                    continue

                tools.append(
                    {
                        "category": category,
                        "tool_dir": tool_dir,
                        "command": command,
                        "explain": explain,
                        "run_file": run_file,
                    }
                )

    return tools


def get_tool_search_result(command):
    # tool_search 是 action.py 内置指令，不会再转发给外部 run/*.py。
    # 它用于让模型查询工具列表或某条指令对应的 use.txt。
    command = command.strip()
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

    query = command[len("tool_search") :].strip()
    if query == "":
        return "tool_search缺少具体指令"

    tool = get_tool_by_command(tools, query)
    if tool is None:
        return f"{query}未找到对应工具"

    use_path = tool["tool_dir"] / "use.txt"
    if use_path.exists() is False:
        return f"{tool['command']}缺少用法文件：{use_path.name}"

    try:
        return read_text(use_path)
    except OSError as error:
        return f"{tool['command']}读取用法文件失败：{error}"


def run_tool_command(command):
    # 普通注册指令会落到这里执行。
    # 统一以 stdout 作为工具返回值协议，因此工具脚本只需要 print 最终结果。
    tools = get_tool_specs()
    tool = get_tool_by_command(tools, command)
    if tool is None:
        return f"不支持的指令类型：{command}"

    run_path = tool["tool_dir"] / "run" / tool["run_file"]
    if run_path.exists() is False:
        return f"{tool['command']}缺少运行文件：{run_path.name}"

    try:
        return subprocess.run(
            [sys.executable, str(run_path), command],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            **get_console_run_kwargs(),
        ).stdout.strip()
    except OSError as error:
        return f"{tool['command']}执行失败：{error}"


def get_tool_use_result(command):
    # tool_use <具体指令> 只是内置壳，真正执行的仍然是具体工具命令本身。
    command = command.strip()
    tool_command = command[len("tool_use") :].strip()
    if tool_command == "":
        return "tool_use缺少具体指令"
    return run_tool_command(tool_command)


def get_command_result(command):
    # 统一收口所有可执行入口，方便主流程只关心一层 dispatch。
    if command == "":
        return "未提供可执行指令"
    if is_tool_search_command(command):
        return get_tool_search_result(command)
    if is_tool_use_command(command):
        return get_tool_use_result(command)
    return run_tool_command(command)


if payload.startswith("type:task"):
    # action.py 只处理 provider 明确下发的工具任务。
    # 其他 type 由各自链路文件负责，这里不做额外分支扩展。
    command = get_command(payload)

    cache_data = load_json(cache_path)
    tool_single_count = increment_tool_single_count(cache_data)

    cache_data = load_json(cache_path)
    item_key = write_action(cache_data, command)
    print(f"执行:{command}")

    deny_message = f"{command}无法执行，请检查用户文件配置或查询指令用法"
    max_limit_message = f"{command}无法执行，已达到最大调用工具次数"

    cache_data = load_json(cache_path)
    tool_log = cache_data.get("tool_log", {})
    single_chat_tools_use_num = int(tool_log.get("single_chat_tools_use_num", 0))
    if get_tool_use_allow(cache_data) is False:
        result = deny_message
    elif single_chat_tools_use_num > 0 and tool_single_count >= single_chat_tools_use_num:
        result = max_limit_message
    else:
        result = get_command_result(command)

    cache_data = load_json(cache_path)
    write_result(cache_data, item_key, result)
    # 工具结果写回后，重新进入 provider 的 type:tool 分支，
    # 让大模型基于最新 tool_log 继续决定是总结结果还是发起下一步动作。
    subprocess.run(
        [sys.executable, str(provider_path), "type:tool"],
        **get_console_run_kwargs(),
    )
