import json
import sys
from pathlib import Path


payload = sys.argv[1]
cache_path = Path(__file__).resolve().parent / "temp" / "cache.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


if payload == "type:start":
    print("请输入文本：", end="", file=sys.stderr)
    user_input = input().strip()
    cache_data = load_json(cache_path)
    cache_data["user_input"] = user_input
    save_json(cache_path, cache_data)
    print("type:runed")


if payload == "type:continue":
    print("请继续输入文本：", end="", file=sys.stderr)
    user_input = input().strip()
    cache_data = load_json(cache_path)
    cache_data["user_input"] = user_input
    save_json(cache_path, cache_data)
    print("type:runed")
