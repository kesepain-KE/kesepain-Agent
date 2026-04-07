import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]
FIND_COMMAND = "/文件查找"
TREE_COMMAND = "/文件夹内部框架查看"
READ_COMMAND = "/文件读取"
LEGACY_FIND_COMMAND = "/文件搜索"
LEGACY_TREE_COMMAND = "/框架查询"
SKIP_DIR_NAMES = {".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"}
MAX_FIND_RESULTS = 50
MAX_TREE_LINES = 200
MAX_READ_CHARS = 12000
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


def get_usage_text():
    return "\n".join(
        [
            f"用法：{FIND_COMMAND} <具体的文件名，支持文件夹>",
            f"用法：{TREE_COMMAND} <具体的文件名>",
            f"用法：{READ_COMMAND} <相对路径>",
        ]
    )


def normalize_relative_text(text):
    cleaned = str(text).strip().strip('"').strip("'").replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.strip("/")


def is_within_root(path):
    try:
        path.relative_to(ROOT_DIR)
        return True
    except ValueError:
        return False


def to_relative_path(path):
    return path.relative_to(ROOT_DIR).as_posix()


def should_skip_dir(path):
    return path.name in SKIP_DIR_NAMES


def iter_workspace_paths():
    stack = [ROOT_DIR]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        except OSError:
            continue

        next_dirs = []
        for child in children:
            if is_within_root(child) is False:
                continue
            yield child
            if child.is_dir() and should_skip_dir(child) is False:
                next_dirs.append(child)
        stack.extend(reversed(next_dirs))


def resolve_existing_path(raw_text):
    relative_text = normalize_relative_text(raw_text)
    if relative_text == "":
        return None, "路径不能为空"

    candidate = (ROOT_DIR / relative_text).resolve()
    if is_within_root(candidate) is False:
        return None, f"路径超出工作区：{relative_text}"
    if candidate.exists():
        return candidate, ""
    return None, ""


def find_paths_by_name(query):
    query_text = query.strip().lower()
    results = []
    if query_text == "":
        return results

    for path in iter_workspace_paths():
        if query_text in path.name.lower():
            results.append(path)
        if len(results) >= MAX_FIND_RESULTS:
            break
    return results


def parse_command_argument(command_text, command_prefixes, usage_text):
    for prefix in command_prefixes:
        if command_text.startswith(prefix):
            argument = command_text[len(prefix) :].strip()
            if argument == "":
                return "", usage_text
            return argument, ""
    return "", usage_text


def build_find_output(matches):
    lines = ["找到以下匹配项："]
    for match in matches:
        item_type = "[文件夹]" if match.is_dir() else "[文件]"
        lines.append(f"{item_type} {to_relative_path(match)}")
    if len(matches) >= MAX_FIND_RESULTS:
        lines.append(f"仅展示前{MAX_FIND_RESULTS}项结果")
    return "\n".join(lines)


def handle_find(command):
    query, error_text = parse_command_argument(
        command.strip(),
        (FIND_COMMAND, LEGACY_FIND_COMMAND),
        f"用法：{FIND_COMMAND} <具体的文件名，支持文件夹>",
    )
    if error_text != "":
        return error_text

    matches = find_paths_by_name(query)
    if len(matches) == 0:
        return f"未找到匹配项：{query}"
    return build_find_output(matches)


def resolve_tree_target(raw_text):
    direct_path, error_text = resolve_existing_path(raw_text)
    if error_text != "":
        return None, error_text
    if direct_path is not None:
        return direct_path, ""

    matches = find_paths_by_name(raw_text)
    if len(matches) == 0:
        return None, f"未找到匹配项：{raw_text}"
    if len(matches) > 1:
        lines = ["找到多个匹配项，请使用更精确的相对路径："]
        for match in matches[:10]:
            item_type = "[文件夹]" if match.is_dir() else "[文件]"
            lines.append(f"{item_type} {to_relative_path(match)}")
        return None, "\n".join(lines)
    return matches[0], ""


def append_tree_lines(directory, level, lines):
    if len(lines) >= MAX_TREE_LINES:
        return

    try:
        children = sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
    except OSError as error:
        lines.append(f"{'    ' * level}[错误] 无法读取目录：{error}")
        return

    for child in children:
        if child.is_dir() and should_skip_dir(child):
            continue
        prefix = "    " * level
        item_type = "[目录]" if child.is_dir() else "[文件]"
        lines.append(f"{prefix}{item_type} {child.name}")
        if len(lines) >= MAX_TREE_LINES:
            lines.append("...")
            return
        if child.is_dir():
            append_tree_lines(child, level + 1, lines)
            if len(lines) >= MAX_TREE_LINES:
                return


def build_tree_output(directory):
    lines = ["查询结果:", f"目录:{to_relative_path(directory)}"]
    append_tree_lines(directory, 0, lines)
    return "\n".join(lines)


def handle_tree(command):
    target_text, error_text = parse_command_argument(
        command.strip(),
        (TREE_COMMAND, LEGACY_TREE_COMMAND),
        f"用法：{TREE_COMMAND} <具体的文件名>",
    )
    if error_text != "":
        return error_text

    target_path, target_error = resolve_tree_target(target_text)
    if target_error != "":
        return target_error

    base_dir = target_path if target_path.is_dir() else target_path.parent
    return build_tree_output(base_dir)


def decode_text_content(raw_bytes):
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return raw_bytes.decode(encoding), ""
        except UnicodeDecodeError:
            continue
    if b"\x00" in raw_bytes:
        return "", "该文件可能是二进制文件，暂不支持直接读取"
    return raw_bytes.decode("utf-8", errors="replace"), ""


def build_read_output(content, truncated):
    lines = ["读取结果:", content]
    if truncated:
        lines.append("")
        lines.append(f"已截断输出，仅展示前{MAX_READ_CHARS}个字符")
    return "\n".join(lines)


def handle_read(command):
    path_text, error_text = parse_command_argument(
        command.strip(),
        (READ_COMMAND,),
        f"用法：{READ_COMMAND} <相对路径>",
    )
    if error_text != "":
        return error_text

    target_path, target_error = resolve_existing_path(path_text)
    if target_error != "":
        return target_error
    if target_path is None:
        return f"未找到文件：{normalize_relative_text(path_text)}"
    if target_path.is_file() is False:
        return f"目标不是文件：{to_relative_path(target_path)}"

    try:
        raw_bytes = target_path.read_bytes()
    except OSError as error:
        return f"读取文件失败：{error}"

    content, decode_error = decode_text_content(raw_bytes)
    if decode_error != "":
        return decode_error

    truncated = False
    if len(content) > MAX_READ_CHARS:
        content = content[:MAX_READ_CHARS].rstrip()
        truncated = True

    return build_read_output(content, truncated)


def main():
    command = read_payload()
    if command == "":
        print(get_usage_text())
        return

    if command.startswith(FIND_COMMAND) or command.startswith(LEGACY_FIND_COMMAND):
        print(handle_find(command))
        return

    if command.startswith(TREE_COMMAND) or command.startswith(LEGACY_TREE_COMMAND):
        print(handle_tree(command))
        return

    if command.startswith(READ_COMMAND):
        print(handle_read(command))
        return

    print(get_usage_text())


if __name__ == "__main__":
    main()
