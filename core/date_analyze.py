import subprocess
import sys
from pathlib import Path


# date_analyze.py 是主链里的“顺序调度器”：
# - start 模式负责拿首轮输入、读取历史、再交给 agent。
# - continue 模式负责先把上一轮结果写回历史，再拿下一轮输入、刷新历史、再交给 agent。
# 这一层本身不做业务判断，只负责串联 chat / memory / agent 三个模块。
ROOT_DIR = Path(__file__).resolve().parent.parent


def load_payload():
    """读取入口模式。

    约定：
    - 只接受单个位置参数，如 type:start / type:continue。
    - 缺省时返回空字符串，让文件保持“无副作用退出”。
    """
    if len(sys.argv) > 1:
        return sys.argv[1]
    return ""


payload = load_payload()


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
    """透传当前控制台输入输出能力给子进程。

    维护说明：
    - stdin 透传是为了让更深层的 chat.py 仍能继续从当前终端读输入。
    - stderr 透传是为了让提示信息和错误继续显示在当前控制台。
    - 某些宿主环境没有有效 fileno，这里要做兼容探测。
    """
    kwargs = {}
    for name, stream in (("stdin", sys.stdin), ("stderr", sys.stderr)):
        if has_usable_fileno(stream) is False:
            continue
        kwargs[name] = stream
    return kwargs


def run_and_read_output(script_name, command):
    """运行一个需要返回简短状态码的核心脚本。

    使用场景：
    - chat.py / memory.py 这类脚本会把真正的人机提示写到终端，
      同时用 stdout 返回 type:runed / type:exit 这种轻量状态。
    - 这里统一捕获 stdout，供 date_analyze 做下一步分支判断。
    """
    result = subprocess.run(
        [sys.executable, str(ROOT_DIR / "core" / script_name), command],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        **get_console_run_kwargs(),
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def run_without_capture(script_name, command):
    """运行一个需要直接接管当前终端输出的脚本。

    当前只用于 agent.py：
    - agent 会继续往下驱动 provider / action / chat_control；
    - 这些链路的输出应直接落到当前控制台，而不是被 date_analyze 吞掉。
    """
    subprocess.run(
        [sys.executable, str(ROOT_DIR / "core" / script_name), command],
        **get_console_run_kwargs(),
    )


def run_start():
    """首轮启动链路。

    顺序固定为：
    1. chat.py type:start 读取用户首句输入；
    2. memory.py type:read 把历史窗口写入 cache.history_date；
    3. agent.py type:start 进入模型决策与工具调用主链。
    """
    chat_output = run_and_read_output("chat.py", "type:start")
    if chat_output != "type:runed":
        return

    memory_output = run_and_read_output("memory.py", "type:read")
    if memory_output != "type:runed":
        return

    run_without_capture("agent.py", "type:start")


def run_continue():
    """续聊链路。

    顺序固定为：
    1. memory.py type:continue 先把上一轮 user_input / LLM_output 写回历史；
    2. chat.py type:continue 再读取下一轮用户输入；
    3. memory.py type:read 刷新 cache.history_date；
    4. agent.py type:continue 进入下一轮决策。

    之所以先 continue 再 read，是因为本轮模型回复已经生成，
    需要先把“上一轮完整对话”落盘，后续读取到的历史窗口才是最新的。
    """
    memory_continue_output = run_and_read_output("memory.py", "type:continue")
    if memory_continue_output != "type:runed":
        return

    chat_output = run_and_read_output("chat.py", "type:continue")
    if chat_output != "type:runed":
        return

    memory_read_output = run_and_read_output("memory.py", "type:read")
    if memory_read_output != "type:runed":
        return

    run_without_capture("agent.py", "type:continue")


if payload == "type:start":
    run_start()


if payload == "type:continue":
    run_continue()
