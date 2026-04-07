import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


root_dir = Path(__file__).resolve().parent.parent
cache_path = root_dir / "core" / "temp" / "cache.json"
config_path = root_dir / "core" / "config.json"
api_path = Path(__file__).resolve().parent / "api.json"
llm_dir = Path(__file__).resolve().parent / "LLM"


def safe_reconfigure_text_stream(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


def load_payload():
    if len(sys.argv) > 1 and sys.argv[1] == "--payload-stdin":
        return sys.stdin.buffer.read().decode("utf-8")
    if len(sys.argv) > 1:
        return sys.argv[1]
    return ""


payload = load_payload()
safe_reconfigure_text_stream(sys.stdout)


def get_console_run_kwargs():
    kwargs = {}
    for name, stream in (("stdin", sys.stdin), ("stderr", sys.stderr)):
        fileno = getattr(stream, "fileno", None)
        if callable(fileno) is False:
            continue
        try:
            fileno()
        except (OSError, ValueError):
            continue
        kwargs[name] = stream
    return kwargs


def get_stderr_run_kwargs():
    kwargs = {}
    fileno = getattr(sys.stderr, "fileno", None)
    if callable(fileno):
        try:
            fileno()
        except (OSError, ValueError):
            return kwargs
        kwargs["stderr"] = sys.stderr
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


def get_num_keys(data):
    keys = [key for key in data if key.startswith("num_")]
    keys.sort(key=lambda item: int(item.split("_")[1]))
    return keys


def get_history_keys(history_date):
    keys = [key for key in history_date if key.startswith("history_")]
    keys.sort(key=lambda item: int(item.split("_")[1]))
    return keys


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


def get_allow_provider_data(cache_data):
    api_data = load_json(api_path)
    api_provider = cache_data["API"]["provider"]
    api_model = cache_data["API"]["model"]
    if api_provider not in api_data:
        return None
    if api_model not in api_data[api_provider]["available_models"]:
        return None
    return api_data[api_provider]


def build_history_lines(history_date):
    lines = [f"zip:{history_date.get('zip_date', '')}"]
    for index, key in enumerate(get_history_keys(history_date), start=1):
        item = history_date[key]
        lines.append(f"{index}|{item.get('time', '')}|{item.get('input', '')}|{item.get('output', '')}")
    return lines


def build_start_history_lines(history_date):
    lines = [f"zip:{history_date.get('zip_date', '')}"]
    for index, key in enumerate(get_history_keys(history_date), start=1):
        item = history_date[key]
        lines.append(f"{index}|{item.get('time', '')}|{item.get('input', '')}|{item.get('output', '')}")
    return lines


def build_tool_lines(tool_log):
    lines = ["tool_log:"]
    for index, key in enumerate(get_num_keys(tool_log), start=1):
        item = tool_log[key]
        lines.append(f"{index}|{item.get('time', '')}|{item.get('action', '')}|{item.get('result', '')}")
    return lines


def run_llm(run_file, llm_payload):
    result = subprocess.run(
        [sys.executable, str(llm_dir / run_file), "--payload-stdin"],
        input=llm_payload,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        **get_stderr_run_kwargs(),
    )
    return result.stdout.strip()


def parse_message_result(text):
    lines = text.splitlines()
    output = "\n".join(lines[1:-1])[len("output:") :]
    token = int(lines[-1][len("token:") :])
    return output, token


def parse_task_result(text):
    lines = text.splitlines()
    command = "\n".join(lines[1:-1])[len("command:") :]
    token = int(lines[-1][len("token:") :])
    return command, token


def append_command(cache_data, command):
    tool_log = cache_data["tool_log"]
    index = 1
    while f"num_{index}" in tool_log:
        index += 1
    tool_log[f"num_{index}"] = {
        "time": datetime.now().strftime("%Y.%m.%d.%H:%M:%S"),
        "action": command,
        "result": "",
    }
    cache_data["tool_log"] = trim_tool_log(tool_log)


def handle_result(cache_data, llm_output):
    if llm_output.startswith("type:message"):
        output, token = parse_message_result(llm_output)
        cache_data["LLM_output"] = output
        cache_data["token_used"] = cache_data.get("token_used", 0) + token
        save_json(cache_path, cache_data)
        print(f"{output}|token:{cache_data['token_used']}")
        cache_data["token_used"] = 0
        save_json(cache_path, cache_data)
        subprocess.run(
            [sys.executable, str(root_dir / "core" / "date_analyze.py"), "type:continue"],
            **get_console_run_kwargs(),
        )
    if llm_output.startswith("type:task"):
        command, token = parse_task_result(llm_output)
        append_command(cache_data, command)
        cache_data["token_used"] = cache_data.get("token_used", 0) + token
        save_json(cache_path, cache_data)
        subprocess.run(
            [sys.executable, str(root_dir / "core" / "action.py"), "--payload-stdin"],
            input="\n".join(["type:task", f"command:{command}"]),
            text=True,
            encoding="utf-8",
            **get_stderr_run_kwargs(),
        )


def run_start():
    cache_data = load_json(cache_path)
    provider_data = get_allow_provider_data(cache_data)
    if provider_data is None:
        print("当前模型未获得允许，请前往provider\\api.json修改")
        return

    config_data = load_json(config_path)
    prompt_text = read_text(root_dir / "system" / "prompt" / "soul_prompt" / cache_data["soul_prompt"])
    task_prompt_text = read_text(root_dir / "system" / "prompt" / "system_core" / config_data["task_prompt"])
    history_date = cache_data.get("history_date", {})

    llm_payload = "\n".join(
        [
            "type:chat",
            f"soul_prompt:{prompt_text}",
            f"task_prompt:{task_prompt_text}",
            f"base_url:{provider_data['base_url']}",
            f"API_key:{cache_data['API']['key']}",
            f"API_model:{cache_data['API']['model']}",
            f"user_input:{cache_data['user_input']}",
            *build_start_history_lines(history_date),
        ]
    )

    llm_output = run_llm(provider_data["api_provider"], llm_payload)
    handle_result(cache_data, llm_output)


def run_zip():
    config_data = load_json(config_path)
    api_data = load_json(api_path)
    zip_config = config_data["history_zip"]
    provider_data = api_data[zip_config["API"]]
    zip_prompt_text = read_text(root_dir / "system" / "prompt" / "system_core" / zip_config["prompt"])

    payload_lines = payload.splitlines()
    if len(payload_lines) < 2 or payload_lines[0] != "type:zip" or payload_lines[1] != "zip:":
        print("zip:")
        return

    zip_lines = [line for line in payload_lines[2:] if line != ""]
    if len(zip_lines) == 0:
        print("zip:")
        return

    llm_payload = "\n".join(
        [
            "type:prompt",
            f"prompt:{zip_prompt_text}",
            f"key:{zip_config['API_KEY']}",
            f"base_url:{zip_config['base_url']}",
            f"model:{zip_config['model']}",
            *zip_lines,
        ]
    )
    llm_output = run_llm(provider_data["api_provider"], llm_payload)
    print(llm_output)


def run_tool():
    cache_data = load_json(cache_path)
    api_data = load_json(api_path)
    provider_data = api_data[cache_data["API"]["provider"]]
    config_data = load_json(config_path)
    prompt_text = read_text(root_dir / "system" / "prompt" / "soul_prompt" / cache_data["soul_prompt"])
    task_prompt_text = read_text(root_dir / "system" / "prompt" / "system_core" / config_data["task_prompt"])
    llm_payload = "\n".join(
        [
            "type:tool",
            f"soul_prompt={prompt_text}",
            f"task_prompt={task_prompt_text}",
            f"base_url:{provider_data['base_url']}",
            f"API_key:{cache_data['API']['key']}",
            f"API_model:{cache_data['API']['model']}",
            f"user_input:{cache_data['user_input']}",
            *build_history_lines(cache_data["history_date"]),
            *build_tool_lines(cache_data["tool_log"]),
        ]
    )
    llm_output = run_llm(provider_data["api_provider"], llm_payload)
    handle_result(cache_data, llm_output)


if payload == "type:start":
    run_start()


if payload.startswith("type:zip"):
    run_zip()


if payload == "type:tool":
    run_tool()
