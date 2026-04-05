import json
import sys
import urllib.request


def load_payload():
    if len(sys.argv) > 1 and sys.argv[1] == "--payload-stdin":
        return sys.stdin.buffer.read().decode("utf-8")
    if len(sys.argv) > 1:
        return sys.argv[1]
    return ""


payload = load_payload()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def parse_chat_tool_payload(text):
    lines = text.splitlines()
    data = {
        "main_soul": "",
        "else_for_run": "",
        "base_url": "",
        "API_key": "",
        "API_model": "",
        "user_input": "",
        "zip": "",
        "history_lines": [],
        "tool_lines": [],
    }
    state = ""
    for line in lines[2:]:
        if line.startswith("main_soul="):
            state = "main_soul"
            data["main_soul"] = line[len("main_soul=") :]
            continue
        if line.startswith("else_for_run="):
            state = "else_for_run"
            data["else_for_run"] = line[len("else_for_run=") :]
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
        if line == "history:":
            state = "history"
            continue
        if line.startswith("zip:"):
            state = ""
            data["zip"] = line[len("zip:") :]
            continue
        if line == "tool:":
            state = "tool"
            continue
        if state == "main_soul":
            data["main_soul"] = data["main_soul"] + "\n" + line
            continue
        if state == "else_for_run":
            data["else_for_run"] = data["else_for_run"] + "\n" + line
            continue
        if state == "history":
            data["history_lines"].append(line)
            continue
        if state == "tool":
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
            continue
        if line == "zip:":
            state = "zip"
            continue
        if state == "prompt":
            data["prompt"] = data["prompt"] + "\n" + line
            continue
        if state == "zip":
            data["zip_lines"].append(line)
    return data


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


def run_chat_tool(mode):
    data = parse_chat_tool_payload(payload)
    user_lines = [
        f"user_input:{data['user_input']}",
        "history:",
        f"zip:{data['zip']}",
        *data["history_lines"],
    ]
    if mode == "tool":
        user_lines.extend(["tool:", *data["tool_lines"]])
    response_data = request_chat_completion(
        data["base_url"],
        data["API_key"],
        data["API_model"],
        [
            {"role": "system", "content": data["main_soul"]},
            {"role": "system", "content": data["else_for_run"]},
            {"role": "user", "content": "\n".join(user_lines)},
        ],
    )
    content = response_data["choices"][0]["message"]["content"].strip()
    token = response_data["usage"]["total_tokens"]
    lines = content.splitlines()
    result_type = lines[0].strip()
    if result_type == "type:message":
        output = "\n".join(lines[1:])[len("output:") :]
        print(f"type:message\noutput:{output}\ntoken:{token}")
    if result_type == "type:task":
        command = "\n".join(lines[1:])[len("command:") :]
        print(f"type:task\ncommand:{command}\ntoken:{token}")
    if result_type != "type:message" and result_type != "type:task":
        print(f"type:message\noutput:{content}\ntoken:{token}")


def run_prompt():
    data = parse_prompt_payload(payload)
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
    run_chat_tool("chat")


if payload.startswith("type:tool"):
    run_chat_tool("tool")


if payload.startswith("type:prompt"):
    run_prompt()
