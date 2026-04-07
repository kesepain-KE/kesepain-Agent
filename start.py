import json
import shutil
import subprocess
import sys
from pathlib import Path


# start.py 只负责“启动期准备”：
# 1. 用 system/start 下的模板覆盖初始化 core/temp。
# 2. 选择用户并将 users/<name>/config.json 合并进临时 cache。
# 3. 确保该用户的历史文件存在。
# 4. 把控制权交给 core/date_analyze.py。
root_dir = Path(__file__).resolve().parent

# 启动模板文件：
# - cache.json 是每次启动都要重建的运行时共享状态模板。
# - task.json 是任务插件的初始状态模板。
# - history.json 是新用户历史文件的空白模板。
system_cache_path = root_dir / "system" / "start" / "cache.json"
system_task_path = root_dir / "system" / "start" / "task.json"
history_template_path = root_dir / "system" / "start" / "history.json"

# 启动临时文件：
# - 这两个文件位于 core/temp，主链运行期都会从这里读状态。
# - start 阶段采用“模板覆盖初始化”，避免沿用上次残留状态。
temp_cache_path = root_dir / "core" / "temp" / "cache.json"
temp_task_path = root_dir / "core" / "temp" / "task.json"

# 用户目录：每个一级子目录就是一个可选用户。
users_dir = root_dir / "users"


def _safe_reconfigure_output(stream):
    """尽量将输出流编码切换为 UTF-8。

    维护说明：
    - 该函数用于减少控制台中文乱码风险。
    - 并非所有流对象都支持 reconfigure，因此先做能力探测。
    - 失败时静默返回，避免影响主启动流程。
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None or not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_json(path):
    """以 UTF-8 读取 JSON 文件并返回解析后的对象。"""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    """以 UTF-8 保存 JSON 文件。

    维护说明：
    - ensure_ascii=False 用于保留中文可读性。
    - indent=4 便于人工排查与版本比对。
    """
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def copy_template_file(source_path, target_path):
    """将启动模板复制到工作路径。

    维护说明：
    - start 流程依赖“模板 -> 临时副本”的覆盖式初始化。
    - 目标目录不存在时会自动创建。
    """
    if not source_path.exists():
        raise SystemExit(f"缺少启动模板文件：{source_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target_path)


def apply_config_overrides(template_data, config_data):
    """递归将用户配置覆盖到缓存模板。

    规则说明：
    - 仅覆盖模板中已存在的键；额外键会被忽略。
    - 若同名键双方均为 dict，则递归合并。
    - 否则直接赋值覆盖。

    约定提醒：
    - 顶层字段 tool_use 与 tool_use_allow 都会映射到 tool_log.tool_use。
    - memory.user_memory_path 会映射到 memory.memory_path。
    """
    for key, value in config_data.items():
        # 用户配置中的 tool_use / tool_use_allow 都映射到 tool_log.tool_use
        if key in ("tool_use", "tool_use_allow") and "tool_log" in template_data:
            template_data["tool_log"]["tool_use"] = value
            continue
        # 用户配置里的历史文件名字段与运行时 cache 的字段名不同，这里做一次桥接。
        if key == "user_memory_path" and "memory_path" in template_data:
            template_data["memory_path"] = value
            continue
        if key not in template_data:
            continue
        if isinstance(value, dict) and isinstance(template_data[key], dict):
            apply_config_overrides(template_data[key], value)
        else:
            template_data[key] = value


def get_user_names():
    """读取 users 目录下的用户文件夹名称并按字典序返回。"""
    if not users_dir.exists():
        raise SystemExit(f"用户目录不存在：{users_dir}")
    return sorted([item.name for item in users_dir.iterdir() if item.is_dir()])


def select_user(user_names):
    """交互式选择用户。

    输入约定：
    - 支持 1-based 序号。
    - 支持直接输入用户名。
    """
    if not user_names:
        raise SystemExit("users 目录下没有可用的用户文件夹")

    for index, user_name in enumerate(user_names, start=1):
        print(f"{index}.{user_name}")

    print("请选择用户文件：", end="")
    # 支持输入序号(1-based)或用户名
    selected_user = input().strip()
    if selected_user.isdigit():
        selected_index = int(selected_user) - 1
        if 0 <= selected_index < len(user_names):
            return user_names[selected_index]
        raise SystemExit("用户序号不存在")

    if selected_user in user_names:
        return selected_user

    raise SystemExit("用户不存在")


def ensure_history_file(user_name, cache_data):
    """确保用户历史对话文件存在，不存在则由模板复制创建。

    维护说明：
    - 历史文件定位统一依赖 cache_data["memory"]["memory_path"]。
    - cache_data 来自模板与用户配置合并结果，作为单一事实来源。
    """
    history_file_name = cache_data["memory"]["memory_path"]
    history_path = (
        users_dir
        / user_name
        / "chat_history"
        / history_file_name
    )
    if history_path.exists():
        return
    history_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(history_template_path, history_path)


def prepare_start_files():
    """准备 start 阶段所需的临时工作文件。

    维护说明：
    - task.json 也在这里一并重置，原因是任务插件依赖 core/temp/task.json
      作为当前任务链状态文件。
    - 这样做可以保证每次新启动都是干净会话。
    """
    copy_template_file(system_cache_path, temp_cache_path)
    copy_template_file(system_task_path, temp_task_path)


def get_console_run_kwargs():
    """收集可安全透传给子进程的控制台流。

    维护说明：
    - stdin 透传用于保证后续多层子进程仍能继续读终端输入。
    - stderr 透传用于让提示和错误继续落在当前控制台。
    - 某些宿主环境下流对象没有有效 fileno，这里要容错跳过。
    """
    kwargs = {}
    for name, stream in (("stdin", sys.stdin), ("stderr", sys.stderr)):
        try:
            stream.fileno()
        except (AttributeError, OSError, ValueError):
            continue
        kwargs[name] = stream
    return kwargs


def main():
    """start 模式入口。

    主流程：
    1. 从 system/start 复制模板到 core/temp。
    2. 选择用户并加载对应配置。
    3. 将用户配置覆盖到临时 cache。
    4. 准备历史对话文件。
    5. 调用 date_analyze.py 并透传退出码。
    """

    # 阶段 1：准备启动临时文件（覆盖式初始化）
    prepare_start_files()

    # 阶段 2：选择用户并加载配置
    user_names = get_user_names()
    user_name = select_user(user_names)

    user_config_path = users_dir / user_name / "config.json"
    user_config = load_json(user_config_path)
    # 用户目录名本身就是主链使用的 name；这里统一回填进运行时配置。
    user_config["name"] = user_name

    # 阶段 3：将用户配置覆盖到缓存模板
    temp_cache = load_json(temp_cache_path)
    apply_config_overrides(temp_cache, user_config)
    save_json(temp_cache_path, temp_cache)

    # 阶段 4：准备历史对话文件
    ensure_history_file(user_name, temp_cache)

    # 阶段 5：启动核心调度（type:start）
    result = subprocess.run(
        [sys.executable, str(root_dir / "core" / "date_analyze.py"), "type:start"],
        **get_console_run_kwargs(),
    )
    # 启动脚本本身不吞退出码，保持外层调用者能感知主链退出结果。
    raise SystemExit(result.returncode)


# 尽量在启动最早阶段切成 UTF-8 输出，减少 Windows 终端中文乱码。
_safe_reconfigure_output(sys.stdout)
_safe_reconfigure_output(sys.stderr)


if __name__ == "__main__":
    main()
