import json
import shutil
import subprocess
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parent
system_cache_path = root_dir / "system" / "start" / "cache.json"
history_template_path = root_dir / "system" / "start" / "history.json"
temp_cache_path = root_dir / "core" / "temp" / "cache.json"
users_dir = root_dir / "users"


def _safe_reconfigure_output(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None or not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def write_value(template_data, config_data):
    for key, value in config_data.items():
        if key == "tool_use":
            template_data["tool_log"]["tool_use"] = value
            continue
        if key not in template_data:
            continue
        if isinstance(value, dict) and isinstance(template_data[key], dict):
            write_value(template_data[key], value)
        else:
            template_data[key] = value


def get_user_names():
    return sorted([item.name for item in users_dir.iterdir() if item.is_dir()])


def select_user(user_names):
    print("当前拥有的用户：")
    for index, user_name in enumerate(user_names, start=1):
        print(f"{index}.{user_name}")

    print("请选择用户文件：", end="")
    selected_user = input().strip()
    if selected_user.isdigit():
        selected_index = int(selected_user) - 1
        if 0 <= selected_index < len(user_names):
            return user_names[selected_index]
        raise SystemExit("用户序号不存在")

    if selected_user in user_names:
        return selected_user

    raise SystemExit("用户不存在")


def ensure_history_file(user_name, user_config):
    history_path = (
        users_dir
        / user_name
        / "chat_history"
        / user_config["memory"]["memory_path"]
    )
    if history_path.exists():
        return
    history_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(history_template_path, history_path)


def main():
    shutil.copyfile(system_cache_path, temp_cache_path)

    user_names = get_user_names()
    user_name = select_user(user_names)

    user_config_path = users_dir / user_name / "config.json"
    user_config = load_json(user_config_path)
    user_config["name"] = user_name

    temp_cache = load_json(temp_cache_path)
    write_value(temp_cache, user_config)
    save_json(temp_cache_path, temp_cache)

    ensure_history_file(user_name, user_config)

    result = subprocess.run(
        [sys.executable, str(root_dir / "core" / "date_analyze.py"), "type:start"]
    )
    raise SystemExit(result.returncode)


_safe_reconfigure_output(sys.stdout)
_safe_reconfigure_output(sys.stderr)


if __name__ == "__main__":
    main()
