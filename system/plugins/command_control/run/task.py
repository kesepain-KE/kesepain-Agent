import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]
LIST_COMMAND = "/查询全部指令"
DETAIL_COMMAND = "/查看指令说明"
CATEGORIES = ("plugins", "skills", "mcp")
payload = " ".join(sys.argv[1:]).strip()


def set_stream_utf8(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


set_stream_utf8(sys.stdout)
set_stream_utf8(sys.stderr)
set_stream_utf8(sys.stdin)


def read_payload():
    if payload != "":
        return payload
    return sys.stdin.buffer.readline().decode("utf-8").strip()


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_text(path):
    with path.open("r", encoding="utf-8") as file:
        return file.read()


def get_usage_text():
    return "\n".join(
        [
            f"用法：{LIST_COMMAND}",
            f"用法：{DETAIL_COMMAND} <特定指令>",
        ]
    )


def get_detail_usage_text():
    return f"用法：{DETAIL_COMMAND} <特定指令>"


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


def normalize_command(command):
    text = str(command).strip()
    if text == "":
        return ""
    if text.startswith("/") is False:
        text = "/" + text.lstrip("/")
    return text


def match_command(spec_command, input_command):
    left = normalize_command(spec_command)
    right = normalize_command(input_command)
    if left == "" or right == "":
        return False
    if right == left:
        return True
    return right.startswith(left + " ")


def get_tool_specs():
    tools = []
    system_dir = ROOT_DIR / "system"

    for category in CATEGORIES:
        category_dir = system_dir / category
        if category_dir.exists() is False:
            continue

        for tool_dir in sorted(category_dir.iterdir(), key=lambda item: item.name):
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
                item = spec_data.get(key)
                if isinstance(item, dict) is False:
                    continue

                command = str(item.get("command", "")).strip()
                explain = str(item.get("explain", "")).strip()
                run_file = str(item.get("run_file", "")).strip()
                if command == "" or run_file == "":
                    continue

                run_path = tool_dir / "run" / run_file
                if run_path.exists() is False:
                    continue

                tools.append(
                    {
                        "category": category,
                        "tool_dir": tool_dir,
                        "command": command,
                        "explain": explain,
                    }
                )

    return tools


def build_list_output(tools):
    lines = ["查询结果："]
    for tool in tools:
        lines.append(f"{tool['command']} {tool['explain']}".rstrip())
    return "\n".join(lines)


def find_tool_by_command(tools, target_command):
    for tool in tools:
        if match_command(tool["command"], target_command):
            return tool
    return None


def handle_list(command):
    if command.strip() != LIST_COMMAND:
        return get_usage_text()
    return build_list_output(get_tool_specs())


def handle_detail(command):
    command_text = command.strip()
    if command_text.startswith(DETAIL_COMMAND) is False:
        return get_usage_text()

    target_command = command_text[len(DETAIL_COMMAND) :].strip()
    if target_command == "":
        return get_detail_usage_text()

    tools = get_tool_specs()
    tool = find_tool_by_command(tools, target_command)
    if tool is None:
        return f"未找到指令：{target_command}"

    use_path = tool["tool_dir"] / "use.txt"
    if use_path.exists() is False:
        return f"{tool['command']}缺少用法文件：use.txt"

    try:
        return read_text(use_path)
    except OSError as error:
        return f"{tool['command']}读取用法文件失败：{error}"


def main():
    command = read_payload()
    if command == "":
        print(get_usage_text())
        return

    if command.startswith(LIST_COMMAND):
        print(handle_list(command))
        return

    if command.startswith(DETAIL_COMMAND):
        print(handle_detail(command))
        return

    print(get_usage_text())


if __name__ == "__main__":
    main()
