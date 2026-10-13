from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

import config


def _request_json(path: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        config.BRIDGE_URL + path,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Bridge returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            "Cannot reach the local bridge. Start it with: python server/app.py"
        ) from error


def _conversation_prompt(messages: list[dict], system_prompt: str) -> str:
    conversation = []
    for message in messages:
        role = message.get("role", "user").upper()
        content = message.get("content", "")
        if role == "TOOL":
            role = f"TOOL RESULT: {message.get('name', 'tool')}"
        conversation.append(f"{role}:\n{content}")
    history = "\n\n".join(conversation)
    return (
        "You are responding through the do_it terminal agent. Follow the system "
        "instructions and conversation below. If tool execution is requested, "
        "return the required JSON tool call block exactly, without executing it yourself.\n\n"
        f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"
        f"CONVERSATION:\n{history}\n\n"
        "Respond to the latest user message."
    )


def call_ai(messages: list[dict], system_prompt: str = "") -> str:
    _, created = _request_json("/ask", {"query": _conversation_prompt(messages, system_prompt)})
    request_id = created.get("id")
    if not request_id:
        raise RuntimeError("The local bridge did not return a request id.")

    deadline = time.monotonic() + 10 * 60
    while time.monotonic() < deadline:
        _, result = _request_json("/result/" + request_id)
        if result.get("status") == "complete":
            return result.get("response", "")
        time.sleep(0.5)
    raise RuntimeError("Timed out waiting for ChatGPT. Check the open ChatGPT tab.")


def _parse_tool_calls(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    parsed_values = []
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE):
        try:
            parsed_values.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass

    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text, index)
            parsed_values.append(value)
        except json.JSONDecodeError:
            pass

    for data in parsed_values:
        raw_calls: list[Any] = []
        if isinstance(data, dict):
            if isinstance(data.get("tool_calls"), list):
                raw_calls = data["tool_calls"]
            elif any(key in data for key in ("name", "tool", "action", "function")):
                raw_calls = [data]
        elif isinstance(data, list):
            raw_calls = data

        tool_calls = []
        for tool_call in raw_calls:
            if not isinstance(tool_call, dict):
                continue
            name = tool_call.get("name") or tool_call.get("tool") or tool_call.get("action")
            function = tool_call.get("function")
            if not name and isinstance(function, dict):
                name = function.get("name")
            arguments = (
                tool_call.get("arguments")
                or tool_call.get("args")
                or tool_call.get("action_input")
                or tool_call.get("parameters")
            )
            if arguments is None and isinstance(function, dict):
                arguments = function.get("arguments", {})
            if name:
                arguments_text = json.dumps(arguments) if isinstance(arguments, dict) else str(arguments or "{}")
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments_text},
                })
        if tool_calls:
            return tool_calls
    return []


def chat_completion(messages: list[dict], tools: list[dict] | None = None) -> dict:
    system_prompt = ""
    filtered_messages: list[dict] = []
    for message in messages:
        if message.get("role") == "system":
            system_prompt += message.get("content", "") + "\n\n"
        else:
            filtered_messages.append(message)

    if tools:
        tool_lines = []
        for tool in tools:
            function = tool.get("function", {})
            tool_lines.append(f"- {function.get('name')}: {function.get('description')}")
        system_prompt += (
            "\nAvailable Tools:\n"
            + "\n".join(tool_lines)
            + "\n\nTOOL EXECUTION INSTRUCTION:\n"
            "1. For requests requiring tools, output JSON with this structure, either fenced or unfenced:\n"
            "```json\n{\"tool_calls\":[{\"name\":\"list_dir\",\"arguments\":{\"path\":\".\"}}]}\n```\n"
            "2. When tool results are present in the history, do not repeat the tool call. Answer the user's request directly and briefly using only the relevant result. Do not add file explanations, suggestions, or follow-up questions unless requested."
        )

    raw_response = call_ai(filtered_messages, system_prompt.strip())
    tool_calls = _parse_tool_calls(raw_response) if tools else []
    content = "" if tool_calls else raw_response.strip()

    result: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result
