"""Pilot as a Hermes terminal backend.

The built-in terminal tool runs each command through a pipe. This backend runs
each command inside a persistent tmux shell instead, so the tool keeps its
normal contract (``output`` / ``returncode`` / observed cwd) while gaining a
real TTY:

* ``cd``, exports, aliases and shell state survive across tool calls;
* a command that does not finish is left running and attachable through the
  ``pilot`` tool instead of being killed with the pipe;
* no command is ever sent into a program that is still running: the backend
  reports the session as busy and tells the model to use ``pilot``.

Select it with ``terminal.backend: pilot`` (or ``TERMINAL_ENV=pilot``).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shlex
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import pilot_tmux as tmux

try:  # Hermes core: the registry rejects providers that do not inherit from this ABC.
    from agent.terminal_env_provider import TerminalEnvironmentProvider as _ProviderBase
except Exception:  # standalone use / test stubs without Hermes on sys.path
    _ProviderBase = object

logger = logging.getLogger(__name__)

MARKER = "__PILOT_TERM_END__"
SESSION_PREFIX = "term-"
CAPTURE_LINES = 4000
POLL_SECONDS = 0.12
BUSY_RC = 126

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(name: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(name, threading.Lock())


def session_name(task_id: str) -> str:
    """Stable tmux session name for a Hermes task/session id (<=32 chars)."""
    raw = str(task_id or "default")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-_")[:12] or "default"
    return f"{SESSION_PREFIX}{slug}-{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


class PilotEnvironment:
    """Duck-typed terminal environment backed by a persistent tmux shell.

    The terminal tool only needs ``execute()``, ``cwd``, ``cleanup()`` and the
    classification flags; everything else is optional.
    """

    is_local = True
    uses_host_filesystem = True
    env_type = "pilot"

    def __init__(self, *, cwd: str, timeout: int = 120, task_id: str = "default") -> None:
        self.cwd = os.path.expanduser(cwd or "~")
        self.timeout = int(timeout or 120)
        self.task_id = task_id or "default"
        self.name = session_name(self.task_id)
        self._lock = _lock_for(self.name)
        self._busy_marker: str = ""
        # File-tool duck typing: some file operations read the environment's
        # export map and host-mount hints.
        self.env: dict[str, str] = {}
        self.host_cwd = None
        self.host_cwd_mount = None

    # ── lifecycle ──────────────────────────────────────────────────────
    def _alive(self) -> bool:
        info = tmux.status(self.name)
        return info is not None and not info.dead

    def _start(self) -> None:
        if tmux.status(self.name) is not None:
            return
        self._busy_marker = ""
        tmux.open_session(
            "bash -i",
            name=self.name,
            cwd=self.cwd,
            cols=tmux.DEFAULT_COLS,
            rows=tmux.DEFAULT_ROWS,
            wait_ms=1200,
        )
        # A broken .bashrc can kill the interactive shell; fall back to a bare one.
        if not self._alive():
            tmux.close(self.name, missing_ok=True)
            tmux.open_session(
                "bash --noprofile --norc -i",
                name=self.name,
                cwd=self.cwd,
                cols=tmux.DEFAULT_COLS,
                rows=tmux.DEFAULT_ROWS,
                wait_ms=800,
            )

    def cleanup(self) -> None:
        self._busy_marker = ""
        try:
            tmux.close(self.name, missing_ok=True)
        except Exception:
            logger.debug("pilot: cleanup of %s failed", self.name, exc_info=True)

    # ── execution ──────────────────────────────────────────────────────
    def execute(
        self,
        command: str,
        *,
        timeout: int | float | None = None,
        cwd: str | None = None,
        bounded_capture: bool = False,
        **_kwargs: Any,
    ) -> dict:
        """Run *command* in the persistent shell and return the terminal-tool result."""
        with self._lock:
            if self._busy_marker:
                # A previous command timed out. If it has since finished, take the
                # new prompt back; otherwise refuse to type into a live program.
                if self._pending_finished():
                    self._busy_marker = ""
                else:
                    return {
                        "output": (
                            f"[pilot] session {self.name} is still running the previous command "
                            f"(it did not return within its timeout). Use the pilot tool: "
                            f"action='screen' name='{self.name}' to look, action='type' to answer a "
                            f"prompt, or action='close' to reset it."
                        ),
                        "returncode": BUSY_RC,
                        "cwd_observed": False,
                    }

            self._start()
            timeout = float(timeout or self.timeout)
            run_line, script = self._write_script(command, cwd)
            try:
                tmux.send(self.name, text=run_line, enter=True)
                result = self._wait(run_line, timeout)
                if result.get("cwd_observed") and result.get("cwd"):
                    self.cwd = result["cwd"]
                return result
            finally:
                try:
                    script.unlink(missing_ok=True)
                    script.parent.rmdir()
                except OSError:
                    pass

    def _write_script(self, command: str, cwd: str | None) -> tuple[str, Path]:
        token = uuid.uuid4().hex[:10]
        directory = Path(tempfile.mkdtemp(prefix="pilot-term-"))
        script = directory / f"run-{token}.sh"
        marker = f"{MARKER}{token}"
        cd_line = ""
        if cwd:
            quoted = shlex.quote(os.path.expanduser(cwd))
            cd_line = (
                f"cd -- {quoted} 2>/dev/null || "
                f"{{ printf '\\n{marker}__99__%s\\n' \"$PWD\"; exit 99; }}\n"
            )
        body = (
            f"{cd_line}"
            f"{command}\n"
            f"__pilot_rc=$?\n"
            f"printf '\\n{marker}__%s__%s\\n' \"$__pilot_rc\" \"$PWD\"\n"
        )
        script.write_text(body, encoding="utf-8")
        os.chmod(script, 0o700)
        self._busy_marker = marker
        return f". {shlex.quote(str(script))}", script

    def _wait(self, run_line: str, timeout: float) -> dict:
        deadline = time.monotonic() + max(0.2, timeout)
        while True:
            screen = tmux.screen(self.name, lines=CAPTURE_LINES)
            parsed = self._parse(screen, run_line)
            if parsed is not None:
                self._busy_marker = ""
                return parsed
            info = tmux.status(self.name)
            if info is not None and info.dead:
                # The command exited the shell itself; keep its final screen.
                self._busy_marker = ""
                return {
                    "output": self._slice(screen, run_line),
                    "returncode": info.exit_status if info.exit_status is not None else -1,
                    "cwd_observed": False,
                }
            if time.monotonic() >= deadline:
                # Leave it running and attachable rather than killing it.
                partial = self._slice(screen, run_line)
                note = (
                    f"\n\n[pilot] still running after {timeout:.0f}s in session {self.name}. "
                    f"The program was not killed. Use the pilot tool to inspect or drive it "
                    f"(action='screen' / 'type' / 'close' name='{self.name}')."
                )
                return {
                    "output": (partial + note) if partial else note.strip(),
                    "returncode": 124,
                    "cwd_observed": False,
                    "hermes_timed_out": True,
                    "pilot_session": self.name,
                }
            time.sleep(POLL_SECONDS)

    def _parse(self, screen: str, run_line: str) -> dict | None:
        marker = self._busy_marker
        at = screen.rfind(marker)
        if at == -1:
            return None
        line_end = screen.find("\n", at)
        line = screen[at : line_end if line_end != -1 else None].strip()
        rest = line[len(marker) :]
        if rest.startswith("__"):
            rest = rest[2:]
        fields = rest.split("__")
        try:
            returncode = int(fields[0])
        except (IndexError, ValueError):
            returncode = -1
        observed = fields[1].strip() if len(fields) > 1 else ""
        return {
            "output": self._slice(screen[:at], run_line),
            "returncode": returncode,
            "cwd": observed or self.cwd,
            "cwd_observed": bool(observed),
        }

    @staticmethod
    def _slice(screen: str, run_line: str) -> str:
        start = screen.rfind(run_line)
        body = screen[start + len(run_line) :] if start != -1 else screen
        return body.strip("\n")

    def _pending_finished(self) -> bool:
        try:
            return self._busy_marker in tmux.screen(self.name, lines=CAPTURE_LINES)
        except tmux.PilotError:
            return False


class PilotTerminalProvider(_ProviderBase):
    """Register Pilot as ``terminal.backend: pilot``."""

    name = "pilot"
    display_name = "Pilot TTY"
    is_remote = False
    is_container = False
    supports_streams = False
    session_isolated_when_nonpersistent = True

    def is_available(self) -> bool:
        return tmux.available()

    def check_requirements(self, config: dict[str, Any] | None = None) -> bool:
        if tmux.available():
            return True
        logger.error(
            "The pilot terminal backend needs tmux on PATH. Install it "
            "(sudo pacman -S tmux, sudo apt install tmux, brew install tmux), then retry."
        )
        return False

    def probe(self) -> tuple[str, str]:
        if tmux.available():
            return ("ready", "tmux found")
        return ("needs_setup", "tmux is not installed")

    def setup_instructions(self) -> list[str]:
        return [
            "Install tmux: sudo pacman -S tmux  (or apt/brew)",
            "Select it for new sessions: hermes config set terminal.backend pilot",
            "Or turn it on/off from this plugin: hermes pilot backend on",
        ]

    def doctor_checks(self) -> list[tuple[bool, str, str]]:
        ok = tmux.available()
        return [(ok, "Pilot terminal backend", "tmux found" if ok else "tmux not installed")]

    def create_environment(
        self,
        *,
        cwd: str,
        timeout: int,
        task_id: str = "default",
        image: str | None = None,
        container_config: dict | None = None,
        **kwargs: Any,
    ) -> PilotEnvironment:
        return PilotEnvironment(cwd=cwd, timeout=timeout, task_id=task_id)


__all__ = ["PilotEnvironment", "PilotTerminalProvider", "session_name", "MARKER"]
