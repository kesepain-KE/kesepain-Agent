import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path


config_path = Path(__file__).resolve().parent / "config.json"
payload = " ".join(sys.argv[1:]).strip()


def set_stream_utf8(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


set_stream_utf8(sys.stdout)
set_stream_utf8(sys.stderr)
set_stream_utf8(sys.stdin)


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_command(command):
    parts = command.split()
    return parts[1], parts[2]


def format_date(date_text):
    year, month, day = date_text.split("-")
    return f"{year}.{int(month)}.{int(day)}"


if payload == "":
    payload = sys.stdin.buffer.readline().decode("utf-8").strip()

if payload == "":
    print("用法：/查询天气 <城市> <未来天数>")
    sys.exit(0)

city, days = parse_command(payload)
config_data = load_json(config_path)

query = urllib.parse.urlencode(
    {
        "key": config_data["private_key"],
        "location": city,
        "language": "zh-Hans",
        "unit": "c",
        "start": 0,
        "days": days,
    }
)

url = f"https://api.seniverse.com/v3/weather/daily.json?{query}"
request = urllib.request.Request(url, method="GET")

with urllib.request.urlopen(request) as response:
    weather_data = json.loads(response.read().decode("utf-8"))

result = weather_data["results"][0]
print(result["location"]["name"])
for daily in result["daily"]:
    print(
        f"时间{format_date(daily['date'])}|"
        f"{daily['text_day']}天气|"
        f"{daily['high']}度|"
        f"{daily['wind_scale']}级风力"
    )
