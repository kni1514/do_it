from __future__ import annotations

import json
import os
import sys
from typing import Any

from rich.console import Console
from rich.markup import escape

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from agent import llm, tools
from agent.memory import Memory

console = Console()

_TOOL_ICONS = {
    "read_file":    "📖",
    "write_file":   "✏️ ",
    "edit_file":    "🔧",
    "append_file":  "➕",
    "list_dir":     "📁",
    "create_dir":   "📂",
    "delete_file":  "🗑️ ",
    "move_file":    "📦",
    "copy_file":    "🗐 ",
    "run_command":  "⚡",
    "search_web":   "🔍",
    "get_file_info":"ℹ️ ",
    "find_in_files":"🔎",
    "patch_json":   "🗄️ ",
}


def _safe_print(text: str):
    try:
        console.print(text)
    except Exception:
        try:
            print(text.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass


def _tool_label(name: str, args: dict) -> str:
    icon = _TOOL_ICONS.get(name, "🔨")
    match name:
        case "write_file":
            return f"{icon} write_file    [cyan]{args.get('path', '')}[/cyan]"
        case "read_file":
            return f"{icon} read_file     [cyan]{args.get('path', '')}[/cyan]"
        case "edit_file":
            return f"{icon} edit_file     [cyan]{args.get('path', '')}[/cyan]"
        case "append_file":
            return f"{icon} append_file   [cyan]{args.get('path', '')}[/cyan]"
        case "copy_file":
            return f"{icon} copy_file     [cyan]{args.get('src', '')}[/cyan] → [cyan]{args.get('dst', '')}[/cyan]"
        case "move_file":
            return f"{icon} move_file     [cyan]{args.get('src', '')}[/cyan] → [cyan]{args.get('dst', '')}[/cyan]"
        case "delete_file":
            return f"{icon} delete_file   [red]{args.get('path', '')}[/red]"
        case "create_dir":
            return f"{icon} create_dir    [cyan]{args.get('path', '')}[/cyan]"
        case "run_command":
            cmd = args.get("command", "")
            short = cmd if len(cmd) < 64 else cmd[:61] + "…"
            return f"{icon} run_command   [yellow]{escape(short)}[/yellow]"
        case "search_web":
            return f"{icon} search_web    [yellow]{escape(args.get('query', ''))}[/yellow]"
        case "find_in_files":
            return f"{icon} find_in_files [yellow]{escape(args.get('pattern', ''))}[/yellow]"
        case "patch_json":
            return f"{icon} patch_json    [cyan]{args.get('path', '')}[/cyan]  [{args.get('key_path', '')}]"
        case _:
            return f"{icon} {name}"


def _print_tool_result(name: str, raw: str):
    try:
        data = json.loads(raw)
    except Exception:
        data = raw

    if not isinstance(data, dict):
        return

    if "error" in data:
        _safe_print(f"   [red]✗ {escape(str(data['error']))}[/red]")
        return

    if name == "run_command":
        rc = data.get("returncode", 0)
        stdout = (data.get("stdout") or "").strip()
        stderr = (data.get("stderr") or "").strip()
        status = "[green]✓ exit 0[/green]" if rc == 0 else f"[red]✗ exit {rc}[/red]"
        _safe_print(f"   {status}")
        if stdout:
            lines = stdout.split("\n")
            shown = "\n   ".join(lines[:20])
            suffix = f"\n   [dim]… {len(lines) - 20} more lines[/dim]" if len(lines) > 20 else ""
            _safe_print(f"   [dim]{escape(shown)}[/dim]{suffix}")
        if stderr and rc != 0:
            lines = stderr.split("\n")
            _safe_print(f"   [dim red]{escape(chr(10).join(lines[:10]))}[/dim red]")
        return

    if name in ("write_file", "edit_file", "append_file", "create_dir",
                "move_file", "copy_file", "delete_file", "patch_json"):
        _safe_print("   [green]✓ done[/green]")
        return

    if name == "read_file":
        lines = (data.get("content") or "").split("\n")
        _safe_print(f"   [dim]{escape(chr(10).join(lines[:6]))}[/dim]")
        return

    if name == "list_dir":
        tree = data.get("tree") or {}
        keys = list(tree.keys())[:14]
        _safe_print(f"   [dim]{escape(', '.join(keys))}[/dim]")
        return

    if name == "search_web":
        for r in (data.get("results") or [])[:2]:
            snippet = (r.get("snippet") or "")[:120]
            _safe_print(f"   [dim]• {escape(snippet)}[/dim]")
        return

    if name == "find_in_files":
        total = data.get("total", 0)
        matches = data.get("matches", [])[:3]
        _safe_print(f"   [dim]{total} match(es)[/dim]")
        for m in matches:
            _safe_print(f"   [dim]{m['file']}:{m['line']}  {escape(m['text'][:80])}[/dim]")
        return


def _is_direct_listing_request(text: str) -> bool:
    value = text.lower()
    asks_to_list = any(word in value for word in ("list", "show", "display", "what files", "which files"))
    asks_for_files = any(word in value for word in ("file", "folder", "directory", "directories", "contents"))
    asks_for_explanation = any(word in value for word in ("explain", "describe", "purpose", "what each", "what does"))
    return asks_to_list and asks_for_files and not asks_for_explanation


def _directory_tree_markdown(raw: str) -> str:
    data = json.loads(raw)
    tree = data.get("tree") or {}
    location = os.path.basename(os.path.normpath(data.get("path") or ".")) or "."
    lines = [f"{location}/"]

    def append_entries(entries: dict, prefix: str):
        items = sorted(entries.items())
        for index, (name, value) in enumerate(items):
            last = index == len(items) - 1
            branch = "└── " if last else "├── "
            is_directory = isinstance(value, dict)
            lines.append(f"{prefix}{branch}{name}{'/' if is_directory else ''}")
            if is_directory:
                append_entries(value, prefix + ("    " if last else "│   "))

    append_entries(tree, "")
    return "```text\n" + "\n".join(lines) + "\n```"


class Agent:
    def __init__(self):
        self.memory = Memory()

    def run(self, user_input: str) -> str:
        self.memory.add_user(user_input)
        self.memory.trim_if_needed()

        iterations = 0
        msg: dict = {}

        while iterations < config.MAX_ITERATIONS:
            iterations += 1

            with console.status("[bold blue]thinking…[/bold blue]", spinner="dots"):
                try:
                    msg = llm.chat_completion(
                        messages=self.memory.messages,
                        tools=tools.TOOL_SCHEMAS,
                    )
                except RuntimeError as e:
                    _safe_print(f"\n[red]{e}[/red]")
                    return str(e)
                except Exception:
                    _safe_print("\n[red]AI call failed[/red]")
                    return "AI call failed"

            self.memory.add_assistant(msg)

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                break

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                tc_id = tc["id"]

                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {}

                _safe_print(f"  {_tool_label(fn_name, args)}")
                result = tools.dispatch(fn_name, args)
                self.memory.add_tool_result(tc_id, fn_name, result)
                if (
                    fn_name == "list_dir"
                    and len(tool_calls) == 1
                    and _is_direct_listing_request(user_input)
                ):
                    self.memory.save()
                    return _directory_tree_markdown(result)
                _print_tool_result(fn_name, result)

        self.memory.save()
        return msg.get("content", "")
