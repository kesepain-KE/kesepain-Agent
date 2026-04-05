import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]
COMMAND_PREFIX = "/文件读取"
USAGE_TEXT = "用法：/文件读取 <工作区相对文件地址>"
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


def parse_command(command):
    command_text = command.strip()
    if command_text == "" or command_text.startswith(COMMAND_PREFIX) is False:
        return "", USAGE_TEXT

    relative_path_text = command_text[len(COMMAND_PREFIX) :].strip()
    if relative_path_text == "":
        return "", USAGE_TEXT
    return relative_path_text, ""


def resolve_workspace_file(relative_path_text):
    input_path = Path(relative_path_text)
    if input_path.is_absolute():
        return None, "无法读取工作区外文件"

    target_path = (ROOT_DIR / input_path).resolve(strict=False)
    try:
        target_path.relative_to(ROOT_DIR)
    except ValueError:
        return None, "无法读取工作区外文件"

    if target_path.exists() is False:
        return None, "目标文件不存在"
    if target_path.is_file() is False:
        return None, "目标路径不是文件"
    return target_path, ""


def is_binary_file(raw_bytes):
    preview = raw_bytes[:1024]
    return b"\x00" in preview


def decode_text(raw_bytes):
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return raw_bytes.decode(encoding), ""
        except UnicodeDecodeError:
            continue
    try:
        return raw_bytes.decode("utf-8", errors="replace"), ""
    except UnicodeDecodeError as error:
        return "", f"读取文件失败：{error}"


def main():
    command = read_payload()
    relative_path_text, parse_error = parse_command(command)
    if parse_error != "":
        print(parse_error)
        return

    target_path, path_error = resolve_workspace_file(relative_path_text)
    if path_error != "":
        print(path_error)
        return
    if target_path is None:
        print("目标文件不存在")
        return

    try:
        raw_bytes = target_path.read_bytes()
    except OSError as error:
        print(f"读取文件失败：{error}")
        return

    if is_binary_file(raw_bytes):
        print("二进制文件不支持直接输出")
        return

    text, decode_error = decode_text(raw_bytes)
    if decode_error != "":
        print(decode_error)
        return

    if text == "":
        print("文件为空")
        return

    sys.stdout.write(text)


if __name__ == "__main__":
    main()
