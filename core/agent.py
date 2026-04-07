import json
import subprocess
import sys
from pathlib import Path


# agent.py 是“主链分发口”：
# - 先检查当前输入是否命中 chat_control 控制命令。
# - 命中时在本地完成 /帮助 /清除 /退出 这类对话控制。
# - 未命中时把控制权交给 provider/provider.py，进入模型决策链。
root_dir = Path(__file__).resolve().parent.parent
config_path = Path(__file__).resolve().parent / "config.json"
cache_path = Path(__file__).resolve().parent / "temp" / "cache.json"
chat_control_json_path = root_dir / "system" / "plugins" / "chat_control" / "command.json"
chat_control_run_path = root_dir / "system" / "plugins" / "chat_control" / "run" / "core_chat.py"
payload = sys.argv[1]


def has_usable_fileno(stream):
    """判断一个标准流对象是否能安全地提供 fileno。"""
    try:
        fileno_method = stream.fileno
    except AttributeError:
        return False

    if not callable(fileno_method):
        return False
    try:
        fileno_method()
    except (OSError, ValueError):
        return False
    return True


def get_console_run_kwargs():
    """透传当前控制台能力给子进程。

    维护说明：
    - stdin 透传用于保证更深层的 chat.py 仍能继续读取终端输入。
    - stderr 透传用于让提示和错误继续显示在当前控制台。
    - 某些宿主环境没有有效 fileno，这里要做兼容探测。
    """
    kwargs = {}
    for name, stream in (("stdin", sys.stdin), ("stderr", sys.stderr)):
        if has_usable_fileno(stream) is False:
            continue
        kwargs[name] = stream
    return kwargs


def load_json(path):
    """以 UTF-8 读取 JSON 文件。"""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    """以 UTF-8 保存 JSON 文件。"""
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def get_command_order_key(key):
    """从 command_1 / command_2 这类键里提取排序号。"""
    if key.startswith("command_"):
        suffix = key[len("command_") :]
        if suffix.isdigit():
            return int(suffix)
    return 10**9


def get_chat_control_commands():
    """读取 chat_control 插件注册的控制命令列表。"""
    command_data = load_json(chat_control_json_path)
    commands = []
    for key in sorted(command_data.keys(), key=get_command_order_key):
        item = command_data[key]
        commands.append(item["command"])
    return commands


def parse_chat_control_result(text):
    """解析 core_chat.py 的轻量返回协议。

    协议约定：
    - 第一行是 type:continue 或 type:exit。
    - 其余行拼接后为 output:<内容>。
    - 空输出默认按 continue 处理，避免异常中断当前对话。
    """
    lines = text.splitlines()
    if len(lines) == 0:
        return "type:continue", ""

    result_type = lines[0]
    output_text = "\n".join(lines[1:])
    if output_text.startswith("output:"):
        output_text = output_text[len("output:") :]
    output = output_text
    return result_type, output


def run_chat_control():
    """尝试执行 chat_control 控制命令。

    返回值语义：
    - True：当前输入已被 chat_control 消费，agent 不应再进入 provider。
    - False：当前输入不是控制命令，应继续进入模型主链。

    continue 分支的后续动作：
    - chat_control 输出帮助/清除结果后，需要立即继续拿下一轮用户输入；
    - 因此这里会串联 chat.py -> memory.py -> agent.py(type:continue)。
    """
    cache_data = load_json(cache_path)
    user_input = cache_data["user_input"]
    if user_input not in get_chat_control_commands():
        return False

    # 控制命令本身是本地逻辑，不需要经过 provider 和模型。
    chat_control_output = subprocess.run(
        [sys.executable, str(chat_control_run_path), user_input],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        **get_console_run_kwargs(),
    ).stdout.strip()
    result_type, output = parse_chat_control_result(chat_control_output)
    print(output)

    if result_type == "type:continue":
        # /帮助、/清除 这类命令执行后，对话并不结束，要继续收下一轮输入。
        chat_output = subprocess.run(
            [sys.executable, str(root_dir / "core" / "chat.py"), "type:continue"],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            **get_console_run_kwargs(),
        ).stdout.strip()
        if chat_output == "type:runed":
            memory_output = subprocess.run(
                [sys.executable, str(root_dir / "core" / "memory.py"), "type:read"],
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                **get_console_run_kwargs(),
            ).stdout.strip()
            if memory_output == "type:runed":
                subprocess.run(
                    [sys.executable, str(root_dir / "core" / "agent.py"), "type:continue"],
                    **get_console_run_kwargs(),
                )
    return True


def apply_start_config_to_cache():
    """把 core/config.json 中的启动期运行参数写入临时 cache。

    维护说明：
    - 这些字段每次启动都要覆盖一次，保证本轮会话拿到最新配置。
    - 这里只处理 start 阶段依赖的核心数值，不负责用户级配置合并。
    """
    config_data = load_json(config_path)
    cache_data = load_json(cache_path)
    cache_data["history"]["history_max"] = config_data["history_max"]
    cache_data["history"]["history_zip_to_num"] = config_data["history_zip_to_num"]
    cache_data["tool_log"]["single_chat_tools_use_num"] = config_data["single_chat_tools_use_num"]
    cache_data["tool_log"]["tool_log_max"] = config_data["tool_log_max"]
    save_json(cache_path, cache_data)


if payload == "type:start":
    # start 阶段先把全局配置写入 cache，再决定是走控制命令还是进入 provider。
    apply_start_config_to_cache()
    if run_chat_control() is False:
        subprocess.run(
            [sys.executable, str(root_dir / "provider" / "provider.py"), "type:start"],
            **get_console_run_kwargs(),
        )


if payload == "type:continue":
    # continue 阶段仍然调用 provider 的 type:start：
    # provider 会直接读取 cache 中最新的 user_input / history_date / tool_log 继续决策，
    # 因此这里不需要额外定义一个 provider type:continue。
    if run_chat_control() is False:
        subprocess.run(
            [sys.executable, str(root_dir / "provider" / "provider.py"), "type:start"],
            **get_console_run_kwargs(),
        )
