"""Higher-level Pilot features built on the tmux primitives.

These are the operations that make a TTY useful beyond open/screen/type:
one-shot TTY runs, scripted expect sequences, scrollback search, pane logging,
file transfer through the pane, and health checks. Stdlib only.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import shlex
import time
from pathlib import Path
from typing import Any

from . import pilot_tmux as tmux

PLUGIN_NAME = "pilot"
_DATA_ROOT: Path | None = None
UPLOAD_LIMIT = 256 * 1024
DOWNLOAD_LIMIT = 256 * 1024
_LOG_PATHS: dict[str, Path] = {}
_SHELLS = {"bash", "zsh", "sh", "fish", "dash", "ksh", "ssh"}
_DENIED_NAMES = {
    ".env", ".netrc", ".git-credentials", "credentials", "authorized_keys",
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
}
_DENIED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


def data_dir() -> Path:
    """Pilot's per-profile data dir, or a test override."""
    if _DATA_ROOT is not None:
        _DATA_ROOT.mkdir(parents=True, exist_ok=True)
        return _DATA_ROOT
    try:
        from plugins.plugin_storage import plugin_data_dir

        return plugin_data_dir(PLUGIN_NAME)
    except Exception:
        home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        root = home / "plugin-data" / PLUGIN_NAME
        root.mkdir(parents=True, exist_ok=True)
        return root


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_path(path: str, default_name: str) -> Path:
    """Resolve a write path and refuse anything outside Pilot's data dir."""
    root = data_dir().resolve()
    if path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve()
    else:
        candidate = (root / default_name).resolve()
    if candidate != root and root not in candidate.parents:
        raise tmux.PilotError(f"path escapes the pilot data directory: {candidate}")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def _check_upload_source(source: Path) -> None:
    resolved = source.resolve()
    home = Path.home()
    hermes = Path(os.environ.get("HERMES_HOME") or (home / ".hermes"))
    denied_roots = [
        hermes,
        home / ".ssh",
        home / ".aws",
        home / ".gnupg",
        home / ".kube",
        home / ".docker",
        home / ".password-store",
        home / ".local" / "share" / "keyrings",
        home / ".config" / "gh",
    ]
    for root in denied_roots:
        root = root.resolve()
        if resolved == root or root in resolved.parents:
            raise tmux.PilotError(f"refusing to read a credential path: {resolved}")
    name = resolved.name.lower()
    if name in _DENIED_NAMES or resolved.suffix.lower() in _DENIED_SUFFIXES:
        raise tmux.PilotError(f"refusing to read a credential file: {resolved}")


def _alive(name: str) -> tmux.SessionInfo:
    info = tmux.status(name)
    if info is None:
        raise tmux.PilotError(f"no pilot session named {name!r}")
    if info.dead:
        raise tmux.PilotError(f"session {name!r} has exited; read it or close it")
    return info


def run_once(
    command: str,
    *,
    timeout: float = 30.0,
    cols: int = tmux.DEFAULT_COLS,
    rows: int = tmux.DEFAULT_ROWS,
    cwd: str = "",
    env: dict | None = None,
    wait_for: str = "",
    keep_open: bool = False,
) -> dict:
    """Run *command* in a fresh TTY, capture its output, and close it."""
    if not (command or "").strip():
        raise tmux.PilotError("run needs a command")
    name = tmux.next_name("run")
    started = time.monotonic()
    info = tmux.open_session(
        command,
        name=name,
        cwd=cwd,
        env=env,
        cols=cols,
        rows=rows,
        wait_for=wait_for,
        wait_ms=min(1500, max(200, int(timeout * 1000))),
    )
    deadline = started + max(0.3, float(timeout))
    timed_out = False
    matched = False
    while time.monotonic() < deadline:
        info = tmux.status(name)
        if info is None or info.dead:
            break
        if wait_for and re.search(wait_for, tmux.screen(name, lines=200)):
            matched = True
            break
        time.sleep(0.1)
    else:
        timed_out = True

    info = tmux.status(name)
    output = tmux.screen(name, lines=2000)
    result: dict[str, Any] = {
        "ok": True,
        "session": name,
        "output": output,
        "dead": bool(info.dead) if info else True,
        "exit_status": info.exit_status if info and info.dead else None,
        "timed_out": timed_out,
        "matched": matched,
        "duration": round(time.monotonic() - started, 2),
    }
    if keep_open:
        result["attach"] = tmux.attach_command(name)
    else:
        tmux.close(name, missing_ok=True)
    return result


def expect(
    name: str,
    steps: list[dict],
    *,
    timeout: float = 20.0,
    lines: int = 200,
) -> dict:
    """Run a scripted sequence of wait/type/keys/sleep/quiet steps."""
    if not isinstance(steps, list) or not steps:
        raise tmux.PilotError("expect needs a non-empty list of steps")
    trace: list[dict] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise tmux.PilotError(f"step {index} must be an object")
        if "wait" in step:
            result = tmux.wait(
                name,
                str(step.get("wait") or ""),
                timeout=float(step.get("timeout") or timeout),
                quiet_ms=int(step.get("quiet_ms") or 700),
                lines=lines,
            )
            trace.append(
                {
                    "step": index,
                    "action": "wait",
                    "matched": result.get("matched"),
                    "timed_out": bool(result.get("timed_out")),
                    "elapsed": result.get("elapsed"),
                }
            )
            if not result.get("matched"):
                return {
                    "ok": False,
                    "failed_step": index,
                    "error": "pattern not found",
                    "trace": trace,
                    "screen": result.get("screen", ""),
                }
        elif "type" in step or "keys" in step:
            text = str(step.get("type") or "")
            keys = step.get("keys") or []
            screen = tmux.send(
                name,
                text=text,
                keys=keys,
                enter=bool(step.get("enter", True)),
            )
            trace.append(
                {"step": index, "action": "type", "text": text[:80], "keys": list(keys)}
            )
        elif "quiet" in step:
            result = tmux.wait(
                name,
                "",
                timeout=float(step.get("timeout") or timeout),
                quiet_ms=int(step.get("quiet") or 700),
                lines=lines,
            )
            trace.append(
                {
                    "step": index,
                    "action": "quiet",
                    "stable": bool(result.get("stable")),
                    "elapsed": result.get("elapsed"),
                }
            )
        elif "sleep" in step:
            delay = max(0.0, min(30.0, float(step.get("sleep") or 0)))
            time.sleep(delay)
            trace.append({"step": index, "action": "sleep", "seconds": delay})
        else:
            raise tmux.PilotError(
                f"step {index} needs one of: wait, type, keys, quiet, sleep"
            )
    return {"ok": True, "trace": trace, "screen": tmux.screen(name, lines=lines)}


def search_screen(
    name: str,
    pattern: str,
    *,
    lines: int = 2000,
    context: int = 2,
    max_hits: int = 20,
) -> dict:
    """Search the pane screen and scrollback with a regex."""
    if not (pattern or "").strip():
        raise tmux.PilotError("search needs a pattern")
    try:
        rx = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    except re.error as exc:
        raise tmux.PilotError(f"bad regex: {exc}") from exc
    text = tmux.screen(name, lines=max(1, min(int(lines), 5000)))
    rows = text.splitlines()
    hits: list[dict] = []
    for index, line in enumerate(rows):
        if not rx.search(line):
            continue
        block: list[dict] = [
            {"line": offset + 1, "text": rows[offset]}
            for offset in range(index - context, index + context + 1)
            if 0 <= offset < len(rows)
        ]
        hits.append({"line": index + 1, "text": line, "context": block})
        if len(hits) >= max(1, min(int(max_hits), 100)):
            break
    return {
        "ok": True,
        "name": name,
        "pattern": pattern,
        "matched": bool(hits),
        "hits": hits,
        "scanned_lines": len(rows),
    }


def log_start(name: str, path: str = "") -> str:
    """Start recording a pane's output to a log file."""
    _alive(name)
    logs = log_dir()
    if path:
        dest = logs / Path(path).name
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = logs / f"{name}-{stamp}.log"
    dest = safe_path(str(dest), dest.name)
    dest.touch(exist_ok=True)
    command = f"cat >> {shlex.quote(str(dest))}"
    tmux._tmux(["pipe-pane", "-o", "-t", name, command], check=True)
    _LOG_PATHS[name] = dest
    return str(dest)


def log_stop(name: str) -> str:
    """Stop recording a pane and return the log path."""
    tmux._tmux(["pipe-pane", "-t", name], check=True)
    path = _LOG_PATHS.get(name)
    if path is None:
        raise tmux.PilotError(f"no active log recorded for {name!r}")
    return str(path)


def log_read(path: str, tail_bytes: int = 20000) -> dict:
    """Read the tail of a log previously created by log_start."""
    candidate = Path(path).expanduser().resolve()
    root = log_dir().resolve()
    if root not in candidate.parents and candidate.parent != root:
        raise tmux.PilotError("log path must be inside the pilot log directory")
    if not candidate.exists():
        raise tmux.PilotError(f"log file not found: {candidate}")
    data = candidate.read_bytes()
    limit = max(1, min(int(tail_bytes), 200_000))
    tail = data[-limit:]
    return {
        "ok": True,
        "path": str(candidate),
        "bytes": len(data),
        "text": tail.decode("utf-8", "replace"),
    }


def signal_session(name: str, signal: str = "INT") -> str:
    """Send Ctrl-C / Ctrl-\\ / Ctrl-Z to the foreground program."""
    _alive(name)
    keys = {"INT": "C-c", "QUIT": "C-\\", "TSTP": "C-z"}
    key = keys.get(str(signal or "INT").upper())
    if key is None:
        raise tmux.PilotError("signal must be INT, QUIT or TSTP")
    tmux._tmux(["send-keys", "-t", name, key], check=True)
    return tmux.screen(name, lines=60)


def health() -> dict:
    """Return tmux and server diagnostics without touching a session."""
    import subprocess

    version = ""
    try:
        proc = subprocess.run(["tmux", "-V"], capture_output=True, text=True, timeout=5)
        version = proc.stdout.strip()
    except Exception:
        pass
    sessions = tmux.list_sessions()
    return {
        "ok": tmux.available(),
        "tmux": version or "not found",
        "socket": tmux.socket_name(),
        "sessions": len(sessions),
        "dead": sum(1 for item in sessions if item.dead),
        "log_dir": str(log_dir()),
        "limits": {
            "upload_bytes": UPLOAD_LIMIT,
            "download_bytes": DOWNLOAD_LIMIT,
            "screen_chars": tmux.MAX_SCREEN_CHARS,
            "name": tmux.NAME_RE.pattern,
        },
    }


def _require_shell(name: str) -> tmux.SessionInfo:
    info = _alive(name)
    command = (info.command or "").split("/")[-1]
    if command not in _SHELLS:
        raise tmux.PilotError(
            f"session {name!r} is running {info.command!r}, not a shell; "
            "file transfer would type into that program"
        )
    return info


def upload_file(
    name: str,
    local_path: str,
    remote_path: str = "",
    *,
    max_bytes: int = UPLOAD_LIMIT,
) -> dict:
    """Write a local file into the pane's shell using base64 chunks."""
    _require_shell(name)
    source = Path(local_path).expanduser()
    if not source.is_file():
        raise tmux.PilotError(f"local file not found: {source}")
    _check_upload_source(source)
    data = source.read_bytes()
    limit = max(1, min(int(max_bytes), UPLOAD_LIMIT))
    if len(data) > limit:
        raise tmux.PilotError(f"file is {len(data)} bytes; limit is {limit}")
    remote = remote_path or source.name
    quoted = shlex.quote(remote)
    encoded = base64.b64encode(data).decode("ascii")
    tmux.send(name, text=f": > {quoted}", enter=True)
    time.sleep(0.15)
    for start in range(0, len(encoded), 6000):
        chunk = encoded[start : start + 6000]
        tmux.send(
            name,
            text=f"printf '%s' '{chunk}' | base64 -d >> {quoted}",
            enter=True,
        )
        time.sleep(0.05)
    token = hashlib.sha256(data).hexdigest()[:8]
    tmux.send(
        name,
        text=f"wc -c < {quoted}; printf '\\n__PILOT_%s__\\n' UP_{token}",
        enter=True,
    )
    result = tmux.wait(name, f"__PILOT_UP_{token}__", timeout=15, lines=200)
    if not result.get("matched"):
        raise tmux.PilotError("upload did not finish; check the pane")
    before = result.get("screen", "").rsplit(f"__PILOT_UP_{token}__", 1)[0]
    tail_line = before.rstrip().splitlines()[-1].strip() if before.strip() else ""
    match = re.search(r"(\d+)\s*$", tail_line)
    observed = int(match.group(1)) if match else -1
    return {
        "ok": observed == len(data),
        "bytes": len(data),
        "observed_bytes": observed,
        "remote_path": remote,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def download_file(
    name: str,
    remote_path: str,
    local_path: str = "",
    *,
    max_bytes: int = DOWNLOAD_LIMIT,
    timeout: float = 30.0,
) -> dict:
    """Read a file from the pane's shell via base64 and write it locally."""
    _require_shell(name)
    quoted = shlex.quote(remote_path)
    limit = max(1, min(int(max_bytes), DOWNLOAD_LIMIT))
    token = hashlib.sha256(f"{name}:{remote_path}:{time.time()}".encode()).hexdigest()[:10]
    tmux.send(
        name,
        text=(
            f"base64 -w0 -- {quoted} 2>/dev/null || base64 {quoted} | tr -d '\\n'; "
            f"printf '\\n__PILOT_%s__\\n' DL_{token}"
        ),
        enter=True,
    )
    result = tmux.wait(name, f"__PILOT_DL_{token}__", timeout=timeout, lines=5000)
    if not result.get("matched"):
        raise tmux.PilotError("download did not finish; check the pane")
    screen = result.get("screen", "")
    marker = f"__PILOT_DL_{token}__"
    before = screen.rsplit(marker, 1)[0]
    matches = re.findall(r"[A-Za-z0-9+/=]{16,}", before)
    if not matches:
        raise tmux.PilotError("no base64 payload found in the pane")
    encoded = max(matches, key=len).strip()
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise tmux.PilotError(f"could not decode remote file: {exc}") from exc
    if len(data) > limit:
        raise tmux.PilotError(f"remote file is {len(data)} bytes; limit is {limit}")
    default_name = f"pilot-download-{name}-{Path(remote_path).name}"
    destination = safe_path(local_path, default_name)
    destination.write_bytes(data)
    return {
        "ok": True,
        "bytes": len(data),
        "local_path": str(destination.resolve()),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


__all__ = [
    "DOWNLOAD_LIMIT",
    "UPLOAD_LIMIT",
    "data_dir",
    "download_file",
    "expect",
    "health",
    "log_dir",
    "log_read",
    "log_start",
    "log_stop",
    "run_once",
    "safe_path",
    "search_screen",
    "signal_session",
    "upload_file",
]
