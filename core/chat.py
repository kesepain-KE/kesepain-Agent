import json
import os
import sys
from pathlib import Path


# chat.py 只负责“拿一轮用户输入并写入 cache”：
# - 不负责历史拼装。
# - 不负责 chat_control 判断。
# - 不负责模型调用。
# 它的输出协议也很轻，只返回 type:runed / type:exit 给上游调度器。
def load_payload():
    """读取入口模式。

    约定：
    - 只接受 type:start / type:continue。
    - 缺省时返回空字符串，使脚本保持无副作用退出。
    """
    if len(sys.argv) > 1:
        return sys.argv[1]
    return ""


payload = load_payload()
CACHE_PATH = Path(__file__).resolve().parent / "temp" / "cache.json"


def load_json(path):
    """以 UTF-8 读取运行时 cache。"""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    """以 UTF-8 保存运行时 cache。"""
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def read_user_text():
    """读取一行用户输入。

    返回值：
    - (text, True)：成功拿到输入。
    - ("", False)：输入流结束，当前对话应退出。

    维护说明：
    - 默认走标准 input()。
    - Windows 下多层子进程链可能拿到失效的 stdin 句柄，因此在 EOFError
      时回退到 CONIN$ 直接读取控制台。
    """
    try:
        return input().strip(), True
    except EOFError:
        # Windows 下多层子进程链里，继承的 stdin 句柄可能失效；直接回退到控制台输入。
        if os.name == "nt":
            try:
                with open("CONIN$", "r", encoding="utf-8") as console_input:
                    user_input = console_input.readline()
            except OSError:
                user_input = ""
            if user_input != "":
                return user_input.rstrip("\r\n"), True
        print("输入流结束，已退出当前对话", file=sys.stderr)
        return "", False
    except KeyboardInterrupt:
        print("输入流结束，已退出当前对话", file=sys.stderr)
        return "", False


def write_user_input(prompt_text):
    """向终端提示并把输入写入 cache。

    额外动作：
    - 每次进入新的一轮用户输入，都把 tool_log.tool_single_count 归零。
    - 这样本轮工具调用计数会从 0 开始重新统计。
    """
    # 提示信息走 stderr，避免污染 stdout 返回协议。
    print(prompt_text, end="", file=sys.stderr, flush=True)
    user_input, ok = read_user_text()
    if ok is False:
        return False
    cache_data = load_json(CACHE_PATH)
    tool_log = cache_data.get("tool_log")
    if isinstance(tool_log, dict) is False:
        tool_log = {}
    # 单轮工具调用次数统计以“用户新输入”为边界；新一轮开始时必须清零。
    tool_log["tool_single_count"] = 0
    cache_data["tool_log"] = tool_log
    cache_data["user_input"] = user_input
    save_json(CACHE_PATH, cache_data)
    return True


if payload == "type:start":
    # 首轮输入提示使用“请输入文本：”。
    if write_user_input("请输入文本："):
        print("type:runed")
    else:
        print("type:exit")


if payload == "type:continue":
    # 续聊输入提示使用“请继续输入文本：”。
    if write_user_input("请继续输入文本："):
        print("type:runed")
    else:
        print("type:exit")
