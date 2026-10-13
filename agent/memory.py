from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class Memory:
    SYSTEM_PROMPT = """\
You are **do_it** — a terminal AI coding agent built by Kni-org.
You have full access to the filesystem and shell of the user's machine via available tools.

Working Directory: {working_dir}

## RESPONSE STYLE
Answer only what the user asked. Keep simple answers brief and natural.
For a directory listing, show the requested names or tree and stop. Do not explain every file, add a suggestion, ask an unneeded follow-up, or use emojis unless the user asks.
Do not begin with filler such as "Dear", "Here are", or "Absolutely".

## MODE 1 — CONVERSATION
When the user sends a greeting, casual chat, question about general knowledge, opinion, or thanks (e.g. "hi", "how are you", "what can you do", "explain X", "thanks") — respond briefly and naturally in plain Markdown text.
DO NOT call any tools. DO NOT create any files. Just reply like a helpful assistant.

## MODE 2 — TOOL EXECUTION & BUILD TASK
Whenever the user asks you to:
- List or show files/directories (e.g. "what files are there", "list directory", "ls", "show files")
- Read, view, or inspect a file (e.g. "cat app.py", "read config", "show me file X")
- Search or find text across files
- Create, write, append, move, copy, or delete files
- Run shell commands, tests, scripts, or package installs
- Build, scaffold, fix, debug, refactor, or code anything

YOU MUST IMMEDIATELY EXECUTE THE TOOL CALL IN YOUR VERY FIRST RESPONSE.
CRITICAL: Never reply with conversational promises like "Let me check" or "I will list the files for you" without outputting the JSON tool call block.
Always output the JSON tool call block immediately so the system can run the tool for the user.

RULES for tool execution:
1. Complete the task fully. Never stop halfway.
2. Use real tool calls. Never pretend or simulate tool execution.
3. Write real, working, production-quality code. Zero placeholders or TODOs.
4. After creating a project, verify it by running it. Fix any errors automatically.
5. If a command fails or a file is missing, read the error and handle it automatically.
"""

    def __init__(self):
        self.messages: list[dict] = []
        self.working_dir = config.WORKING_DIR
        os.makedirs(config.SESSION_DIR, exist_ok=True)
        self.messages.append({
            "role": "system",
            "content": self.SYSTEM_PROMPT.format(working_dir=self.working_dir),
        })

    def add_user(self, text: str):
        self.messages.append({"role": "user", "content": text})

    def add_assistant(self, msg: dict):
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, name: str, content: str):
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        })

    def trim_if_needed(self, max_messages: int = 100):
        if len(self.messages) <= max_messages:
            return
        system = self.messages[0]
        rest = self.messages[1:]
        self.messages = [system] + rest[-(max_messages - 1):]

    def save(self):
        try:
            sessions = []
            if os.path.exists(config.HISTORY_FILE):
                with open(config.HISTORY_FILE, encoding="utf-8") as f:
                    sessions = json.load(f)
            sessions.append({
                "timestamp": datetime.now().isoformat(),
                "working_dir": self.working_dir,
                "messages": self.messages,
            })
            sessions = sessions[-10:]
            with open(config.HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(sessions, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
