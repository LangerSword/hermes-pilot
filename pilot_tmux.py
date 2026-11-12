"""tmux-backed interactive terminal for the pilot plugin.

The agent gets a real TTY (not a pipe): curses programs render, `ssh` prompts,
`vim` takes keystrokes, a REPL keeps its state between tool calls. Every
session lives on a private tmux server scoped to the active Hermes profile, so
Pilot never touches the user's own tmux sessions.

Stdlib only; tmux must be installed. Nothing here imports Hermes internals.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Iterable


def socket_name(home: str | None = None) -> str:
    """The private tmux socket for the current profile, resolved per call.

    Hermes multiplexes profiles in one process, so this must not be cached at
    import time. ``get_hermes_home()`` is context-local and changes per turn.
    """
    if home is None:
        try:
            from hermes_constants import get_hermes_home

            home = str(get_hermes_home())
        except Exception:
            home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    digest = hashlib.sha256(os.path.abspath(home).encode()).hexdigest()[:8]
    return f"hermes-pilot-{digest}"


DEFAULT_COLS = 120
DEFAULT_ROWS = 36
MAX_SCREEN_CHARS = 20_000
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")

# Panes inherit this, not the agent's environment. Provider keys, adapter
# tokens and other secrets must never reach a model-authored command.
_MINIMAL_ENV_KEYS = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "LANG", "TZ",
    "TMPDIR", "XDG_RUNTIME_DIR", "TMUX_TMPDIR", "PWD",
)


def minimal_env() -> dict[str, str]:
    """The only environment a pane inherits from Hermes."""
    env = {key: os.environ[key] for key in _MINIMAL_ENV_KEYS if os.environ.get(key)}
    for key, value in os.environ.items():
        if key.startswith("LC_") and len(key) <= 12:
            env[key] = value
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.setdefault("HOME", os.path.expanduser("~"))
    env.setdefault("SHELL", "/bin/sh")
    env.setdefault("TERM", "xterm-256color")
    env["TMUX"] = ""  # never inherit an outer client state
    return env


def _allowed_env_key(key: str) -> bool:
    return key in _MINIMAL_ENV_KEYS or key.startswith("LC_")


def _sanitize_server_env() -> None:
    """Remove inherited secrets from an already-running tmux server."""
    proc = _tmux(["show-environment", "-g"])
    if proc.returncode != 0:
        return
    for line in proc.stdout.splitlines():
        raw = line.strip()
        if not raw:
            continue
        key = raw.split("=", 1)[0].lstrip("-")
        if key and not _allowed_env_key(key):
            _tmux(["set-environment", "-g", "-u", key])
    for key, value in minimal_env().items():
        if key != "TMUX":
            _tmux(["set-environment", "-g", key, value])

# Named keys the model may send. Anything else must be plain text.
NAMED_KEYS = frozenset(
    {
        "Enter", "Escape", "Tab", "BTab", "Space", "BSpace", "DC", "IC",
        "Up", "Down", "Left", "Right", "Home", "End", "PPage", "NPage",
        "C-a", "C-b", "C-c", "C-d", "C-e", "C-g", "C-h", "C-k", "C-l",
        "C-n", "C-o", "C-p", "C-q", "C-r", "C-s", "C-t", "C-u", "C-v",
        "C-w", "C-x", "C-y", "C-z", "F1", "F2", "F3", "F4", "F5", "F6",
        "F7", "F8", "F9", "F10", "F11", "F12",
    }
)


class PilotError(RuntimeError):
    """A user-facing pilot failure (bad name, missing session, no tmux)."""


@dataclass(frozen=True)
class SessionInfo:
    name: str
    pid: int | None
    command: str
    dead: bool
    cols: int
    rows: int
    created: int
    exit_status: int | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "pid": self.pid,
            "command": self.command,
            "dead": self.dead,
            "size": f"{self.cols}x{self.rows}",
            "created": self.created,
            "exit_status": self.exit_status,
        }


def available() -> bool:
    return shutil.which("tmux") is not None


def _tmux(args: Iterable[str], timeout: float = 15.0, check: bool = False) -> subprocess.CompletedProcess:
    if not available():
        raise PilotError("tmux is not installed (pilot needs it for a real TTY)")
    try:
        proc = subprocess.run(
            ["tmux", "-L", socket_name(), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=minimal_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise PilotError(f"tmux timed out after {timeout:.0f}s") from exc
    if check and proc.returncode != 0:
        raise PilotError((proc.stderr or proc.stdout or "tmux failed").strip())
    return proc


def _server_up() -> bool:
    return _tmux(["list-sessions"], check=False).returncode == 0


def validate_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_RE.match(name):
        raise PilotError(
            "session name must be 1-32 chars of letters, digits, '_' or '-', starting with a letter or digit"
        )
    return name


def list_sessions() -> list[SessionInfo]:
    if not available() or not _server_up():
        return []
    proc = _tmux(["list-sessions", "-F", "#{session_name}\t#{session_created}"])
    if proc.returncode != 0:
        return []
    out: list[SessionInfo] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        name, _, created = line.partition("\t")
        info = status(name.strip())
        if info is not None:
            out.append(
                SessionInfo(
                    name=info.name,
                    pid=info.pid,
                    command=info.command,
                    dead=info.dead,
                    cols=info.cols,
                    rows=info.rows,
                    created=int(created or 0),
                )
            )
    return out


def status(name: str) -> SessionInfo | None:
    name = validate_name(name)
    if not available():
        return None
    fmt = (
        "#{pane_pid}\t#{pane_current_command}\t#{pane_dead}\t#{pane_width}\t#{pane_height}"
        "\t#{pane_dead_status}"
    )
    proc = _tmux(["list-panes", "-t", name, "-F", fmt])
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    first = proc.stdout.splitlines()[0]
    pid_s, cmd, dead_s, cols_s, rows_s, exit_s = (first.split("\t") + [""] * 6)[:6]
    try:
        pid = int(pid_s)
    except ValueError:
        pid = None
    try:
        exit_status = int(exit_s) if exit_s.strip() else None
    except ValueError:
        exit_status = None
    return SessionInfo(
        name=name,
        pid=pid,
        command=cmd or "",
        dead=dead_s.strip() == "1",
        cols=int(cols_s or DEFAULT_COLS),
        rows=int(rows_s or DEFAULT_ROWS),
        created=0,
        exit_status=exit_status,
    )


def next_name(prefix: str = "s") -> str:
    used = {s.name for s in list_sessions()}
    for i in range(1, 100):
        candidate = f"{prefix}{i}"
        if candidate not in used:
            return candidate
    raise PilotError("too many pilot sessions; close one first")


def open_session(
    command: str,
    *,
    name: str = "",
    cwd: str = "",
    env: dict | None = None,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    wait_for: str = "",
    wait_ms: int = 1500,
) -> SessionInfo:
    """Start ``command`` in a detached tmux pane and return its status."""
    if not (command or "").strip():
        raise PilotError("open needs a command")
    name = validate_name(name) if name else next_name()
    _ensure_no_duplicate(name)
    if _server_up():
        _sanitize_server_env()
    reap_dead()
    cols = max(20, min(int(cols or DEFAULT_COLS), 400))
    rows = max(5, min(int(rows or DEFAULT_ROWS), 200))

    create = ["new-session", "-d", "-s", name, "-x", str(cols), "-y", str(rows)]
    if cwd:
        create += ["-c", str(cwd)]
    for key, value in (env or {}).items():
        if key and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(key)):
            create += ["-e", f"{key}={value}"]
    create += ["--", "sh", "-c", command]

    # Set the server options BEFORE the pane exists, so even a command that exits
    # immediately leaves its final screen readable (and its exit status visible).
    prefix = [
        "set-option", "-g", "history-limit", "20000", ";",
        "set-option", "-g", "remain-on-exit", "on", ";",
    ]
    proc = _tmux(prefix + ["set-option", "-g", "remain-on-exit-format", "", ";"] + create)
    if proc.returncode != 0:
        # Older tmux without remain-on-exit-format: same chain, no dead-pane banner suppression.
        proc = _tmux(prefix + create)
    if proc.returncode != 0:
        raise PilotError((proc.stderr or proc.stdout or "tmux new-session failed").strip())

    _tmux(["set-option", "-t", name, "status", "off"])

    if wait_ms > 0:
        wait(name, pattern=wait_for, timeout=max(0.2, wait_ms / 1000), quiet_ms=250)
    info = status(name)
    if info is None:
        raise PilotError(f"session {name!r} did not start")
    return info


def _ensure_no_duplicate(name: str) -> None:
    if status(name) is not None:
        raise PilotError(f"session {name!r} already exists; close it or pick another name")


def trim_screen(text: str, max_chars: int = MAX_SCREEN_CHARS) -> str:
    """Strip trailing spaces, dead-pane banners, and leading/trailing blank lines."""
    lines = []
    for line in (text or "").replace("\r", "").splitlines():
        cleaned = line.rstrip()
        if re.match(r"^Pane is dead \(status .*\)$", cleaned.strip()):
            continue
        lines.append(cleaned)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[:max_chars] + "\n… [screen truncated]"
    return body


def screen(name: str, lines: int = 100, include_history: bool = True) -> str:
    """Return the visible screen (plus scrollback up to *lines*), as plain text."""
    name = validate_name(name)
    if status(name) is None:
        raise PilotError(f"no pilot session named {name!r}")
    args = ["capture-pane", "-p", "-J", "-t", name]
    if include_history and lines:
        args += ["-S", f"-{max(1, min(int(lines), 5000))}"]
    proc = _tmux(args, check=True)
    return trim_screen(proc.stdout)


def _check_keys(keys: Iterable[str]) -> list[str]:
    out = []
    for key in keys:
        key = str(key)
        if key in NAMED_KEYS:
            out.append(key)
        elif len(key) == 1:
            out.append(key)
        else:
            raise PilotError(f"unknown key {key!r}; use a single character or one of the named keys")
    return out


def send(name: str, text: str = "", keys: Iterable[str] | None = None, enter: bool = True) -> str:
    """Type *text* literally, press named *keys*, then Return by default."""
    name = validate_name(name)
    if status(name) is None:
        raise PilotError(f"no pilot session named {name!r}")
    if text:
        _tmux(["send-keys", "-t", name, "-l", "--", text], check=True)
    for key in _check_keys(keys or []):
        _tmux(["send-keys", "-t", name, key], check=True)
    if enter:
        _tmux(["send-keys", "-t", name, "Enter"], check=True)
    return screen(name, lines=40)


def wait(
    name: str,
    pattern: str = "",
    *,
    timeout: float = 20.0,
    quiet_ms: int = 700,
    lines: int = 100,
) -> dict:
    """Poll the screen until *pattern* matches or output goes quiet."""
    name = validate_name(name)
    deadline = time.monotonic() + max(0.2, float(timeout or 20))
    compiled = re.compile(pattern, re.M) if pattern else None
    last = ""
    stable_since = time.monotonic()
    started = time.monotonic()
    while True:
        current = screen(name, lines=lines)
        if current != last:
            last = current
            stable_since = time.monotonic()
        matched = bool(compiled.search(current)) if compiled else False
        if matched:
            return {
                "name": name,
                "matched": True,
                "pattern": pattern,
                "elapsed": round(time.monotonic() - started, 2),
                "screen": current,
            }
        # An empty pane is not "settled" — it means the program has not painted yet.
        if (
            compiled is None
            and current.strip()
            and (time.monotonic() - stable_since) * 1000 >= max(100, quiet_ms)
        ):
            return {
                "name": name,
                "matched": False,
                "stable": True,
                "elapsed": round(time.monotonic() - started, 2),
                "screen": current,
            }
        if time.monotonic() >= deadline:
            return {
                "name": name,
                "matched": False,
                "timed_out": True,
                "pattern": pattern,
                "elapsed": round(time.monotonic() - started, 2),
                "screen": current,
            }
        time.sleep(0.12)


DEAD_REAP_TTL = 300  # seconds a finished pane is kept before an open reaps it


def reap_dead(ttl_seconds: int = DEAD_REAP_TTL) -> int:
    """Close finished panes nobody has read for a while. Best effort, never raises."""
    try:
        if not available() or not _server_up():
            return 0
        proc = _tmux(["list-sessions", "-F", "#{session_name}\t#{session_activity}"])
        if proc.returncode != 0:
            return 0
        now = time.time()
        killed = 0
        for line in proc.stdout.splitlines():
            name, _, activity = line.partition("\t")
            info = status(name.strip()) if name.strip() else None
            if info is None or not info.dead:
                continue
            try:
                idle = now - int(activity or 0)
            except ValueError:
                idle = 0
            if idle >= ttl_seconds and close(info.name):
                killed += 1
        return killed
    except Exception:
        return 0


def close(name: str, *, missing_ok: bool = True) -> bool:
    name = validate_name(name)
    proc = _tmux(["kill-session", "-t", name])
    if proc.returncode != 0:
        if missing_ok:
            return False
        raise PilotError(f"no pilot session named {name!r}")
    return True


def close_all() -> int:
    sessions = list_sessions()
    for info in sessions:
        close(info.name)
    return len(sessions)


def attach_command(name: str) -> str:
    """The exact shell command a human runs to watch or take over the pane."""
    return f"tmux -L {socket_name()} attach -t {validate_name(name)}"


def rename(name: str, new_name: str) -> str:
    name, new_name = validate_name(name), validate_name(new_name)
    if status(new_name) is not None:
        raise PilotError(f"session {new_name!r} already exists")
    _tmux(["rename-session", "-t", name, new_name], check=True)
    return new_name


def resize(name: str, cols: int, rows: int) -> None:
    name = validate_name(name)
    cols = max(20, min(int(cols), 400))
    rows = max(5, min(int(rows), 200))
    _tmux(["resize-window", "-t", name, "-x", str(cols), "-y", str(rows)], check=True)


__all__ = [
    "PilotError",
    "SessionInfo",
    "socket_name",
    "available",
    "attach_command",
    "close",
    "close_all",
    "list_sessions",
    "minimal_env",
    "next_name",
    "open_session",
    "reap_dead",
    "resize",
    "screen",
    "send",
    "status",
    "trim_screen",
    "validate_name",
    "wait",
]
