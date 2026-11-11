"""``hermes pilot`` CLI and the ``/pilot`` slash command."""

from __future__ import annotations

import argparse
import os
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


def handle_slash(raw_args: str = "") -> str:
    args = (raw_args or "").strip().split()
    action = args[0].lower() if args else "list"
    sessions = tmux.list_sessions()
    if action in {"list", "ls"}:
        return _table(sessions)
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
    return "usage: /pilot [list|screen <name>|attach <name>|kill <name>]"


def setup_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        nargs="?",
        default="list",
        choices=["list", "screen", "attach", "kill", "killall"],
        help="list (default), screen, attach, kill, killall",
    )
    parser.add_argument("name", nargs="?", default="", help="Session name")
    parser.add_argument("--lines", type=int, default=60, help="Scrollback lines for screen")
    parser.set_defaults(func=handle_cli)


def handle_cli(args: Any) -> int:
    action = str(getattr(args, "action", "list") or "list").lower()
    name = str(getattr(args, "name", "") or "")

    if not tmux.available():
        print("pilot: tmux is not installed")
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
        command = ["tmux", "-L", tmux.SOCKET, "attach", "-t", name]
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
