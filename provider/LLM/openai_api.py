import json
import sys
import urllib.request


payload = sys.argv[1]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def parse_interactive_payload(text):
    lines = text.splitlines()
    data = {
        "main_soul_lines": [],
        "else_for_run_lines": [],
        "history_lines": [],
        "tool_lines": [],
        "zip": "",
    }
    state = ""
    for line in lines[2:]:
        if line.startswith("main_soul="):
            state = "main_soul"
            data["main_soul_lines"].append(line[len("main_soul=") :])
            continue
        if line.startswith("else_for_run="):
            state = "else_for_run"
            data["else_for_run_lines"].append(line[len("else_for_run=") :])
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
        if line == "tool:":
            state = "tool"
            continue
        if line.startswith("zip:"):
            data["zip"] = line[len("zip:") :]
            continue
        if state == "main_soul":
            data["main_soul_lines"].append(line)
            continue
        if state == "else_for_run":
            data["else_for_run_lines"].append(line)
            continue
        if state == "history":
            data["history_lines"].append(line)
            continue
        if state == "tool":
            data["tool_lines"].append(line)
    data["main_soul"] = "\n".join(data["main_soul_lines"])
    data["else_for_run"] = "\n".join(data["else_for_run_lines"])
    return data


def parse_prompt_payload(text):
    lines = text.splitlines()
    data = {
        "prompt_lines": [],
        "zip_lines": [],
    }
    state = ""
    for line in lines[1:]:
        if line.startswith("prompt:"):
            state = "prompt"
            data["prompt_lines"].append(line[len("prompt:") :])
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
            data["prompt_lines"].append(line)
        if state == "zip":
            data["zip_lines"].append(line)
    data["prompt"] = "\n".join(data["prompt_lines"])
    return data


def build_user_content(interactive_data, include_tools):
    lines = [
        f"user_input:{interactive_data['user_input']}",
        "history:",
        f"zip:{interactive_data['zip']}",
        *interactive_data["history_lines"],
    ]
    if include_tools:
        lines.append("tool:")
        lines.extend(interactive_data["tool_lines"])
    return "\n".join(lines)


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


def print_chat_result(content, token):
    lines = content.strip().splitlines()
    result_type = lines[0].strip()
    body_lines = lines[1:]
    if result_type == "type:message":
        body_lines[0] = body_lines[0][len("output:") :]
        output = "\n".join(body_lines)
        print(f"type:message\noutput:{output}\ntoken:{token}")
    if result_type == "type:task":
        body_lines[0] = body_lines[0][len("command:") :]
        command = "\n".join(body_lines)
        print(f"type:task\ncommand:{command}\ntoken:{token}")


if payload.startswith("type:chat") or payload.startswith("type:tool"):
    include_tools = payload.startswith("type:tool")
    interactive_data = parse_interactive_payload(payload)
    response_data = request_chat_completion(
        interactive_data["base_url"],
        interactive_data["API_key"],
        interactive_data["API_model"],
        [
            {"role": "system", "content": interactive_data["main_soul"]},
            {"role": "system", "content": interactive_data["else_for_run"]},
            {
                "role": "user",
                "content": build_user_content(interactive_data, include_tools),
            },
        ],
    )
    response_content = response_data["choices"][0]["message"]["content"]
    response_token = response_data["usage"]["total_tokens"]
    print_chat_result(response_content, response_token)


if payload.startswith("type:prompt"):
    prompt_data = parse_prompt_payload(payload)
    response_data = request_chat_completion(
        prompt_data["base_url"],
        prompt_data["key"],
        prompt_data["model"],
        [
            {"role": "system", "content": prompt_data["prompt"]},
            {"role": "user", "content": "\n".join(prompt_data["zip_lines"])},
        ],
    )
    response_content = response_data["choices"][0]["message"]["content"].strip()
    print(f"zip:{response_content}")
