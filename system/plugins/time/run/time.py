import sys
from datetime import datetime


TIME_COMMAND = "/查询时间"
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
    return f"用法：{TIME_COMMAND}"


def parse_command(command):
    command_text = command.strip()
    if command_text == "":
        return False, get_usage_text()
    if command_text != TIME_COMMAND:
        return False, get_usage_text()
    return True, ""


def format_current_time():
    now = datetime.now()
    return f"当前时间为:{now.year}年{now.month}月{now.day}日{now.hour}:{now.minute:02d}:{now.second:02d}"


def main():
    command = read_payload()
    ok, error_text = parse_command(command)
    if ok is False:
        print(error_text)
        return

    print(format_current_time())


if __name__ == "__main__":
    main()
