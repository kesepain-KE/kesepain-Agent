import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_URL = "https://api.tavily.com/search"
SEARCH_COMMAND = "/网络搜索"
LEGACY_SEARCH_COMMAND = "/网络查询"
USAGE_TEXT = f"用法：{SEARCH_COMMAND} <多个关键词>"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
payload = " ".join(sys.argv[1:]).strip()


def set_stream_utf8(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


set_stream_utf8(sys.stdout)
set_stream_utf8(sys.stderr)
set_stream_utf8(sys.stdin)


def normalize_text(value):
    if isinstance(value, str) is False:
        return ""
    return " ".join(value.split())


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_payload():
    if payload != "":
        return payload
    return sys.stdin.buffer.readline().decode("utf-8").strip()


def parse_query(command):
    command_text = command.strip()
    prefix = ""
    if command_text.startswith(SEARCH_COMMAND):
        prefix = SEARCH_COMMAND
    elif command_text.startswith(LEGACY_SEARCH_COMMAND):
        prefix = LEGACY_SEARCH_COMMAND
    if command_text == "" or prefix == "":
        return "", USAGE_TEXT
    query = command_text[len(prefix) :].strip()
    if query == "":
        return "", USAGE_TEXT
    return query, ""


def load_key():
    if CONFIG_PATH.exists() is False:
        return "", f"配置文件不存在：{CONFIG_PATH.name}"
    try:
        config_data = load_json(CONFIG_PATH)
    except json.JSONDecodeError:
        return "", "配置文件格式错误，请检查 config.json"
    except OSError as error:
        return "", f"读取配置文件失败：{error}"

    key = normalize_text(config_data.get("key", ""))
    if key == "":
        return "", "未配置 Tavily key，请检查 config.json"
    return key, ""


def build_request_data(query):
    return {
        "query": query,
        "search_depth": "basic",
        "topic": "general",
        "max_results": 5,
        "include_answer": True,
    }


def parse_error_message(body_text):
    if body_text == "":
        return ""
    try:
        error_data = json.loads(body_text)
    except json.JSONDecodeError:
        return normalize_text(body_text)[:200]

    for key in ("detail", "message", "error"):
        value = error_data.get(key, "")
        if isinstance(value, str) and value.strip() != "":
            return normalize_text(value)
    return normalize_text(body_text)[:200]


def call_tavily(key, query):
    request_body = json.dumps(build_request_data(query), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="ignore").strip()
        error_message = parse_error_message(error_body)
        if error_message != "":
            return None, f"网络查询失败：HTTP {error.code} {error_message}"
        return None, f"网络查询失败：HTTP {error.code}"
    except urllib.error.URLError as error:
        return None, f"网络查询失败：{error.reason}"
    except TimeoutError:
        return None, "网络查询失败：请求超时"
    except OSError as error:
        return None, f"网络查询失败：{error}"

    try:
        response_data = json.loads(response_body)
    except json.JSONDecodeError:
        return None, "网络查询失败：返回数据格式错误"

    if isinstance(response_data, dict) is False:
        return None, "网络查询失败：返回数据格式错误"
    return response_data, ""


def truncate_text(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def build_fallback_summary(results):
    fragments = []
    for result in results[:3]:
        if isinstance(result, dict) is False:
            continue
        content = normalize_text(result.get("content", ""))
        if content == "":
            continue
        fragments.append(content)
        if len(" ".join(fragments)) >= 220:
            break
    if len(fragments) == 0:
        return "未查询到相关网络信息"
    return truncate_text(" ".join(fragments), 220)


def format_result(query, response_data):
    results = response_data.get("results", [])
    if isinstance(results, list) is False:
        return "网络查询失败：返回数据格式错误"

    answer = normalize_text(response_data.get("answer", ""))
    if answer == "":
        answer = build_fallback_summary(results)

    lines = [f"查询:{query}", f"摘要:{answer}"]
    for index, item in enumerate(results[:5], start=1):
        if isinstance(item, dict) is False:
            continue
        title = normalize_text(item.get("title", "")) or "未提供标题"
        url = normalize_text(item.get("url", "")) or "未提供链接"
        content = normalize_text(item.get("content", "")) or "未提供摘要"
        lines.append(f"来源{index}:{title}")
        lines.append(f"链接{index}:{url}")
        lines.append(f"摘要{index}:{truncate_text(content, 220)}")
    return "\n".join(lines)


def main():
    command = read_payload()
    query, query_error = parse_query(command)
    if query_error != "":
        print(query_error)
        return

    key, key_error = load_key()
    if key_error != "":
        print(key_error)
        return

    response_data, request_error = call_tavily(key, query)
    if request_error != "":
        print(request_error)
        return

    print(format_result(query, response_data))


if __name__ == "__main__":
    main()
