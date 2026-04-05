import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]
SEARCH_COMMAND = "/文件搜索"
TREE_COMMAND = "/框架查询"
USAGE_TEXT = "\n".join(
    [
        "用法：/文件搜索 <关键词>",
        "用法：/框架查询 <工作区相对文件地址>",
    ]
)
SKIP_DIR_NAMES = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
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


def normalize_relative_path(path):
    return str(path.relative_to(ROOT_DIR)).replace("/", "\\")


def parse_command(command):
    command_text = command.strip()
    if command_text == "":
        return "", "", USAGE_TEXT

    if command_text.startswith(SEARCH_COMMAND):
        argument = command_text[len(SEARCH_COMMAND) :].strip()
        if argument == "":
            return "", "", f"用法：{SEARCH_COMMAND} <关键词>"
        return "search", argument, ""

    if command_text.startswith(TREE_COMMAND):
        argument = command_text[len(TREE_COMMAND) :].strip()
        if argument == "":
            return "", "", f"用法：{TREE_COMMAND} <工作区相对文件地址>"
        return "tree", argument, ""

    return "", "", USAGE_TEXT


def search_files(keyword):
    matches = []
    normalized_keyword = keyword.casefold()
    for current_root, dir_names, file_names in os.walk(ROOT_DIR):
        dir_names[:] = sorted(
            [name for name in dir_names if name not in SKIP_DIR_NAMES],
            key=lambda item: item.casefold(),
        )
        for file_name in sorted(file_names, key=lambda item: item.casefold()):
            file_path = Path(current_root) / file_name
            relative_path = normalize_relative_path(file_path)
            search_text = f"{file_name} {relative_path}".casefold()
            if normalized_keyword in search_text:
                matches.append(relative_path)
    return matches


def resolve_workspace_path(relative_path_text):
    input_path = Path(relative_path_text)
    if input_path.is_absolute():
        return None, "无法查询工作区外文件"

    target_path = (ROOT_DIR / input_path).resolve(strict=False)
    try:
        target_path.relative_to(ROOT_DIR)
    except ValueError:
        return None, "无法查询工作区外文件"

    if target_path.exists() is False:
        return None, "目标路径不存在"
    return target_path, ""


def iter_tree_entries(path):
    return sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.casefold()))


def build_tree_lines(path):
    lines = [path.name]
    if path.is_file():
        return lines

    def walk_tree(current_path, depth):
        prefix = "|   " * depth
        for item in iter_tree_entries(current_path):
            lines.append(f"{prefix}|-{item.name}")
            if item.is_dir():
                walk_tree(item, depth + 1)

    walk_tree(path, 1)
    return lines


def main():
    command = read_payload()
    action, argument, error_text = parse_command(command)
    if error_text != "":
        print(error_text)
        return

    if action == "search":
        matches = search_files(argument)
        if len(matches) == 0:
            print("未找到匹配文件")
            return
        print("\n".join(matches))
        return

    if action == "tree":
        target_path, path_error = resolve_workspace_path(argument)
        if path_error != "":
            print(path_error)
            return
        print("\n".join(build_tree_lines(target_path)))
        return

    print(USAGE_TEXT)


if __name__ == "__main__":
    main()
