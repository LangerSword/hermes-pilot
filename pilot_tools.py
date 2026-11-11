"""The ``pilot`` tool: drive a real interactive terminal.

Toolset ``pilot``. One tool, eight actions. Every action returns compact JSON;
the ``screen`` field is what a human would see in the pane, so the model reads
the terminal instead of guessing what a program is showing.
"""

from __future__ import annotations

import json
from typing import Any

from . import pilot_tmux as tmux

TOOLSET = "pilot"
TOOL_NAME = "pilot"
MAX_SCREEN_FOR_MODEL = 12_000

_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Drive a real interactive terminal (a TTY) — for programs that need keystrokes, not pipes: "
        "ssh logins, vim/nano, htop/btop, fzf, less, package installers, REPLs, ncurses menus, "
        "gh auth prompts. Sessions live in a private tmux server and persist across tool calls. "
        "Loop: action='open' (command, optional wait_for), action='screen' to see the pane, "
        "action='type' to send text/keys, action='wait' until a pattern appears or output goes quiet, "
        "action='close' when done. Examples: vim — open `vim /tmp/x.txt`, type 'i', text, keys "
        "['Escape'], then type ':wq' with enter=true; REPL — open `python3 -q`, type 'x=41', then 'x+1'. "
        "Use action='attach' to get the command that lets the human watch or take over the same pane. "
        "Prefer the normal terminal tool for one-shot non-interactive commands."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["open", "type", "screen", "wait", "list", "status", "close", "attach"],
                "description": "Which pilot operation to run.",
            },
            "command": {
                "type": "string",
                "description": "For action='open': the command to run in the new TTY, e.g. 'ssh me@host', 'vim notes.md', 'htop'.",
            },
            "name": {
                "type": "string",
                "description": "Session name (letters/digits/_/-). Optional for open (auto s1, s2, …).",
            },
            "cwd": {"type": "string", "description": "Working directory for action='open'."},
            "env": {
                "type": "object",
                "description": "Extra environment variables for action='open' (string values).",
            },
            "cols": {"type": "integer", "description": "Terminal width for action='open' (default 120)."},
            "rows": {"type": "integer", "description": "Terminal height for action='open' (default 36)."},
            "wait_for": {
                "type": "string",
                "description": "Regex to wait for after opening, e.g. '[$#] $' or 'Password:'.",
            },
            "wait_ms": {
                "type": "integer",
                "description": "How long to wait after opening, in ms (default 1500).",
            },
            "text": {
                "type": "string",
                "description": "For action='type': literal text to type into the pane.",
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Named keys to press after the text, e.g. ['Escape'], ['C-c'], ['Up','Enter'], ['Tab'].",
            },
            "enter": {
                "type": "boolean",
                "description": "For action='type': press Enter after text/keys (default true). Set false when typing inside vim insert mode.",
            },
            "pattern": {
                "type": "string",
                "description": "For action='wait': regex to wait for in the screen, e.g. 'hello|error|\\\\$ $'.",
            },
            "timeout": {
                "type": "number",
                "description": "For action='wait': seconds before giving up (default 20).",
            },
            "quiet_ms": {
                "type": "integer",
                "description": "For action='wait' without a pattern: consider the pane settled after this much unchanged time (default 700).",
            },
            "lines": {
                "type": "integer",
                "description": "For action='screen'/'wait': how many scrollback lines to include (default 100).",
            },
        },
        "required": ["action"],
    },
}


def tool_schema() -> dict:
    return _SCHEMA


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _cap(text: str, limit: int = MAX_SCREEN_FOR_MODEL) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… [screen truncated; use action='screen' with smaller lines]"


def _brief(info: tmux.SessionInfo) -> dict:
    return {
        "name": info.name,
        "command": info.command,
        "pid": info.pid,
        "dead": info.dead,
        "exit_status": info.exit_status,
        "size": f"{info.cols}x{info.rows}",
    }


def handle(args: dict) -> str:
    action = str((args or {}).get("action") or "").strip().lower()
    try:
        if action == "open":
            info = tmux.open_session(
                str(args.get("command") or ""),
                name=str(args.get("name") or ""),
                cwd=str(args.get("cwd") or ""),
                env=args.get("env") if isinstance(args.get("env"), dict) else None,
                cols=int(args.get("cols") or tmux.DEFAULT_COLS),
                rows=int(args.get("rows") or tmux.DEFAULT_ROWS),
                wait_for=str(args.get("wait_for") or ""),
                wait_ms=int(args.get("wait_ms") or 1500),
            )
            return _json(
                {
                    "ok": True,
                    "session": _brief(info),
                    "attach": tmux.attach_command(info.name),
                    "screen": _cap(tmux.screen(info.name, lines=60)),
                }
            )

        if action == "type":
            name = str(args.get("name") or "")
            text = tmux.send(
                name,
                text=str(args.get("text") or ""),
                keys=args.get("keys") or [],
                enter=bool(args.get("enter", True)),
            )
            return _json({"ok": True, "name": name, "screen": _cap(text)})

        if action == "screen":
            name = str(args.get("name") or "")
            return _json(
                {
                    "ok": True,
                    "name": name,
                    "screen": _cap(tmux.screen(name, lines=int(args.get("lines") or 100))),
                }
            )

        if action == "wait":
            result = tmux.wait(
                str(args.get("name") or ""),
                pattern=str(args.get("pattern") or ""),
                timeout=float(args.get("timeout") or 20),
                quiet_ms=int(args.get("quiet_ms") or 700),
                lines=int(args.get("lines") or 100),
            )
            result["ok"] = True
            result["screen"] = _cap(result.pop("screen", ""))
            return _json(result)

        if action == "list":
            sessions = [_brief(info) for info in tmux.list_sessions()]
            return _json({"ok": True, "count": len(sessions), "sessions": sessions})

        if action == "status":
            info = tmux.status(str(args.get("name") or ""))
            if info is None:
                return _json({"ok": False, "error": "no such session"})
            return _json({"ok": True, "session": _brief(info)})

        if action == "close":
            closed = tmux.close(str(args.get("name") or ""))
            return _json({"ok": True, "closed": closed})

        if action == "attach":
            name = str(args.get("name") or "")
            tmux.validate_name(name)
            if tmux.status(name) is None:
                return _json({"ok": False, "error": "no such session"})
            return _json(
                {
                    "ok": True,
                    "command": tmux.attach_command(name),
                    "hint": "Run that in a real terminal to watch live; detach with Ctrl-b then d. "
                    "Anything you type there is visible to the agent's next screen read.",
                }
            )

        return _json({"ok": False, "error": f"unknown action {action!r}"})
    except tmux.PilotError as exc:
        return _json({"ok": False, "error": str(exc)})
    except Exception as exc:  # pragma: no cover - defensive
        return _json({"ok": False, "error": f"pilot failed: {exc}"})


__all__ = ["TOOLSET", "TOOL_NAME", "handle", "tool_schema"]
