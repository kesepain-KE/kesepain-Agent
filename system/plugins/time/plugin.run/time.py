import sys
from datetime import datetime


payload = " ".join(sys.argv[1:]).strip()


def set_stream_utf8(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


set_stream_utf8(sys.stdout)
set_stream_utf8(sys.stderr)
set_stream_utf8(sys.stdin)


if payload == "":
    payload = sys.stdin.buffer.readline().decode("utf-8").strip()

if payload == "":
    print("用法：/查询时间")
    sys.exit(0)

now = datetime.now()
print(f"{now.year}年{now.month}月{now.day}日{now.hour}:{now.minute:02d}:{now.second:02d}")
