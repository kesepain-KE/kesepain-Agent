import json
import re
import shutil
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]
TASK_TEMPLATE_PATH = ROOT_DIR / "system" / "start" / "task.json"
TASK_DATA_PATH = ROOT_DIR / "core" / "temp" / "task.json"
CREATE_COMMAND = "/任务创建"
QUERY_COMMAND = "/任务进度查看"
FINISH_COMMAND = "/任务标注"
LEGACY_QUERY_COMMAND = "/任务查询"
LEGACY_FINISH_COMMAND = "/任务完成"
MAX_TASK_STEPS = 15
NUMBERED_STEP_PATTERN = re.compile(r"(\d+)\|")
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


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def reset_task_file():
    TASK_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TASK_TEMPLATE_PATH, TASK_DATA_PATH)


def get_usage_text():
    return "\n".join(
        [
            f"用法：{CREATE_COMMAND} <任务描述>|<任务步骤1>|<任务步骤2>|...",
            f"用法：{QUERY_COMMAND}",
            f"用法：{FINISH_COMMAND} <任务序号>",
        ]
    )


def is_query_command(command_text):
    return command_text in (QUERY_COMMAND, LEGACY_QUERY_COMMAND)


def get_finish_command_prefix(command_text):
    if command_text.startswith(FINISH_COMMAND):
        return FINISH_COMMAND
    if command_text.startswith(LEGACY_FINISH_COMMAND):
        return LEGACY_FINISH_COMMAND
    return ""


def get_task_step_keys(task_data):
    task_date = task_data.get("task_date", {})
    keys = []
    for key, value in task_date.items():
        if key.startswith("step_") is False:
            continue
        if isinstance(value, dict) is False:
            continue
        if str(value.get("measure", "")).strip() == "":
            continue
        try:
            index = int(key.split("_")[1])
        except (IndexError, ValueError):
            continue
        keys.append((index, key))
    keys.sort(key=lambda item: item[0])
    return keys


def get_task_steps(task_data):
    steps = []
    for index, key in get_task_step_keys(task_data):
        item = task_data["task_date"][key]
        steps.append(
            {
                "index": index,
                "key": key,
                "measure": str(item.get("measure", "")).strip(),
                "execute": bool(item.get("execute", False)),
            }
        )
    return steps


def build_steps_from_segments(segments):
    description = segments[0].strip()
    if description == "":
        return None, None, "任务描述不能为空"

    step_texts = [segment.strip() for segment in segments[1:] if segment.strip() != ""]
    if len(step_texts) == 0:
        return None, None, "任务步骤不能为空，格式为：<任务描述>|<任务步骤1>|<任务步骤2>"
    if len(step_texts) > MAX_TASK_STEPS:
        return None, None, f"任务节点最多创建{MAX_TASK_STEPS}个"

    steps = [(index, step_text) for index, step_text in enumerate(step_texts, start=1)]
    return description, steps, ""


def build_steps_from_numbered_content(content):
    matches = list(NUMBERED_STEP_PATTERN.finditer(content))
    if len(matches) == 0:
        return None, None, "任务步骤不能为空，格式为：<任务描述>|<任务步骤1>|<任务步骤2>"

    description = content[: matches[0].start()].strip()
    if description == "":
        return None, None, "任务描述不能为空"

    steps = []
    for current_index, match in enumerate(matches):
        step_number = int(match.group(1))
        step_start = match.end()
        if current_index + 1 < len(matches):
            step_end = matches[current_index + 1].start()
        else:
            step_end = len(content)
        step_measure = content[step_start:step_end].strip()
        if step_measure == "":
            return None, None, f"任务节点{step_number}内容不能为空"
        steps.append((step_number, step_measure))

    if len(steps) > MAX_TASK_STEPS:
        return None, None, f"任务节点最多创建{MAX_TASK_STEPS}个"

    expected_numbers = list(range(1, len(steps) + 1))
    actual_numbers = [step_number for step_number, _ in steps]
    if actual_numbers != expected_numbers:
        return None, None, "任务流程编号必须从1开始连续递增"

    return description, steps, ""


def parse_create_command(command):
    command_text = command.strip()
    if command_text.startswith(CREATE_COMMAND) is False:
        return None, None, get_usage_text()

    content = command_text[len(CREATE_COMMAND) :].strip()
    if content == "":
        return None, None, f"用法：{CREATE_COMMAND} <任务描述>|<任务步骤1>|<任务步骤2>|..."

    segments = [segment.strip() for segment in content.split("|")]
    if len(segments) >= 2 and NUMBERED_STEP_PATTERN.search(content) is None:
        return build_steps_from_segments(segments)
    return build_steps_from_numbered_content(content)


def parse_finish_command(command):
    command_text = command.strip()
    prefix = get_finish_command_prefix(command_text)
    if prefix == "":
        return None, get_usage_text()

    remainder = command_text[len(prefix) :].strip()
    if remainder == "":
        return None, f"用法：{FINISH_COMMAND} <任务序号>"

    parts = remainder.split()
    if len(parts) != 1 or parts[0].isdigit() is False:
        return None, f"用法：{FINISH_COMMAND} <任务序号>"
    return int(parts[0]), ""


def build_query_output(task_data):
    description = str(task_data.get("task_defination", "")).strip()
    steps = get_task_steps(task_data)
    if description == "" or len(steps) == 0:
        return "当前没有已创建任务"

    lines = [f"任务:{description}"]
    for step in steps:
        status = "已完成" if step["execute"] else "未完成"
        lines.append(f"{step['index']}|{step['measure']}|{status}")
    return "\n".join(lines)


def handle_create(command):
    description, steps, error_text = parse_create_command(command)
    if error_text != "":
        return error_text
    if steps is None:
        return "任务步骤不能为空，格式为：<任务描述>|<任务步骤1>|<任务步骤2>"

    reset_task_file()
    task_data = load_json(TASK_DATA_PATH)
    task_data["task_defination"] = description
    task_data["task_date"] = {}
    for step_number, step_measure in steps:
        task_data["task_date"][f"step_{step_number}"] = {
            "measure": step_measure,
            "execute": False,
        }
    save_json(TASK_DATA_PATH, task_data)
    return "已创建任务"


def handle_query(command):
    command_text = command.strip()
    if is_query_command(command_text) is False:
        return f"用法：{QUERY_COMMAND}"

    task_data = load_json(TASK_DATA_PATH)
    return build_query_output(task_data)


def handle_finish(command):
    step_number, error_text = parse_finish_command(command)
    if error_text != "":
        return error_text

    task_data = load_json(TASK_DATA_PATH)
    steps = get_task_steps(task_data)
    if len(steps) == 0 or str(task_data.get("task_defination", "")).strip() == "":
        return "当前没有已创建任务"

    target_step = None
    for step in steps:
        if step["index"] == step_number:
            target_step = step
            break

    if target_step is None:
        return f"未找到任务节点：{step_number}"
    if target_step["execute"]:
        return f"任务节点已完成：{step_number}|{target_step['measure']}"

    task_data["task_date"][target_step["key"]]["execute"] = True
    save_json(TASK_DATA_PATH, task_data)

    updated_steps = get_task_steps(task_data)
    remaining_steps = [step for step in updated_steps if step["execute"] is False]
    lines = [f"已标记指定任务节点为完成：{step_number}|{target_step['measure']}", "剩余任务："]
    if len(remaining_steps) == 0:
        lines.append("无剩余任务")
    else:
        for step in remaining_steps:
            lines.append(f"{step['index']}|{step['measure']}")
    return "\n".join(lines)


def main():
    command = read_payload()
    if command == "":
        print(get_usage_text())
        return

    if command.startswith(CREATE_COMMAND):
        print(handle_create(command))
        return

    if is_query_command(command.strip()):
        print(handle_query(command))
        return

    if get_finish_command_prefix(command.strip()) != "":
        print(handle_finish(command))
        return

    print(get_usage_text())


if __name__ == "__main__":
    main()
