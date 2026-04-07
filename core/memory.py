import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# memory.py 负责“历史对话文件”和“运行时 cache.history_date”之间的同步：
# - read 模式：把用户历史文件里的摘要和最近若干条消息装载进 cache。
# - continue 模式：把当前轮 user_input / LLM_output 追加入历史文件，
#   并在达到阈值时触发历史压缩。
ROOT_DIR = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT_DIR / "core" / "temp" / "cache.json"


def load_payload():
    """读取入口模式。

    约定：
    - 只接受 type:read / type:continue。
    - 缺省时返回空字符串，使脚本保持无副作用退出。
    """
    if len(sys.argv) > 1:
        return sys.argv[1]
    return ""


payload = load_payload()


def load_json(path):
    """以 UTF-8 读取 JSON 文件。"""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    """以 UTF-8 保存 JSON 文件。"""
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def get_history_path(cache_data):
    """根据当前 cache 定位用户历史文件路径。"""
    return ROOT_DIR / "users" / cache_data["name"] / "chat_history" / cache_data["memory"]["memory_path"]


def get_history_keys(standard_chat):
    """按 history_1 / history_2 的数字顺序返回历史键。"""
    keys = [key for key in standard_chat if key.startswith("history_")]
    keys.sort(key=lambda key: int(key.split("_")[1]))
    return keys


def get_history_items(history_data):
    """把标准历史区转换成按时间顺序排列的消息列表。"""
    standard_chat = history_data.get("standard_chat", {})
    if isinstance(standard_chat, dict) is False:
        standard_chat = {}
    return [standard_chat[key] for key in get_history_keys(standard_chat)]


def format_time():
    """生成历史文件里统一使用的时间字符串。"""
    now = datetime.now()
    return f"{now.year}.{now.month:02d}.{now.day:02d}.{now.hour:02d}:{now.minute:02d}:{now.second:02d}"


def build_zip_payload(zip_messages):
    """把待压缩历史整理成 provider type:zip 的传参格式。"""
    zip_lines = ["type:zip", "zip:"]
    for index, message in enumerate(zip_messages, start=1):
        zip_lines.append(f"{index}|{message['time']}|{message['input']}|{message['output']}")
    return "\n".join(zip_lines)


def rebuild_standard_chat(messages):
    """把压缩后保留的消息列表重建回 history_N 键结构。"""
    rebuilt = {}
    for index, message in enumerate(messages, start=1):
        rebuilt[f"history_{index}"] = {
            "time": message.get("time", ""),
            "input": message.get("input", ""),
            "output": message.get("output", ""),
        }
    return rebuilt


def run_provider_zip(zip_payload):
    """调用 provider 的 zip 模式压缩旧历史。"""
    return subprocess.run(
        [sys.executable, str(ROOT_DIR / "provider" / "provider.py"), "--payload-stdin"],
        input=zip_payload,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def run_read():
    """把历史文件中的摘要和最近若干条消息装载进 cache.history_date。

    维护说明：
    - zip_chat 对应 cache.history_date.zip_date。
    - standard_chat 中只截取最近 memory_chat_num 条，避免每轮把全部历史都发给模型。
    """
    cache_data = load_json(CACHE_PATH)
    history_path = get_history_path(cache_data)
    history_data = load_json(history_path)
    history_items = get_history_items(history_data)
    memory_chat_num = int(cache_data["history"]["memory_chat_num"])
    latest_items = history_items[-memory_chat_num:] if memory_chat_num > 0 else []

    zip_chat = history_data.get("zip_chat", "")
    if isinstance(zip_chat, str) is False:
        zip_chat = ""
    history_date = {"zip_date": zip_chat}

    for index, item in enumerate(latest_items, start=1):
        history_date[f"history_{index}"] = {
            "time": item.get("time", ""),
            "input": item["input"],
            "output": item["output"],
        }

    cache_data["history_date"] = history_date
    save_json(CACHE_PATH, cache_data)
    print("type:runed")


def run_continue():
    """把当前轮对话写回历史文件，并在达到阈值时触发压缩。

    顺序说明：
    1. 先把当前 cache.user_input / cache.LLM_output 追加进用户历史文件。
    2. 再判断 standard_chat 是否达到 history_max。
    3. 达到阈值时，把最旧的 (history_max - history_zip_to_num) 条交给 provider 压缩。
    4. 用 zip_chat 保存压缩摘要，并把未压缩保留区重排为 history_1...history_N。
    """
    cache_data = load_json(CACHE_PATH)
    history_path = get_history_path(cache_data)
    history_data = load_json(history_path)
    if isinstance(history_data.get("standard_chat"), dict) is False:
        history_data["standard_chat"] = {}

    standard_chat = history_data["standard_chat"]
    next_index = len(get_history_keys(standard_chat)) + 1
    standard_chat[f"history_{next_index}"] = {
        "time": format_time(),
        "input": cache_data.get("user_input", ""),
        "output": cache_data.get("LLM_output", ""),
    }
    save_json(history_path, history_data)

    history_items = get_history_items(history_data)
    history_max = int(cache_data["history"]["history_max"])
    history_zip_to_num = int(cache_data["history"]["history_zip_to_num"])

    # 仅在达到上限后压缩“最旧的一段历史”，保留最近 history_zip_to_num 条不压缩。
    if history_max > 0 and len(history_items) >= history_max:
        zip_num = history_max - history_zip_to_num
        if zip_num > 0:
            zip_messages = history_items[:zip_num]
            zip_payload = build_zip_payload(zip_messages)
            zip_output = run_provider_zip(zip_payload)
            if zip_output.startswith("zip:"):
                # 只有 provider 明确返回 zip: 前缀时，才认为压缩成功并回写结果。
                history_data["zip_chat"] = zip_output[len("zip:") :]
                kept_messages = history_items[zip_num:]
                history_data["standard_chat"] = rebuild_standard_chat(kept_messages)
                save_json(history_path, history_data)

    print("type:runed")


if payload == "type:read":
    run_read()


if payload == "type:continue":
    run_continue()
