import json
import re
import subprocess
import sys
import urllib.parse
from datetime import date, timedelta


WEATHER_COMMAND = "/天气查询"
LEGACY_WEATHER_COMMAND = "/查询天气"
USAGE_TEXT = f"用法：{WEATHER_COMMAND} <城市> <具体时间>"
DATE_PATTERN = re.compile(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?$")
SHORT_DATE_PATTERN = re.compile(r"^(\d{1,2})[-/月](\d{1,2})日?$")
payload = " ".join(sys.argv[1:]).strip()


DESCRIPTION_MAP = {
    "Sunny": "晴",
    "Clear": "晴",
    "Partly cloudy": "多云",
    "Cloudy": "阴",
    "Overcast": "阴",
    "Mist": "薄雾",
    "Fog": "雾",
    "Patchy rain nearby": "附近有零星降雨",
    "Patchy light rain": "零星小雨",
    "Light rain": "小雨",
    "Moderate rain": "中雨",
    "Heavy rain": "大雨",
    "Patchy snow nearby": "附近有零星降雪",
    "Light snow": "小雪",
    "Moderate snow": "中雪",
    "Heavy snow": "大雪",
    "Thundery outbreaks nearby": "附近有雷暴",
}


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
    prefix = ""
    if command_text.startswith(WEATHER_COMMAND):
        prefix = WEATHER_COMMAND
    elif command_text.startswith(LEGACY_WEATHER_COMMAND):
        prefix = LEGACY_WEATHER_COMMAND
    if prefix == "":
        return "", None, USAGE_TEXT

    remainder = command_text[len(prefix) :].strip()
    if remainder == "":
        return "", None, USAGE_TEXT

    parts = remainder.split(maxsplit=1)
    if len(parts) != 2:
        return "", None, USAGE_TEXT

    city = parts[0].strip()
    target_date, error_text = parse_date_text(parts[1].strip())
    if error_text != "":
        return "", None, error_text
    return city, target_date, ""


def parse_date_text(text):
    today = date.today()
    offset_map = {
        "今天": 0,
        "今日": 0,
        "明天": 1,
        "后天": 2,
        "昨天": -1,
        "前天": -2,
    }
    if text in offset_map:
        return today + timedelta(days=offset_map[text]), ""

    match = DATE_PATTERN.match(text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3))), ""
        except ValueError:
            return None, "日期格式错误，请使用有效日期"

    match = SHORT_DATE_PATTERN.match(text)
    if match:
        try:
            return date(today.year, int(match.group(1)), int(match.group(2))), ""
        except ValueError:
            return None, "日期格式错误，请使用有效日期"

    return None, "时间格式不支持，请使用今天、明天、后天、昨天、前天或YYYY-MM-DD"


def fetch_weather_json(city):
    city_text = urllib.parse.quote(city)
    uri = f"https://wttr.in/{city_text}?format=j1"
    ps_command = "\n".join(
        [
            "$ProgressPreference='SilentlyContinue'",
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8",
            f"(Invoke-WebRequest -Uri '{uri}' -UseBasicParsing).Content",
        ]
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except OSError as error:
        return None, f"天气查询失败：{error}"

    if result.returncode != 0:
        error_text = result.stderr.strip() or result.stdout.strip()
        return None, f"天气查询失败：{error_text or '请求失败'}"

    body_text = result.stdout.strip()
    if body_text == "":
        return None, "天气查询失败：返回内容为空"

    try:
        return json.loads(body_text), ""
    except json.JSONDecodeError:
        return None, "天气查询失败：返回数据格式错误"


def get_hourly_description(hourly_items):
    if isinstance(hourly_items, list) is False or len(hourly_items) == 0:
        return "未知"
    preferred_index = min(4, len(hourly_items) - 1)
    candidate = hourly_items[preferred_index]
    descriptions = candidate.get("weatherDesc", [])
    if isinstance(descriptions, list) and len(descriptions) != 0:
        description = str(descriptions[0].get("value", "")).strip()
        if description != "":
            return DESCRIPTION_MAP.get(description, description)
    return "未知"


def get_total_precipitation(hourly_items):
    total = 0.0
    found = False
    if isinstance(hourly_items, list) is False:
        return "未知"
    for item in hourly_items:
        try:
            total += float(item.get("precipMM", "0") or 0)
            found = True
        except (TypeError, ValueError):
            continue
    if found is False:
        return "未知"
    return f"{total:.1f}".rstrip("0").rstrip(".") + " mm"


def format_temperature(value):
    if value in ("", None):
        return "未知"
    return f"{value}°C"


def format_location(data):
    nearest_area = data.get("nearest_area", [])
    if isinstance(nearest_area, list) is False or len(nearest_area) == 0:
        return "未知城市"

    item = nearest_area[0]
    area_name = item.get("areaName", [{}])
    country = item.get("country", [{}])
    area_text = str(area_name[0].get("value", "")).strip() if area_name else ""
    country_text = str(country[0].get("value", "")).strip() if country else ""
    if area_text == "":
        return country_text or "未知城市"
    if country_text == "":
        return area_text
    return f"{area_text}, {country_text}"


def find_weather_item(data, target_date):
    target_text = target_date.isoformat()
    weather_items = data.get("weather", [])
    if isinstance(weather_items, list) is False:
        return None, []

    available_dates = []
    for item in weather_items:
        item_date = str(item.get("date", "")).strip()
        if item_date != "":
            available_dates.append(item_date)
        if item_date == target_text:
            return item, available_dates
    return None, available_dates


def format_weather(city, target_date, data):
    if target_date < date.today():
        return "当前天气源暂不支持历史天气，请改用今天、明天、后天或近期具体日期"

    weather_item, available_dates = find_weather_item(data, target_date)
    if weather_item is None:
        if len(available_dates) == 0:
            return f"未查询到城市天气：{city}"
        return "当前天气源仅支持以下日期：" + "、".join(available_dates)

    lines = [
        f"城市:{format_location(data)}",
        f"日期:{target_date.isoformat()}",
        f"天气:{get_hourly_description(weather_item.get('hourly', []))}",
        f"最低温:{format_temperature(weather_item.get('mintempC'))}",
        f"最高温:{format_temperature(weather_item.get('maxtempC'))}",
        f"平均温:{format_temperature(weather_item.get('avgtempC'))}",
        f"降水:{get_total_precipitation(weather_item.get('hourly', []))}",
    ]
    return "\n".join(lines)


def main():
    command = read_payload()
    city, target_date, error_text = parse_command(command)
    if error_text != "":
        print(error_text)
        return

    data, request_error = fetch_weather_json(city)
    if request_error != "":
        print(request_error)
        return

    print(format_weather(city, target_date, data))


if __name__ == "__main__":
    main()
