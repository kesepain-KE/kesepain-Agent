import json
import subprocess
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parent.parent
config_path = Path(__file__).resolve().parent / "config.json"
cache_path = Path(__file__).resolve().parent / "temp" / "cache.json"
payload = sys.argv[1]


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


if payload == "type:start":
    config_data = load_json(config_path)
    cache_data = load_json(cache_path)
    cache_data["history"]["history_max"] = config_data["history_max"]
    cache_data["history"]["history_zip_to_num"] = config_data["history_zip_to_num"]
    cache_data["tool_log"]["single_chat_tools_use_num"] = config_data["single_chat_tools_use_num"]
    save_json(cache_path, cache_data)
    subprocess.run([sys.executable, str(root_dir / "provider" / "provider.py"), "type:start"])

if payload == "type:continue":
    subprocess.run([sys.executable, str(root_dir / "provider" / "provider.py"), "type:start"])
