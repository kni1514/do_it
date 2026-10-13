from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

console = Console()


def _abs(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(config.WORKING_DIR, path))


def _safe_result(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> str:
    full = _abs(path)
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if end_line is None:
            end_line = len(lines)
        content = "".join(lines[start_line - 1 : end_line])
        return _safe_result({"path": full, "content": content, "total_lines": len(lines)})
    except FileNotFoundError:
        return _safe_result({"error": f"File not found: {full}"})
    except Exception as e:
        return _safe_result({"error": str(e)})


def write_file(path: str, content: str) -> str:
    full = _abs(path)
    try:
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return _safe_result({"status": "ok", "path": full, "bytes": len(content.encode())})
    except Exception as e:
        return _safe_result({"error": str(e)})


def edit_file(path: str, old_text: str, new_text: str) -> str:
    full = _abs(path)
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            content = f.read()
        if old_text not in content:
            return _safe_result({"error": f"Target text not found in {full}"})
        updated = content.replace(old_text, new_text, 1)
        with open(full, "w", encoding="utf-8") as f:
            f.write(updated)
        return _safe_result({"status": "ok", "path": full})
    except Exception as e:
        return _safe_result({"error": str(e)})


def append_file(path: str, content: str) -> str:
    full = _abs(path)
    try:
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "a", encoding="utf-8") as f:
            f.write(content)
        return _safe_result({"status": "ok", "path": full})
    except Exception as e:
        return _safe_result({"error": str(e)})


def list_dir(path: str = ".", depth: int = 3) -> str:
    full = _abs(path)
    try:
        tree: dict = {}

        def _walk(d: str, node: dict, cur_depth: int):
            if cur_depth > depth:
                return
            try:
                entries = sorted(os.listdir(d))
            except PermissionError:
                return
            for entry in entries:
                if entry == "__pycache__" or entry.endswith(".pyc"):
                    continue
                if entry.startswith(".") and entry not in (".env",):
                    continue
                ep = os.path.join(d, entry)
                if os.path.isdir(ep):
                    node[entry + "/"] = {}
                    _walk(ep, node[entry + "/"], cur_depth + 1)
                else:
                    node[entry] = f"{os.path.getsize(ep)} bytes"

        _walk(full, tree, 1)
        return _safe_result({"path": full, "tree": tree})
    except Exception as e:
        return _safe_result({"error": str(e)})


def create_dir(path: str) -> str:
    full = _abs(path)
    try:
        os.makedirs(full, exist_ok=True)
        return _safe_result({"status": "ok", "path": full})
    except Exception as e:
        return _safe_result({"error": str(e)})


def delete_file(path: str) -> str:
    full = _abs(path)
    try:
        if os.path.isdir(full):
            shutil.rmtree(full)
        else:
            os.remove(full)
        return _safe_result({"status": "ok", "deleted": full})
    except FileNotFoundError:
        return _safe_result({"error": f"Not found: {full}"})
    except Exception as e:
        return _safe_result({"error": str(e)})


def move_file(src: str, dst: str) -> str:
    src_full = _abs(src)
    dst_full = _abs(dst)
    try:
        os.makedirs(os.path.dirname(dst_full) or ".", exist_ok=True)
        shutil.move(src_full, dst_full)
        return _safe_result({"status": "ok", "from": src_full, "to": dst_full})
    except Exception as e:
        return _safe_result({"error": str(e)})


def run_command(command: str, cwd: str | None = None, timeout: int = 120) -> str:
    work_dir = _abs(cwd) if cwd else config.WORKING_DIR
    is_windows = platform.system() == "Windows"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            executable=None if is_windows else "/bin/bash",
        )
        return _safe_result({
            "returncode": result.returncode,
            "stdout": result.stdout[-8000:] if len(result.stdout) > 8000 else result.stdout,
            "stderr": result.stderr[-4000:] if len(result.stderr) > 4000 else result.stderr,
            "cwd": work_dir,
        })
    except subprocess.TimeoutExpired:
        return _safe_result({"error": f"Command timed out after {timeout}s"})
    except Exception as e:
        return _safe_result({"error": str(e)})


def search_web(query: str, max_results: int = 5) -> str:
    try:
        import urllib.parse
        import urllib.request

        encoded = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "do_it/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        results = []
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", ""),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
            })
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                    "snippet": topic["Text"],
                    "url": topic.get("FirstURL", ""),
                })
        return _safe_result({"query": query, "results": results[:max_results]})
    except Exception as e:
        return _safe_result({"error": str(e), "note": "Web search unavailable; proceed without it."})


def get_file_info(path: str) -> str:
    full = _abs(path)
    try:
        stat = os.stat(full)
        return _safe_result({
            "path": full,
            "exists": True,
            "is_file": os.path.isfile(full),
            "is_dir": os.path.isdir(full),
            "size_bytes": stat.st_size,
        })
    except FileNotFoundError:
        return _safe_result({"path": full, "exists": False})
    except Exception as e:
        return _safe_result({"error": str(e)})


def find_in_files(pattern: str, path: str = ".", file_ext: str = "") -> str:
    full = _abs(path)
    matches = []
    try:
        for root, dirs, files in os.walk(full):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git")]
            for fname in files:
                if file_ext and not fname.endswith(file_ext):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, encoding="utf-8", errors="replace") as f:
                        for i, line in enumerate(f, 1):
                            if pattern.lower() in line.lower():
                                matches.append({
                                    "file": os.path.relpath(fpath, full),
                                    "line": i,
                                    "text": line.rstrip(),
                                })
                                if len(matches) >= 50:
                                    break
                except Exception:
                    continue
                if len(matches) >= 50:
                    break
        return _safe_result({"pattern": pattern, "matches": matches, "total": len(matches)})
    except Exception as e:
        return _safe_result({"error": str(e)})


def copy_file(src: str, dst: str) -> str:
    src_full = _abs(src)
    dst_full = _abs(dst)
    try:
        os.makedirs(os.path.dirname(dst_full) or ".", exist_ok=True)
        shutil.copy2(src_full, dst_full)
        return _safe_result({"status": "ok", "from": src_full, "to": dst_full})
    except Exception as e:
        return _safe_result({"error": str(e)})


def patch_json(path: str, key_path: str, value: Any) -> str:
    full = _abs(path)
    try:
        with open(full, encoding="utf-8") as f:
            data = json.load(f)
        keys = key_path.split(".")
        node = data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        with open(full, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return _safe_result({"status": "ok", "path": full})
    except Exception as e:
        return _safe_result({"error": str(e)})


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file with optional line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file. Creates parent directories automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace the first occurrence of old_text with new_text in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Append text to end of a file (creates if not exists).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List directory contents as a tree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "depth": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_dir",
            "description": "Create a directory and all parents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory (recursive for directories).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                },
                "required": ["src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file from src to dst.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                },
                "required": ["src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command. Use for package installs, running scripts, git, build tools, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web via DuckDuckGo for docs, packages, examples, best practices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_info",
            "description": "Check if a path exists and get its metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_in_files",
            "description": "Search for a text pattern across all files in a directory (like grep).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                    "file_ext": {"type": "string", "description": "Filter by extension e.g. '.py', '.js'"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_json",
            "description": "Update a value inside a JSON file using a dot-separated key path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "key_path": {"type": "string", "description": "Dot-separated key path e.g. 'scripts.start'"},
                    "value": {"description": "New value (any JSON type)"},
                },
                "required": ["path", "key_path", "value"],
            },
        },
    },
]

TOOL_FUNCTIONS: dict[str, callable] = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "append_file": append_file,
    "list_dir": list_dir,
    "create_dir": create_dir,
    "delete_file": delete_file,
    "move_file": move_file,
    "copy_file": copy_file,
    "run_command": run_command,
    "search_web": search_web,
    "get_file_info": get_file_info,
    "find_in_files": find_in_files,
    "patch_json": patch_json,
}


def dispatch(name: str, args: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return fn(**args)
    except TypeError as e:
        return json.dumps({"error": f"Bad arguments for {name}: {e}"})
