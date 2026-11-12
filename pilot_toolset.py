"""The Pilot tool suite: focused tools over the core tmux engine.

The original ``pilot`` multi-action tool stays for compatibility. These
focused tools make common operations cheaper to call and add capabilities the
single tool never had: one-shot TTY runs, scripted expect sequences, scrollback
search, snapshots/diffs, pane logging, signals, file transfer and health.
"""

from __future__ import annotations

import difflib
import json
from typing import Any, Callable

from . import pilot_features as feat
from . import pilot_tmux as tmux
from .pilot_tools import TOOLSET, handle, tool_schema

TOOL_NAMES: list[str] = []
_SNAPSHOTS: dict[tuple[str, str], str] = {}


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _schema(name: str, description: str, props: dict, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": props,
            "required": required or [],
        },
    }


def _guard(fn: Callable[[dict], dict]) -> Callable[[dict], str]:
    def run(args: dict) -> str:
        try:
            return _json(fn(args or {}))
        except tmux.PilotError as exc:
            return _json({"ok": False, "error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive
            return _json({"ok": False, "error": f"pilot failed: {exc}"})

    return run


def _core(action: str, mapping: dict[str, str]) -> Callable[[dict], str]:
    def run(args: dict) -> str:
        payload = {"action": action}
        for source, target in mapping.items():
            if source in (args or {}):
                payload[target] = args[source]
        return handle(payload)

    return run


# ── core wrappers ────────────────────────────────────────────────────────
_OPEN_PROPS = {
    "command": {"type": "string", "description": "Command to run in the new TTY."},
    "name": {"type": "string", "description": "Session name (optional; auto s1, s2…)."},
    "cwd": {"type": "string"},
    "env": {"type": "object"},
    "cols": {"type": "integer"},
    "rows": {"type": "integer"},
    "wait_for": {"type": "string", "description": "Regex to wait for after opening."},
    "wait_ms": {"type": "integer"},
}
_NAME = {"name": {"type": "string", "description": "Session name."}}
_TYPE_PROPS = {
    **_NAME,
    "text": {"type": "string", "description": "Literal text to type."},
    "keys": {"type": "array", "items": {"type": "string"}, "description": "Named keys to press."},
    "enter": {"type": "boolean", "description": "Press Return after text/keys (default true)."},
}
_WAIT_PROPS = {
    **_NAME,
    "pattern": {"type": "string", "description": "Regex to wait for."},
    "timeout": {"type": "number"},
    "quiet_ms": {"type": "integer"},
    "lines": {"type": "integer"},
}


def _open(args: dict) -> str:
    return _core("open", {k: k for k in _OPEN_PROPS})(args)


def _screen(args: dict) -> str:
    return _core("screen", {k: k for k in ("name", "lines")})(args)


def _type(args: dict) -> str:
    return _core("type", {k: k for k in ("name", "text", "keys", "enter")})(args)


def _wait(args: dict) -> str:
    return _core("wait", {k: k for k in ("name", "pattern", "timeout", "quiet_ms", "lines")})(args)


def _list(_args: dict) -> str:
    return handle({"action": "list"})


def _status(args: dict) -> str:
    return _core("status", {"name": "name"})(args)


def _attach(args: dict) -> str:
    return _core("attach", {"name": "name"})(args)


def _close(args: dict) -> str:
    return _core("close", {"name": "name"})(args)


def _killall(_args: dict) -> str:
    return _json({"ok": True, "closed": tmux.close_all()})


# ── advanced handlers ────────────────────────────────────────────────────
def _run(args: dict) -> dict:
    result = feat.run_once(
        str(args.get("command") or ""),
        timeout=float(args.get("timeout") or 30),
        cols=int(args.get("cols") or tmux.DEFAULT_COLS),
        rows=int(args.get("rows") or tmux.DEFAULT_ROWS),
        cwd=str(args.get("cwd") or ""),
        env=args.get("env") if isinstance(args.get("env"), dict) else None,
        wait_for=str(args.get("wait_for") or ""),
        keep_open=bool(args.get("keep_open", False)),
    )
    result["output"] = result["output"][:12000]
    return result


def _expect(args: dict) -> dict:
    return feat.expect(
        str(args.get("name") or ""),
        args.get("steps") or [],
        timeout=float(args.get("timeout") or 20),
        lines=int(args.get("lines") or 200),
    )


def _search(args: dict) -> dict:
    return feat.search_screen(
        str(args.get("name") or ""),
        str(args.get("pattern") or ""),
        lines=int(args.get("lines") or 2000),
        context=int(args.get("context") or 2),
        max_hits=int(args.get("max_hits") or 20),
    )


def _diff(args: dict) -> dict:
    name = str(args.get("name") or "")
    slot = str(args.get("slot") or "default")
    mode = str(args.get("mode") or "diff").lower()
    key = (name, slot)
    if mode == "snapshot":
        text = tmux.screen(name, lines=int(args.get("lines") or 500))
        _SNAPSHOTS[key] = text
        return {"ok": True, "name": name, "slot": slot, "lines": len(text.splitlines())}
    if mode != "diff":
        raise tmux.PilotError("mode must be snapshot or diff")
    if key not in _SNAPSHOTS:
        raise tmux.PilotError(f"no snapshot {slot!r} for session {name!r}; run mode='snapshot' first")
    before = _SNAPSHOTS[key]
    after = tmux.screen(name, lines=int(args.get("lines") or 500))
    diff = list(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(), fromfile="before", tofile="after", lineterm="", n=2
        )
    )
    added = [line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")]
    removed = [line[1:] for line in diff if line.startswith("-") and not line.startswith("---")]
    body = "\n".join(diff)
    return {
        "ok": True,
        "name": name,
        "slot": slot,
        "changed": bool(diff),
        "added": len(added),
        "removed": len(removed),
        "diff": body[:12000],
    }


def _log(args: dict) -> dict:
    action = str(args.get("action") or "read").lower()
    name = str(args.get("name") or "")
    if action == "start":
        return {"ok": True, "path": feat.log_start(name, str(args.get("path") or ""))}
    if action == "stop":
        return {"ok": True, "path": feat.log_stop(name)}
    if action == "read":
        return feat.log_read(str(args.get("path") or ""), int(args.get("tail_bytes") or 20000))
    raise tmux.PilotError("log action must be start, stop or read")


def _signal(args: dict) -> dict:
    screen = feat.signal_session(str(args.get("name") or ""), str(args.get("signal") or "INT"))
    return {"ok": True, "name": args.get("name"), "signal": args.get("signal") or "INT", "screen": screen}


def _resize(args: dict) -> dict:
    name = str(args.get("name") or "")
    tmux.resize(name, int(args.get("cols") or tmux.DEFAULT_COLS), int(args.get("rows") or tmux.DEFAULT_ROWS))
    info = tmux.status(name)
    return {"ok": True, "name": name, "size": f"{info.cols}x{info.rows}" if info else ""}


def _rename(args: dict) -> dict:
    name = tmux.rename(str(args.get("name") or ""), str(args.get("new_name") or ""))
    return {"ok": True, "name": name, "attach": tmux.attach_command(name)}


def _health(_args: dict) -> dict:
    return feat.health()


def _upload(args: dict) -> dict:
    return feat.upload_file(
        str(args.get("name") or ""),
        str(args.get("local_path") or ""),
        str(args.get("remote_path") or ""),
        max_bytes=int(args.get("max_bytes") or feat.UPLOAD_LIMIT),
    )


def _download(args: dict) -> dict:
    return feat.download_file(
        str(args.get("name") or ""),
        str(args.get("remote_path") or ""),
        str(args.get("local_path") or ""),
        max_bytes=int(args.get("max_bytes") or feat.DOWNLOAD_LIMIT),
        timeout=float(args.get("timeout") or 30),
    )


def _cleanup(args: dict) -> dict:
    ttl = int(args.get("ttl") or 300)
    reaped = tmux.reap_dead(ttl_seconds=ttl)
    return {"ok": True, "reaped": reaped, "ttl": ttl}


def _send(args: dict) -> dict:
    screen = tmux.send(
        str(args.get("name") or ""),
        text=str(args.get("text") or ""),
        keys=args.get("keys") or [],
        enter=bool(args.get("enter", True)),
    )
    result = {"ok": True, "name": args.get("name"), "screen": screen}
    if args.get("wait_for"):
        waited = tmux.wait(
            str(args.get("name") or ""),
            str(args.get("wait_for") or ""),
            timeout=float(args.get("timeout") or 10),
            lines=int(args.get("lines") or 200),
        )
        result["matched"] = bool(waited.get("matched"))
        result["elapsed"] = waited.get("elapsed")
        result["screen"] = waited.get("screen", screen)
    return result


def _snapshot(args: dict) -> dict:
    name = str(args.get("name") or "")
    text = tmux.screen(name, lines=int(args.get("lines") or 500))
    dest = feat.safe_path(str(args.get("path") or ""), f"pilot-{name}.txt")
    dest.write_text(text + "\n", encoding="utf-8")
    return {
        "ok": True,
        "name": name,
        "path": str(dest.resolve()),
        "lines": len(text.splitlines()),
        "bytes": dest.stat().st_size,
    }


TOOL_SPECS: list[dict] = [
    {
        "name": "pilot",
        "description": "Drive a real interactive TTY: open, screen, type, wait, list, status, attach, close.",
        "schema": tool_schema(),
        "handler": lambda args: handle(args or {}),
        "emoji": "🕹️",
    },
    {
        "name": "pilot_open",
        "description": "Open a program in a new persistent TTY session; returns the first screen and attach command.",
        "schema": _schema("pilot_open", "Open a program in a new persistent TTY session.", _OPEN_PROPS, ["command"]),
        "handler": _guard(lambda args: json.loads(_open(args))),
    },
    {
        "name": "pilot_screen",
        "description": "Read a session's visible screen and scrollback as plain text.",
        "schema": _schema(
            "pilot_screen",
            "Read a session's visible screen and scrollback as plain text.",
            {**_NAME, "lines": {"type": "integer"}},
            ["name"],
        ),
        "handler": _guard(lambda args: json.loads(_screen(args))),
    },
    {
        "name": "pilot_type",
        "description": "Type literal text and named keys into a session.",
        "schema": _schema("pilot_type", "Type literal text and named keys into a session.", _TYPE_PROPS, ["name"]),
        "handler": _guard(lambda args: json.loads(_type(args))),
    },
    {
        "name": "pilot_wait",
        "description": "Wait for a regex in the screen, or for the pane to go quiet.",
        "schema": _schema("pilot_wait", "Wait for a regex or for the pane to settle.", _WAIT_PROPS, ["name"]),
        "handler": _guard(lambda args: json.loads(_wait(args))),
    },
    {
        "name": "pilot_list",
        "description": "List Pilot sessions with pid, command, size, dead state and exit status.",
        "schema": _schema("pilot_list", "List Pilot sessions.", {}),
        "handler": _guard(lambda args: json.loads(_list(args))),
    },
    {
        "name": "pilot_status",
        "description": "Get one session's status, including pane exit status.",
        "schema": _schema("pilot_status", "Get one session's status.", _NAME, ["name"]),
        "handler": _guard(lambda args: json.loads(_status(args))),
    },
    {
        "name": "pilot_attach",
        "description": "Return the command that attaches a human to the same pane.",
        "schema": _schema("pilot_attach", "Return the human attach command for a session.", _NAME, ["name"]),
        "handler": _guard(lambda args: json.loads(_attach(args))),
    },
    {
        "name": "pilot_close",
        "description": "Close one session.",
        "schema": _schema("pilot_close", "Close one session.", _NAME, ["name"]),
        "handler": _guard(lambda args: json.loads(_close(args))),
    },
    {
        "name": "pilot_killall",
        "description": "Close every Pilot session.",
        "schema": _schema("pilot_killall", "Close every Pilot session.", {}),
        "handler": _guard(lambda args: json.loads(_killall(args))),
    },
    {
        "name": "pilot_run",
        "description": "Run one command in a fresh TTY and return output, exit status and duration; closes it unless keep_open.",
        "schema": _schema(
            "pilot_run",
            "Run one command in a fresh TTY and capture its output.",
            {
                "command": {"type": "string"},
                "timeout": {"type": "number"},
                "cwd": {"type": "string"},
                "env": {"type": "object"},
                "cols": {"type": "integer"},
                "rows": {"type": "integer"},
                "wait_for": {"type": "string"},
                "keep_open": {"type": "boolean"},
            },
            ["command"],
        ),
        "handler": _guard(_run),
    },
    {
        "name": "pilot_expect",
        "description": "Script a sequence: wait for prompts, type answers, press keys, sleep. Returns a step trace.",
        "schema": _schema(
            "pilot_expect",
            "Script a sequence of wait/type/keys/sleep steps against a session.",
            {
                "name": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "object"}},
                "timeout": {"type": "number"},
                "lines": {"type": "integer"},
            },
            ["name", "steps"],
        ),
        "handler": _guard(_expect),
    },
    {
        "name": "pilot_search",
        "description": "Regex search the pane and scrollback; returns matching lines with context.",
        "schema": _schema(
            "pilot_search",
            "Search a pane's screen and scrollback.",
            {
                "name": {"type": "string"},
                "pattern": {"type": "string"},
                "lines": {"type": "integer"},
                "context": {"type": "integer"},
                "max_hits": {"type": "integer"},
            },
            ["name", "pattern"],
        ),
        "handler": _guard(_search),
    },
    {
        "name": "pilot_diff",
        "description": "Snapshot the screen, then diff the current screen against it.",
        "schema": _schema(
            "pilot_diff",
            "Snapshot a pane or diff it against a stored snapshot.",
            {
                "name": {"type": "string"},
                "mode": {"type": "string", "enum": ["snapshot", "diff"]},
                "slot": {"type": "string"},
                "lines": {"type": "integer"},
            },
            ["name"],
        ),
        "handler": _guard(_diff),
    },
    {
        "name": "pilot_log",
        "description": "Record a pane to a log file (start/stop) or read the tail.",
        "schema": _schema(
            "pilot_log",
            "Start, stop or read a pane recording.",
            {
                "name": {"type": "string"},
                "action": {"type": "string", "enum": ["start", "stop", "read"]},
                "path": {"type": "string"},
                "tail_bytes": {"type": "integer"},
            },
            ["name"],
        ),
        "handler": _guard(_log),
    },
    {
        "name": "pilot_signal",
        "description": "Send Ctrl-C, Ctrl-\\ or Ctrl-Z to the foreground program.",
        "schema": _schema(
            "pilot_signal",
            "Signal the foreground program in a pane.",
            {
                "name": {"type": "string"},
                "signal": {"type": "string", "enum": ["INT", "QUIT", "TSTP"]},
            },
            ["name"],
        ),
        "handler": _guard(_signal),
    },
    {
        "name": "pilot_resize",
        "description": "Resize a pane to new columns and rows.",
        "schema": _schema(
            "pilot_resize",
            "Resize a pane.",
            {
                "name": {"type": "string"},
                "cols": {"type": "integer"},
                "rows": {"type": "integer"},
            },
            ["name", "cols", "rows"],
        ),
        "handler": _guard(_resize),
    },
    {
        "name": "pilot_rename",
        "description": "Rename a session and return its new attach command.",
        "schema": _schema(
            "pilot_rename",
            "Rename a session.",
            {
                "name": {"type": "string"},
                "new_name": {"type": "string"},
            },
            ["name", "new_name"],
        ),
        "handler": _guard(_rename),
    },
    {
        "name": "pilot_health",
        "description": "Check tmux, the private socket, session counts and limits.",
        "schema": _schema("pilot_health", "Check Pilot and tmux health.", {}),
        "handler": _guard(_health),
    },
    {
        "name": "pilot_upload",
        "description": "Write a local file into the pane's shell via base64 (for SSH/remote sessions).",
        "schema": _schema(
            "pilot_upload",
            "Upload a local file into a shell session.",
            {
                "name": {"type": "string"},
                "local_path": {"type": "string"},
                "remote_path": {"type": "string"},
                "max_bytes": {"type": "integer"},
            },
            ["name", "local_path"],
        ),
        "handler": _guard(_upload),
    },
    {
        "name": "pilot_download",
        "description": "Read a file from the pane's shell via base64 and write it locally.",
        "schema": _schema(
            "pilot_download",
            "Download a file from a shell session.",
            {
                "name": {"type": "string"},
                "remote_path": {"type": "string"},
                "local_path": {"type": "string"},
                "max_bytes": {"type": "integer"},
                "timeout": {"type": "number"},
            },
            ["name", "remote_path"],
        ),
        "handler": _guard(_download),
    },
    {
        "name": "pilot_send",
        "description": "Type text/keys, then optionally wait for a pattern, in one call.",
        "schema": _schema(
            "pilot_send",
            "Type into a session and optionally wait for a pattern.",
            {
                "name": {"type": "string"},
                "text": {"type": "string"},
                "keys": {"type": "array", "items": {"type": "string"}},
                "enter": {"type": "boolean"},
                "wait_for": {"type": "string"},
                "timeout": {"type": "number"},
                "lines": {"type": "integer"},
            },
            ["name"],
        ),
        "handler": _guard(_send),
    },
    {
        "name": "pilot_snapshot",
        "description": "Write a pane's current screen to a text file.",
        "schema": _schema(
            "pilot_snapshot",
            "Save a pane's current screen to a text file.",
            {
                "name": {"type": "string"},
                "path": {"type": "string"},
                "lines": {"type": "integer"},
            },
            ["name"],
        ),
        "handler": _guard(_snapshot),
    },
    {
        "name": "pilot_cleanup",
        "description": "Reap finished sessions older than a TTL.",
        "schema": _schema(
            "pilot_cleanup",
            "Reap finished Pilot sessions.",
            {"ttl": {"type": "integer"}},
        ),
        "handler": _guard(_cleanup),
    },
]

TOOL_NAMES = [spec["name"] for spec in TOOL_SPECS]

__all__ = ["TOOLSET", "TOOL_NAMES", "TOOL_SPECS"]
