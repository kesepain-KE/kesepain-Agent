import json
import sys
import urllib.request


def load_payload():
    if len(sys.argv) > 1 and sys.argv[1] == "--payload-stdin":
        return sys.stdin.buffer.read().decode("utf-8")
    if len(sys.argv) > 1:
        return sys.argv[1]
    return ""


def safe_reconfigure_text_stream(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


payload = load_payload()
safe_reconfigure_text_stream(sys.stdout)
safe_reconfigure_text_stream(sys.stdin)
safe_reconfigure_text_stream(sys.stderr)


def parse_chat_payload(text):
    """Strict parser for start mode payload defined in LLM docs."""
    lines = text.splitlines()
    data = {
        "soul_prompt": "",
        "task_prompt": "",
        "base_url": "",
        "API_key": "",
        "API_model": "",
        "user_input": "",
        "zip": "",
        "history_lines": [],
    }
    state = ""

    for line in lines[1:]:
        if line.startswith("soul_prompt:"):
            state = "soul_prompt"
            data["soul_prompt"] = line[len("soul_prompt:") :]
            continue
        if line.startswith("task_prompt:"):
            state = "task_prompt"
            data["task_prompt"] = line[len("task_prompt:") :]
            continue
        if line.startswith("base_url:"):
            state = ""
            data["base_url"] = line[len("base_url:") :]
            continue
        if line.startswith("API_key:"):
            state = ""
            data["API_key"] = line[len("API_key:") :]
            continue
        if line.startswith("API_model:"):
            state = ""
            data["API_model"] = line[len("API_model:") :]
            continue
        if line.startswith("user_input:"):
            state = ""
            data["user_input"] = line[len("user_input:") :]
            continue
        if line.startswith("zip:"):
            state = "history"
            data["zip"] = line[len("zip:") :]
            continue

        if state == "soul_prompt":
            data["soul_prompt"] = data["soul_prompt"] + "\n" + line
            continue
        if state == "task_prompt":
            data["task_prompt"] = data["task_prompt"] + "\n" + line
            continue
        if state == "history" and line != "":
            data["history_lines"].append(line)

    return data


def parse_tool_payload(text):
    """Parser for tool mode payload defined in LLM docs."""
    lines = text.splitlines()
    data = {
        "soul_prompt": "",
        "task_prompt": "",
        "base_url": "",
        "API_key": "",
        "API_model": "",
        "user_input": "",
        "zip": "",
        "history_lines": [],
        "tool_lines": [],
    }
    state = ""

    def parse_assign_value(line, key):
        if line.startswith(f"{key}="):
            return line[len(key) + 1 :]
        if line.startswith(f"{key}:"):
            return line[len(key) + 1 :]
        return None

    for line in lines[1:]:
        soul_value = parse_assign_value(line, "soul_prompt")
        if soul_value is not None:
            state = "soul_prompt"
            data["soul_prompt"] = soul_value
            continue

        task_value = parse_assign_value(line, "task_prompt")
        if task_value is not None:
            state = "task_prompt"
            data["task_prompt"] = task_value
            continue

        if line.startswith("base_url:"):
            state = ""
            data["base_url"] = line[len("base_url:") :]
            continue
        if line.startswith("API_key:"):
            state = ""
            data["API_key"] = line[len("API_key:") :]
            continue
        if line.startswith("API_model:"):
            state = ""
            data["API_model"] = line[len("API_model:") :]
            continue
        if line.startswith("user_input:"):
            state = ""
            data["user_input"] = line[len("user_input:") :]
            continue
        if line.startswith("zip:"):
            state = "history"
            data["zip"] = line[len("zip:") :]
            continue
        if line == "tool_log:" or line == "tool:":
            state = "tool"
            continue

        if state == "soul_prompt":
            data["soul_prompt"] = data["soul_prompt"] + "\n" + line
            continue
        if state == "task_prompt":
            data["task_prompt"] = data["task_prompt"] + "\n" + line
            continue
        if state == "history" and line != "":
            data["history_lines"].append(line)
            continue
        if state == "tool" and line != "":
            data["tool_lines"].append(line)

    return data


def parse_prompt_payload(text):
    lines = text.splitlines()
    data = {
        "prompt": "",
        "key": "",
        "base_url": "",
        "model": "",
        "zip_lines": [],
    }
    state = ""
    model_loaded = False
    for line in lines[1:]:
        if line.startswith("prompt:"):
            state = "prompt"
            data["prompt"] = line[len("prompt:") :]
            continue
        if line.startswith("key:"):
            state = ""
            data["key"] = line[len("key:") :]
            continue
        if line.startswith("base_url:"):
            state = ""
            data["base_url"] = line[len("base_url:") :]
            continue
        if line.startswith("model:"):
            state = ""
            data["model"] = line[len("model:") :]
            model_loaded = True
            continue
        if line == "zip:":
            state = "zip"
            continue
        if state == "prompt":
            data["prompt"] = data["prompt"] + "\n" + line
            continue
        if state == "zip" and line != "":
            data["zip_lines"].append(line)
            continue
        if model_loaded and line != "":
            data["zip_lines"].append(line)
    return data


def get_missing_fields(data, required_fields):
    missing = []
    for key in required_fields:
        if data.get(key, "") == "":
            missing.append(key)
    return missing


def print_chat_or_tool_result(content, token):
    lines = content.splitlines()
    if len(lines) == 0:
        print(f"type:message\noutput:\ntoken:{token}")
        return

    result_type = lines[0].strip()
    if result_type == "type:message":
        body = "\n".join(lines[1:])
        if body.startswith("output:"):
            body = body[len("output:") :]
        print(f"type:message\noutput:{body}\ntoken:{token}")
        return

    if result_type == "type:task":
        body = "\n".join(lines[1:])
        if body.startswith("command:"):
            body = body[len("command:") :]
        print(f"type:task\ncommand:{body}\ntoken:{token}")
        return

    print(f"type:message\noutput:{content}\ntoken:{token}")


def request_chat_completion(base_url, api_key, model, messages):
    request_data = json.dumps(
        {
            "model": model,
            "messages": messages,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=request_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def run_chat():
    data = parse_chat_payload(payload)
    missing = get_missing_fields(
        data,
        ["soul_prompt", "task_prompt", "base_url", "API_key", "API_model", "user_input"],
    )
    if len(missing) != 0:
        print(f"type:message\noutput:LLM start模式负载缺少字段:{','.join(missing)}\ntoken:0")
        return

    user_lines = [
        f"user_input:{data['user_input']}",
        f"zip:{data['zip']}",
        *data["history_lines"],
    ]
    response_data = request_chat_completion(
        data["base_url"],
        data["API_key"],
        data["API_model"],
        [
            {"role": "system", "content": data["soul_prompt"]},
            {"role": "system", "content": data["task_prompt"]},
            {"role": "user", "content": "\n".join(user_lines)},
        ],
    )
    content = response_data["choices"][0]["message"]["content"].strip()
    token = response_data["usage"]["total_tokens"]
    print_chat_or_tool_result(content, token)


def run_tool():
    data = parse_tool_payload(payload)
    missing = get_missing_fields(
        data,
        ["soul_prompt", "task_prompt", "base_url", "API_key", "API_model", "user_input"],
    )
    if len(missing) != 0:
        print(f"type:message\noutput:LLM tool模式负载缺少字段:{','.join(missing)}\ntoken:0")
        return

    user_lines = [
        f"user_input:{data['user_input']}",
        f"zip:{data['zip']}",
        *data["history_lines"],
        "tool:",
        *data["tool_lines"],
    ]
    response_data = request_chat_completion(
        data["base_url"],
        data["API_key"],
        data["API_model"],
        [
            {"role": "system", "content": data["soul_prompt"]},
            {"role": "system", "content": data["task_prompt"]},
            {"role": "user", "content": "\n".join(user_lines)},
        ],
    )
    content = response_data["choices"][0]["message"]["content"].strip()
    token = response_data["usage"]["total_tokens"]
    print_chat_or_tool_result(content, token)


def run_prompt():
    data = parse_prompt_payload(payload)
    missing = get_missing_fields(data, ["prompt", "key", "base_url", "model"])
    if len(missing) != 0:
        print(f"zip:LLM prompt模式负载缺少字段:{','.join(missing)}")
        return
    if len(data["zip_lines"]) == 0:
        print("zip:")
        return

    response_data = request_chat_completion(
        data["base_url"],
        data["key"],
        data["model"],
        [
            {"role": "system", "content": data["prompt"]},
            {"role": "user", "content": "\n".join(data["zip_lines"])},
        ],
    )
    content = response_data["choices"][0]["message"]["content"].strip()
    print(f"zip:{content}")


if payload.startswith("type:chat"):
    run_chat()


if payload.startswith("type:tool"):
    run_tool()


if payload.startswith("type:prompt"):
    run_prompt()
