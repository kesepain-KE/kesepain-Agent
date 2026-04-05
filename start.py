import json
import locale
import shutil
import subprocess
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parent
system_cache_path = root_dir / "system" / "start" / "cache.json"
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


def _safe_reconfigure_input(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None or not callable(reconfigure):
        return
    encoding = "utf-8"
    try:
        if stream.isatty():
            encoding = locale.getpreferredencoding(False) or "utf-8"
    except Exception:
        pass
    try:
        reconfigure(encoding=encoding)
    except Exception:
        pass


_safe_reconfigure_output(sys.stdout)
_safe_reconfigure_output(sys.stderr)
_safe_reconfigure_input(sys.stdin)

print("当前拥有的用户：")

def write_value(template_data, config_data):
    for key, value in config_data.items():
        if key == "tool_use":
            template_data["tool_log"]["tool_use"] = value
            continue
        if isinstance(value, dict):
            write_value(template_data[key], value)
        else:
            template_data[key] = value


shutil.copyfile(system_cache_path, temp_cache_path)

user_names = sorted([item.name for item in users_dir.iterdir() if item.is_dir()])

for index, user_name in enumerate(user_names, start=1):
    print(f"{index}.{user_name}")

print("请选择用户文件：", end="")
selected_user = input().strip()

if selected_user.isdigit():
    user_name = user_names[int(selected_user) - 1]
else:
    user_name = selected_user

user_config_path = users_dir / user_name / "config.json"
with user_config_path.open("r", encoding="utf-8") as file:
    user_config = json.load(file)

with temp_cache_path.open("r", encoding="utf-8") as file:
    temp_cache = json.load(file)

write_value(temp_cache, user_config)

with temp_cache_path.open("w", encoding="utf-8") as file:
    json.dump(temp_cache, file, ensure_ascii=False, indent=4)

subprocess.run([sys.executable, str(root_dir / "core" / "date_analyze.py"), "type:start"])
