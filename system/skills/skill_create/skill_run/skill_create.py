import json
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]
SKILLS_DIR = ROOT_DIR / "system" / "skills"
COMMAND_PREFIX = "/创建技能"
USAGE_TEXT = "用法：/创建技能 <skill目录名> | <指令名称> | <指令说明>"
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


def normalize_command_name(command_name):
    normalized = command_name.strip()
    if normalized == "":
        return ""
    if normalized.startswith("/") is False:
        normalized = f"/{normalized}"
    return normalized


def parse_command(command):
    command_text = command.strip()
    if command_text == "" or command_text.startswith(COMMAND_PREFIX) is False:
        return None, USAGE_TEXT

    body = command_text[len(COMMAND_PREFIX) :].strip()
    if body == "":
        return None, USAGE_TEXT

    parts = [item.strip() for item in body.split("|", 2)]
    if len(parts) != 3 or any(item == "" for item in parts):
        return None, USAGE_TEXT

    skill_name, command_name, description = parts
    if re.fullmatch(r"[A-Za-z0-9_-]+", skill_name) is None:
        return None, "skill目录名仅支持字母、数字、下划线、中划线"

    command_name = normalize_command_name(command_name)
    if command_name == "":
        return None, "指令名称不能为空"

    return {
        "skill_name": skill_name,
        "command_name": command_name,
        "description": description,
    }, ""


def write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_run_file_name(skill_name):
    return f"{skill_name}.py"


def build_skill_json(skill_name, command_name, description):
    data = {
        "num_1": {
            "command": command_name,
            "explain": description,
            "run_file": build_run_file_name(skill_name),
        }
    }
    return json.dumps(data, ensure_ascii=False, indent=4) + "\n"


def build_skill_create_text(skill_name, command_name, description):
    run_file_name = build_run_file_name(skill_name)
    lines = [
        "实现以下要求：",
        "1.运行文件，输入：",
        f"    {command_name} <参数>",
        "2.输出：",
        "    <输出内容>",
        "3.功能说明：",
        f"    {description}",
        "4.示例：",
        f"    {command_name} 示例参数",
        "",
        "请根据技能目标补全入参解析、输出格式和具体实现。",
        f"主运行文件：system\\skills\\{skill_name}\\skill_run\\{run_file_name}",
        f"配置文件：system\\skills\\{skill_name}\\skill_run\\config.json",
    ]
    return "\n".join(lines) + "\n"


def build_skill_use_text(command_name, description):
    lines = [
        "指令1：",
        f"    指令内容：{command_name} <参数>",
        "    示例1：",
        f"        {command_name} 示例参数",
        "    注意：",
        f"        1.技能目标：{description}",
        "        2.当前为新生成的skill骨架，请按实际需求补全参数说明和实现",
    ]
    return "\n".join(lines) + "\n"


def build_runtime_script(skill_name, command_name, description):
    lines = [
        "import json",
        "import sys",
        "from pathlib import Path",
        "",
        "",
        'CONFIG_PATH = Path(__file__).resolve().parent / "config.json"',
        f'USAGE_TEXT = "用法：{command_name} <参数>"',
        'payload = " ".join(sys.argv[1:]).strip()',
        "",
        "",
        "def set_stream_utf8(stream):",
        '    reconfigure = getattr(stream, "reconfigure", None)',
        "    if callable(reconfigure):",
        '        reconfigure(encoding="utf-8")',
        "",
        "",
        "set_stream_utf8(sys.stdout)",
        "set_stream_utf8(sys.stderr)",
        "set_stream_utf8(sys.stdin)",
        "",
        "",
        "def load_json(path):",
        '    with path.open("r", encoding="utf-8") as file:',
        "        return json.load(file)",
        "",
        "",
        "def read_payload():",
        '    if payload != "":',
        "        return payload",
        '    return sys.stdin.buffer.readline().decode("utf-8").strip()',
        "",
        "",
        "def parse_arguments(command):",
        "    command_text = command.strip()",
        f'    prefix = "{command_name}"',
        '    if command_text == "" or command_text.startswith(prefix) is False:',
        '        return "", USAGE_TEXT',
        "    args_text = command_text[len(prefix) :].strip()",
        '    if args_text == "":',
        '        return "", USAGE_TEXT',
        '    return args_text, ""',
        "",
        "",
        "def load_config():",
        "    if CONFIG_PATH.exists() is False:",
        '        return {}, ""',
        "    try:",
        "        return load_json(CONFIG_PATH), \"\"",
        "    except json.JSONDecodeError:",
        '        return {}, "配置文件格式错误，请检查 config.json"',
        "    except OSError as error:",
        '        return {}, f"读取配置文件失败：{error}"',
        "",
        "",
        "def main():",
        "    command = read_payload()",
        "    args_text, parse_error = parse_arguments(command)",
        '    if parse_error != "":',
        "        print(parse_error)",
        "        return",
        "",
        "    _, config_error = load_config()",
        '    if config_error != "":',
        "        print(config_error)",
        "        return",
        "",
        f'    print("技能名称：{skill_name}")',
        f'    print("指令：{command_name}")',
        f'    print("功能说明：{description}")',
        '    print(f"输入参数：{args_text}")',
        '    print("请编辑当前脚本，实现具体逻辑。")',
        "",
        "",
        'if __name__ == "__main__":',
        "    main()",
        "",
    ]
    return "\n".join(lines)


def create_skill_files(spec):
    skill_name = spec["skill_name"]
    command_name = spec["command_name"]
    description = spec["description"]
    run_file_name = build_run_file_name(skill_name)

    skill_dir = SKILLS_DIR / skill_name
    if skill_dir.exists():
        return f"skill已存在：system\\skills\\{skill_name}"

    write_text(skill_dir / "skill.json", build_skill_json(skill_name, command_name, description))
    write_text(
        skill_dir / "skill_create.txt",
        build_skill_create_text(skill_name, command_name, description),
    )
    write_text(skill_dir / "skill_use.txt", build_skill_use_text(command_name, description))
    write_text(skill_dir / "skill_run" / "config.json", "{}\n")
    write_text(
        skill_dir / "skill_run" / run_file_name,
        build_runtime_script(skill_name, command_name, description),
    )

    lines = [
        "创建成功",
        f"skill目录：system\\skills\\{skill_name}",
        f"指令名称：{command_name}",
        f"运行文件：system\\skills\\{skill_name}\\skill_run\\{run_file_name}",
    ]
    return "\n".join(lines)


def main():
    command = read_payload()
    spec, error_text = parse_command(command)
    if error_text != "":
        print(error_text)
        return
    print(create_skill_files(spec))


if __name__ == "__main__":
    main()
