#!/usr/bin/env python3
"""Pilot demo — a real TTY, driven by keys.

Runs only local, harmless programs (bash, python, vim, fzf, htop if present) in
a private tmux server and closes every session at the end.

    python3 scripts/demo.py
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

_spec = importlib.util.spec_from_file_location(
    "hermes_pilot", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
_pkg = importlib.util.module_from_spec(_spec)
sys.modules["hermes_pilot"] = _pkg
_spec.loader.exec_module(_pkg)

from hermes_pilot import pilot_tmux as tmux  # noqa: E402


def rule(title: str) -> None:
    print(f"\n{'─' * 76}\n{title}\n{'─' * 76}")


def body(screen: str, limit: int = 14) -> None:
    lines = screen.splitlines()
    print("\n".join(lines[:limit]))
    if len(lines) > limit:
        print(f"… ({len(lines) - limit} more lines)")


def main() -> int:
    if not tmux.available():
        print("tmux is required")
        return 1
    tmux.close_all()

    rule("1. A program that reads stdin — impossible through a pipe")
    tmux.open_session(
        "printf 'Name? '; read n; echo \"hello $n, this is a real TTY\"",
        name="ask",
        wait_ms=800,
    )
    body(tmux.screen("ask"))
    tmux.send("ask", text="Lakshaya")
    result = tmux.wait("ask", "hello Lakshaya", timeout=5)
    body(result["screen"])
    print(f"\nmatched={result['matched']} · pane dead: {(tmux.status('ask') or tmux.SessionInfo('ask', None, '', True, 0, 0, 0)).dead}")
    tmux.close("ask")

    rule("2. A REPL that keeps state across tool calls")
    tmux.open_session("python3 -q", name="repl", wait_ms=700)
    tmux.send("repl", text="square = lambda n: n * n")
    time.sleep(0.3)
    tmux.send("repl", text="square(12)")
    body(tmux.wait("repl", "144", timeout=6)["screen"])
    tmux.close("repl")

    rule("3. Editing a file in vim by keystrokes")
    path = Path(tempfile.mkdtemp(prefix="pilot-demo-")) / "notes.txt"
    tmux.open_session(f"vim -Nu NONE -n {path}", name="vim", wait_ms=900)
    tmux.send("vim", keys=["i"], enter=False)
    time.sleep(0.2)
    tmux.send("vim", text="written by an agent, one keystroke at a time", enter=False)
    time.sleep(0.3)
    body(tmux.screen("vim"), limit=8)
    tmux.send("vim", keys=["Escape"], enter=False)
    time.sleep(0.2)
    tmux.send("vim", text=":wq", enter=True)
    deadline = time.time() + 8
    while time.time() < deadline and not path.exists():
        time.sleep(0.1)
    print(f"file on disk: {path}")
    print("contents    :", repr(path.read_text() if path.exists() else "<missing>"))
    tmux.close("vim")

    rule("4. A full-screen picker (fzf), driven by keys")
    tmux.open_session(
        "printf 'alpha\\nbeta\\ngamma\\ndelta\\n' | fzf --height 8", name="fzf", wait_ms=900
    )
    tmux.send("fzf", text="bet", enter=False)
    tmux.send("fzf", keys=["Enter"], enter=False)
    time.sleep(0.5)
    body(tmux.screen("fzf"), limit=8)
    tmux.close("fzf")

    rule("5. Reading a curses dashboard (htop)")
    if shutil.which("htop"):
        tmux.open_session("htop", name="htop", wait_ms=1200)
        body(tmux.screen("htop", lines=40), limit=10)
        tmux.send("htop", keys=["q"], enter=False)
        time.sleep(0.3)
        tmux.close("htop")
    else:
        print("htop not installed — skipped")

    rule("6. What the human sees: hermes pilot list")
    tmux.open_session("bash --norc -i", name="live1", wait_ms=400)
    print(f"{'name':<10} {'command':<10} {'pid':<8} {'state':<6} attach")
    for info in tmux.list_sessions():
        print(
            f"{info.name:<10} {info.command[:10]:<10} {str(info.pid):<8} "
            f"{'dead' if info.dead else 'live':<6} {tmux.attach_command(info.name)}"
        )
    print("\nThat attach command opens the same pane in any terminal. Type into it;")
    print("the agent's next screen read sees what you typed. Detach with Ctrl-b d.")

    tmux.close_all()
    print("\nall pilot sessions closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
