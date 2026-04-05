import json
import subprocess
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parent.parent
cache_path = root_dir / "core" / "temp" / "cache.json"
config_path = root_dir / "core" / "config.json"
api_path = Path(__file__).resolve().parent / "api.json"
llm_dir = Path(__file__).resolve().parent / "LLM"
payload = sys.argv[1]

stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(stdout_reconfigure):
    stdout_reconfigure(encoding="utf-8")

stderr_reconfigure = getattr(sys.stderr, "reconfigure", None)
if callable(stderr_reconfigure):
    stderr_reconfigure(encoding="utf-8")


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def read_text(path):
    with path.open("r", encoding="utf-8") as file:
        return file.read()


def build_history_lines(history_date):
    lines = ["history:"]
    lines.append(f"zip:{history_date.get('zip_date', '')}")
    index = 1
    while f"num_{index}" in history_date:
        message = history_date[f"num_{index}"]
        lines.append(f"{index}.{message['time']}|{message['input']}|{message['output']}")
        index += 1
    return lines


def build_tool_lines(tool_log):
    lines = ["tool:"]
    display_index = 1
    for key in get_current_turn_tool_log_keys(tool_log):
        tool_item = tool_log[key]
        if is_placeholder_tool_item(tool_item):
            continue
        lines.append(f"{display_index}.{tool_item['action']}|{tool_item['result']}")
        display_index += 1
    return lines


def parse_message_result(text):
    lines = text.strip().splitlines()
    body_lines = lines[1:-1]
    if body_lines:
        body_lines[0] = body_lines[0][len("output:") :]
    return "\n".join(body_lines), int(lines[-1][len("token:") :])


def parse_task_result(text):
    lines = text.strip().splitlines()
    body_lines = lines[1:-1]
    if body_lines:
        body_lines[0] = body_lines[0][len("command:") :]
    return "\n".join(body_lines), int(lines[-1][len("token:") :])


def next_tool_log_key(tool_log):
    index = 1
    while f"num_{index}" in tool_log:
        index += 1
    return f"num_{index}"


def is_placeholder_tool_item(tool_item):
    return tool_item.get("action") == "input" and tool_item.get("result") == "output"


def tool_log_keys(tool_log):
    keys = []
    for key in tool_log:
        if key.startswith("num_") and is_placeholder_tool_item(tool_log[key]) is False:
            keys.append(key)
    keys.sort(key=lambda item: int(item.split("_")[1]))
    return keys


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


def append_tool_log_item(cache_data, action, result, increment_tool_call_count):
    tool_log = cache_data["tool_log"]
    if increment_tool_call_count:
        tool_log["tool_call_count"] = get_tool_call_count(tool_log) + 1
    tool_log[next_tool_log_key(tool_log)] = {
        "action": action,
        "result": result,
    }
    cache_data["tool_log"] = trim_tool_log(tool_log)


def get_provider_data(cache_data):
    api_data = load_json(api_path)
    api_provider = cache_data["API"]["provider"]
    api_model = cache_data["API"]["model"]
    provider_data = api_data.get(api_provider)
    if provider_data is None:
        return None
    if api_model not in provider_data["available_models"]:
        return None
    return provider_data


def build_common_llm_lines(cache_data, provider_data):
    config_data = load_json(config_path)
    main_soul = read_text(root_dir / "system" / "prompt" / cache_data["prompt"])
    task_prompt = read_text(root_dir / "system" / "prompt" / "system_core" / config_data["task_prompt"])
    history_date = {}
    if cache_data["memory"]["memory_use"] is True:
        history_date = cache_data["history_date"]
    return [
        "prompt:",
        f"main_soul={main_soul}",
        f"else_for_run={task_prompt}",
        f"base_url:{provider_data['base_url']}",
        f"API_key:{cache_data['API']['key']}",
        f"API_model:{cache_data['API']['model']}",
        f"user_input:{cache_data['user_input']}",
        *build_history_lines(history_date),
    ]


def build_interactive_payload(mode, cache_data, provider_data):
    llm_lines = [f"type:{mode}", *build_common_llm_lines(cache_data, provider_data)]
    if mode == "tool":
        llm_lines.extend(build_tool_lines(cache_data["tool_log"]))
    return "\n".join(llm_lines)


def run_llm(provider_data, llm_payload):
    llm_result = subprocess.run(
        [
            sys.executable,
            str(llm_dir / provider_data["api_provider"]),
            llm_payload,
        ],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return llm_result.stdout.strip()


def handle_message_output(cache_data, llm_output):
    output, token = parse_message_result(llm_output)
    cache_data["LLM_output"] = output
    cache_data["token_use"] += token
    current_token = cache_data["token_use"]
    save_json(cache_path, cache_data)
    print(f"{output}|token:{current_token}", flush=True)
    cache_data["token_use"] = 0
    save_json(cache_path, cache_data)
    subprocess.run([sys.executable, str(root_dir / "core" / "date_analyze.py"), "type:continue"])


def handle_task_output(cache_data, llm_output):
    command, token = parse_task_result(llm_output)
    cache_data["token_use"] += token
    tool_limit = get_tool_limit(cache_data["tool_log"])
    tool_call_count = get_tool_call_count(cache_data["tool_log"])
    if tool_limit > 0 and tool_call_count >= tool_limit:
        append_tool_log_item(
            cache_data,
            command,
            "工具调用次数已达上限",
            increment_tool_call_count=False,
        )
        save_json(cache_path, cache_data)
        subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "provider.py"), "type:tool"])
        return

    append_tool_log_item(cache_data, command, "", increment_tool_call_count=False)
    save_json(cache_path, cache_data)
    subprocess.run(
        [
            sys.executable,
            str(root_dir / "core" / "action.py"),
            "\n".join(["type:task", f"command:{command}"]),
        ]
    )


def handle_llm_output(cache_data, llm_output):
    if llm_output.startswith("type:message"):
        handle_message_output(cache_data, llm_output)
        return
    if llm_output.startswith("type:task"):
        handle_task_output(cache_data, llm_output)
        return
    if llm_output != "":
        print(llm_output, flush=True)


def run_interactive_mode(mode):
    cache_data = load_json(cache_path)
    provider_data = get_provider_data(cache_data)
    if provider_data is None:
        print("当前模型未获得允许，请前往provider\\api.json修改")
        return
    llm_payload = build_interactive_payload(mode, cache_data, provider_data)
    llm_output = run_llm(provider_data, llm_payload)
    handle_llm_output(cache_data, llm_output)


if payload == "type:start":
    run_interactive_mode("chat")


if payload == "type:tool":
    run_interactive_mode("tool")


if payload.startswith("type:zip"):
    config_data = load_json(config_path)
    api_data = load_json(api_path)
    zip_config = config_data["zip_history"]
    provider_data = api_data[zip_config["API"]]
    zip_prompt = read_text(root_dir / "system" / "prompt" / "system_core" / zip_config["prompt"])
    payload_lines = payload.splitlines()[2:]
    llm_lines = [
        "type:prompt",
        f"prompt:{zip_prompt}",
        f"key:{zip_config['API_KEY']}",
        f"base_url:{zip_config['base_url']}",
        f"model:{zip_config['model']}",
        "zip:",
        *payload_lines,
    ]
    llm_output = run_llm(provider_data, "\n".join(llm_lines))
    print(llm_output)
