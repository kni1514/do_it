from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

if sys.platform == "win32":
    import ctypes
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.align import Align
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

import config
from agent.core import Agent

HOME_DIR = os.path.expanduser("~")

console = Console(highlight=False)

PROMPT_STYLE = Style.from_dict({
    "prompt": "ansibrightcyan bold",
    "": "ansiwhite",
})

def print_banner():
    content = Text("do_it\n", style="bold bright_cyan", justify="center")
    content.append("Terminal AI Coding Agent\n", style="bold white")
    content.append("Powered by ChatGPT · Kni-org\n", style="cyan")
    content.append(f"\nWorking in {config.WORKING_DIR}", style="dim")
    console.print(Align.center(Panel(content, border_style="cyan", padding=(1, 4), expand=False)))
    console.print(Align.center(Text("help  ·  clear  ·  exit", style="dim yellow")))
    console.print()


def _bridge_is_ready() -> bool:
    request = urllib.request.Request(config.BRIDGE_URL + "/query")
    try:
        with urllib.request.urlopen(request, timeout=0.5) as response:
            return response.status in (200, 204)
    except urllib.error.HTTPError as error:
        return error.code in (200, 204)
    except (urllib.error.URLError, TimeoutError):
        return False


def start_bridge() -> subprocess.Popen | None:
    if _bridge_is_ready():
        return None

    server_path = os.path.join(SCRIPT_DIR, "server", "app.py")
    process = subprocess.Popen(
        [sys.executable, server_path],
        cwd=SCRIPT_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "The local ChatGPT server stopped during startup. Install dependencies with: pip install -r requirements.txt"
            )
        if _bridge_is_ready():
            return process
        time.sleep(0.2)

    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    raise RuntimeError("The local ChatGPT server did not start on 127.0.0.1:1514.")


def stop_bridge(process: subprocess.Popen | None):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def print_help():
    console.print(Panel(
        "[bold]do_it[/bold] — Terminal AI Coding Agent by [bold cyan]Kni-org[/bold cyan]\n\n"
        "[cyan]Built-in commands:[/cyan]\n"
        "  [yellow]help[/yellow]  [yellow]?[/yellow]        Show this help\n"
        "  [yellow]clear[/yellow]          Clear screen\n"
        "  [yellow]exit[/yellow]  [yellow]quit[/yellow]  [yellow]q[/yellow]  Exit\n\n"
        "[cyan]What you can ask:[/cyan]\n"
        '  "build a FastAPI REST API for a todo app with SQLite"\n'
        '  "create a CLI tool with click and typer"\n'
        '  "scaffold a Next.js + TypeScript project with Tailwind"\n'
        '  "write and run tests for main.py"\n'
        '  "find and fix the bug in app.py"\n'
        '  "set up Docker Compose with nginx + postgres + redis"\n'
        '  "refactor this project to use async/await throughout"\n\n'
        "[cyan]Navigation:[/cyan]\n"
        "  [dim]↑ / ↓ arrows[/dim]  Browse input history\n"
        "  [dim]→ arrow[/dim]       Accept auto-suggestion\n",
        title="[bold cyan]do_it  ·  Kni-org[/bold cyan]",
        border_style="cyan",
    ))


def print_response(text: str):
    if not text.strip():
        return
    console.print()
    console.print(Rule(style="dim"))
    try:
        console.print(Markdown(text))
    except Exception:
        console.print(text)
    console.print(Rule(style="dim"))
    console.print()


def run_repl(agent: Agent, initial_prompt: str | None = None):
    os.makedirs(config.SESSION_DIR, exist_ok=True)
    history_path = os.path.join(config.SESSION_DIR, "input_history.txt")
    session: PromptSession = PromptSession(
        history=FileHistory(history_path),
        auto_suggest=AutoSuggestFromHistory(),
        style=PROMPT_STYLE,
        mouse_support=False,
    )

    if initial_prompt:
        console.print(f"\n[bold cyan]▶[/bold cyan] [white]{initial_prompt}[/white]\n")
        response = agent.run(initial_prompt)
        print_response(response)

    while True:
        try:
            user_input = session.prompt(
                [("class:prompt", "\n◆ do_it > ")],
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n\n[dim]Session saved. Goodbye.[/dim]\n")
            break

        if not user_input:
            continue

        lower = user_input.lower()

        if lower in ("exit", "quit", "q", ":q"):
            console.print("\n[dim]Session saved. Goodbye.[/dim]\n")
            break

        if lower in ("help", "?"):
            print_help()
            continue

        if lower == "clear":
            os.system("cls" if sys.platform == "win32" else "clear")
            continue

        console.print()
        try:
            response = agent.run(user_input)
            print_response(response)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Enter a new prompt to continue.[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Unexpected error: {e}[/red]")


def main():
    parser = argparse.ArgumentParser(
        prog="do_it",
        description="do_it — Terminal AI Coding Agent by Kni-org",
    )
    parser.add_argument("prompt", nargs="?", help="Run a single prompt non-interactively")
    parser.add_argument("--version", action="version", version="do_it  v1.0  ·  Kni-org")
    args = parser.parse_args()

    bridge_process = None
    try:
        bridge_process = start_bridge()
        print_banner()
        agent = Agent()

        if args.prompt:
            console.print(f"[bold cyan]▶[/bold cyan] [white]{args.prompt}[/white]\n")
            response = agent.run(args.prompt)
            print_response(response)
            agent.memory.save()
        else:
            run_repl(agent)
    except RuntimeError as error:
        console.print(f"[red]{error}[/red]")
        return 1
    finally:
        stop_bridge(bridge_process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
