"""``hermes pilot`` CLI and the ``/pilot`` slash command."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Any

from . import pilot_tmux as tmux


def _table(sessions: list[tmux.SessionInfo]) -> str:
    if not sessions:
        return "pilot · no live sessions\n  The agent opens one with the `pilot` tool (action='open')."
    rows = [f"pilot · {len(sessions)} session(s)", ""]
    rows.append(f"{'name':<14} {'command':<16} {'pid':<8} {'size':<9} {'state':<6} attach")
    rows.append("-" * 96)
    for info in sessions:
        state = "dead" if info.dead else "live"
        rows.append(
            f"{info.name[:14]:<14} {info.command[:16]:<16} {str(info.pid or ''):<8} "
            f"{f'{info.cols}x{info.rows}':<9} {state:<6} {tmux.attach_command(info.name)}"
        )
    return "\n".join(rows)


def _run_hermes(argv: list[str]) -> str:
    try:
        proc = subprocess.run(["hermes", *argv], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"pilot: could not run `hermes {' '.join(argv)}`: {exc}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return out or f"(exit {proc.returncode})"


def backend_status() -> str:
    """Report whether the normal terminal tool runs in Pilot."""
    current = _run_hermes(["config", "get", "terminal.backend"])
    return (
        "pilot backend\n"
        f"  terminal.backend : {current.splitlines()[0] if current else '(unset)'}\n"
        f"  tmux             : {'found' if tmux.available() else 'missing'}\n"
        "  on               : hermes pilot backend on\n"
        "  off              : hermes pilot backend off"
    )


def _set_backend(value: str) -> str:
    out = _run_hermes(["config", "set", "terminal.backend", value])
    return (
        f"{out}\n\nNew sessions use the {value} backend. If Hermes is already running, restart it "
        "once (hermes gateway restart, from a terminal outside the agent) so the plugin's backend "
        "is registered in that process. This session keeps the backend it started with."
    )


def handle_slash(raw_args: str = "") -> str:
    args = (raw_args or "").strip().split()
    action = args[0].lower() if args else "list"
    sessions = tmux.list_sessions()
    if action in {"list", "ls"}:
        return _table(sessions)
    if action == "backend":
        return backend_status()
    if action in {"screen", "show"}:
        if len(args) < 2:
            return "usage: /pilot screen <name>"
        try:
            return tmux.screen(args[1], lines=int(args[2]) if len(args) > 2 else 60)
        except tmux.PilotError as exc:
            return f"pilot: {exc}"
    if action in {"attach", "watch"}:
        if len(args) < 2:
            return "usage: /pilot attach <name>"
        return f"attach from a real terminal:\n  {tmux.attach_command(args[1])}\n\ndetach with Ctrl-b then d"
    if action in {"kill", "close"}:
        if len(args) < 2:
            return "usage: /pilot kill <name>"
        ok = tmux.close(args[1])
        return f"pilot: closed {args[1]}" if ok else f"pilot: no session {args[1]!r}"
    return "usage: /pilot [list|screen <name>|attach <name>|kill <name>|backend]"


def setup_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        nargs="?",
        default="list",
        choices=["list", "screen", "attach", "kill", "killall", "backend"],
        help="list (default), screen, attach, kill, killall, backend",
    )
    parser.add_argument("name", nargs="?", default="", help="Session name, or on/off/status for backend")
    parser.add_argument("--lines", type=int, default=60, help="Scrollback lines for screen")
    parser.set_defaults(func=handle_cli)


def handle_cli(args: Any) -> int:
    action = str(getattr(args, "action", "list") or "list").lower()
    name = str(getattr(args, "name", "") or "")

    if action == "backend":
        choice = (name or "status").lower()
        if choice in {"on", "pilot", "enable"}:
            print(_set_backend("pilot"))
            return 0
        if choice in {"off", "local", "disable"}:
            print(_set_backend("local"))
            return 0
        print(backend_status())
        return 0

    if not tmux.available():
        print("pilot: tmux is not installed (needed for sessions and the terminal backend)")
        return 1

    if action == "list":
        print(_table(tmux.list_sessions()))
        return 0

    if action == "screen":
        if not name:
            print("usage: hermes pilot screen <name> [--lines N]")
            return 2
        try:
            print(tmux.screen(name, lines=int(getattr(args, "lines", 60) or 60)))
            return 0
        except tmux.PilotError as exc:
            print(f"pilot: {exc}")
            return 1

    if action == "attach":
        if not name:
            print("usage: hermes pilot attach <name>")
            return 2
        if tmux.status(name) is None:
            print(f"pilot: no session {name!r}")
            return 1
        command = ["tmux", "-L", tmux.socket_name(), "attach", "-t", name]
        if not sys.stdin.isatty():
            print(" ".join(command))
            return 0
        os.execvp("tmux", command)
        return 0  # unreachable

    if action == "kill":
        if not name:
            print("usage: hermes pilot kill <name>")
            return 2
        ok = tmux.close(name)
        print(f"pilot: closed {name}" if ok else f"pilot: no session {name!r}")
        return 0 if ok else 1

    if action == "killall":
        count = tmux.close_all()
        print(f"pilot: closed {count} session(s)")
        return 0

    print(f"unknown action {action!r}")
    return 2


__all__ = ["handle_cli", "handle_slash", "setup_cli"]
