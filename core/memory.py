import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


root_dir = Path(__file__).resolve().parent.parent
cache_path = root_dir / "core" / "temp" / "cache.json"
payload = sys.argv[1]


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def get_history_path(cache_data):
    return root_dir / "users" / cache_data["name"] / "chat_history" / cache_data["memory"]["memory_path"]


def get_sorted_messages(history_data):
    messages = list(history_data["standard_chat"]["messages"].values())
    messages.sort(key=lambda item: item["num"])
    return messages


def is_template_message(message):
    return (
        message["time"] == "time"
        and message["input"] == "input"
        and message["output"] == "output"
    )


def normalize_zip_chat(zip_chat):
    if isinstance(zip_chat, list):
        return ""
    return zip_chat


def normalize_history_data(history_data):
    messages = get_sorted_messages(history_data)
    real_messages = []
    for message in messages:
        if is_template_message(message) is False:
            real_messages.append(message)
    history_data["zip_chat"] = normalize_zip_chat(history_data["zip_chat"])
    history_data["standard_chat"]["messages"] = renumber_messages(real_messages)
    return history_data


def format_time():
    now = datetime.now()
    return f"{now.year}.{now.month}.{now.day}.{now.hour}:{now.minute:02d}:{now.second:02d}"


def renumber_messages(messages):
    renumbered = {}
    for index, message in enumerate(messages, start=1):
        renumbered[f"num_{index}"] = {
            "num": index,
            "time": message["time"],
            "input": message["input"],
            "output": message["output"],
        }
    return renumbered


if payload == "type:read":
    cache_data = load_json(cache_path)
    if cache_data["memory"]["memory_use"] is True:
        history_path = get_history_path(cache_data)
        history_data = normalize_history_data(load_json(history_path))
        save_json(history_path, history_data)
        messages = get_sorted_messages(history_data)
        latest_messages = messages[-cache_data["history"]["memory_chat_num"] :]
        history_date = {"zip_date": history_data["zip_chat"]}
        for index, message in enumerate(latest_messages, start=1):
            history_date[f"num_{index}"] = {
                "time": message["time"],
                "input": message["input"],
                "output": message["output"],
            }
        cache_data["history_date"] = history_date
    if cache_data["memory"]["memory_use"] is False:
        cache_data["history_date"] = {}
    save_json(cache_path, cache_data)
    print("type:runed")


if payload == "type:continue":
    cache_data = load_json(cache_path)
    history_path = get_history_path(cache_data)

    if cache_data["memory"]["memory_save"] is True:
        history_data = normalize_history_data(load_json(history_path))
        messages = get_sorted_messages(history_data)
        next_num = len(messages) + 1
        history_data["standard_chat"]["messages"][f"num_{next_num}"] = {
            "num": next_num,
            "time": format_time(),
            "input": cache_data["user_input"],
            "output": cache_data["LLM_output"],
        }
        save_json(history_path, history_data)

    history_data = normalize_history_data(load_json(history_path))
    messages = get_sorted_messages(history_data)
    history_max = cache_data["history"]["history_max"]
    history_zip_to_num = cache_data["history"]["history_zip_to_num"]

    if len(messages) > history_max:
        zip_num = history_max - history_zip_to_num
        zip_messages = messages[:zip_num]
        zip_lines = ["type:zip", "zip:"]
        for index, message in enumerate(zip_messages, start=1):
            zip_lines.append(f"{index}.{message['time']}|{message['input']}|{message['output']}")
        zip_result = subprocess.run(
            [sys.executable, str(root_dir / "provider" / "provider.py"), "\n".join(zip_lines)],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        history_data["zip_chat"] = zip_result.stdout.strip()[4:]
        history_data["standard_chat"]["messages"] = renumber_messages(messages[zip_num:])
        save_json(history_path, history_data)

    print("type:runed")
