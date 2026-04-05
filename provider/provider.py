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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


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
    lines = ["history:", f"zip:{history_date.get('zip_date', '')}"]
    for index, key in enumerate(get_num_keys(history_date), start=1):
        item = history_date[key]
        lines.append(f"{index}.{item['time']}|{item['input']}|{item['output']}")
    return lines


def build_tool_lines(tool_log):
    lines = ["tool:"]
    for index, key in enumerate(get_num_keys(tool_log), start=1):
        item = tool_log[key]
        lines.append(f"{index}.{item['action']}|{item['result']}")
    return lines


def run_llm(run_file, llm_payload):
    result = subprocess.run(
        [sys.executable, str(llm_dir / run_file), "--payload-stdin"],
        input=llm_payload,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
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
        "action": command,
        "result": "",
    }
    cache_data["tool_log"] = trim_tool_log(tool_log)


def handle_result(cache_data, llm_output):
    if llm_output.startswith("type:message"):
        output, token = parse_message_result(llm_output)
        cache_data["LLM_output"] = output
        cache_data["token_use"] = cache_data["token_use"] + token
        save_json(cache_path, cache_data)
        print(f"{output}|token:{cache_data['token_use']}")
        cache_data["token_use"] = 0
        save_json(cache_path, cache_data)
        subprocess.run([sys.executable, str(root_dir / "core" / "date_analyze.py"), "type:continue"])
    if llm_output.startswith("type:task"):
        command, token = parse_task_result(llm_output)
        append_command(cache_data, command)
        cache_data["token_use"] = cache_data["token_use"] + token
        save_json(cache_path, cache_data)
        subprocess.run(
            [
                sys.executable,
                str(root_dir / "core" / "action.py"),
                "\n".join(["type:task", f"command:{command}"]),
            ]
        )


def run_start():
    cache_data = load_json(cache_path)
    provider_data = get_allow_provider_data(cache_data)
    if provider_data is None:
        print("当前模型未获得允许，请前往provider\\api.json修改")
        return
    config_data = load_json(config_path)
    prompt_text = read_text(root_dir / "system" / "prompt" / cache_data["prompt"])
    task_prompt_text = read_text(root_dir / "system" / "prompt" / "system_core" / config_data["task_prompt"])
    history_date = {}
    if cache_data["memory"]["memory_use"] is True:
        history_date = cache_data["history_date"]
    llm_payload = "\n".join(
        [
            "type:chat",
            "prompt:",
            f"main_soul={prompt_text}",
            f"else_for_run={task_prompt_text}",
            f"base_url:{provider_data['base_url']}",
            f"API_key:{cache_data['API']['key']}",
            f"API_model:{cache_data['API']['model']}",
            f"user_input:{cache_data['user_input']}",
            *build_history_lines(history_date),
        ]
    )
    llm_output = run_llm(provider_data["api_provider"], llm_payload)
    handle_result(cache_data, llm_output)


def run_zip():
    config_data = load_json(config_path)
    api_data = load_json(api_path)
    zip_config = config_data["zip_history"]
    provider_data = api_data[zip_config["API"]]
    zip_prompt_text = read_text(root_dir / "system" / "prompt" / "system_core" / zip_config["prompt"])
    llm_payload = "\n".join(
        [
            "type:prompt",
            f"prompt:{zip_prompt_text}",
            f"key:{zip_config['API_KEY']}",
            f"base_url:{zip_config['base_url']}",
            f"model:{zip_config['model']}",
            "zip:",
            *payload.splitlines()[2:],
        ]
    )
    llm_output = run_llm(provider_data["api_provider"], llm_payload)
    print(llm_output)


def run_tool():
    cache_data = load_json(cache_path)
    api_data = load_json(api_path)
    provider_data = api_data[cache_data["API"]["provider"]]
    config_data = load_json(config_path)
    prompt_text = read_text(root_dir / "system" / "prompt" / cache_data["prompt"])
    task_prompt_text = read_text(root_dir / "system" / "prompt" / "system_core" / config_data["task_prompt"])
    llm_payload = "\n".join(
        [
            "type:tool",
            "prompt:",
            f"main_soul={prompt_text}",
            f"else_for_run={task_prompt_text}",
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
