"""Capture the two terminal frames used as poster evidence.

Left: what the agent's pipe-based terminal tool returns for htop (real bytes,
rendered as caret notation so control codes are visible).
Right: what Pilot returns for the same program (a real capture-pane).

Run once; the renderer reads the text files it writes.
"""

from __future__ import annotations

import html
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hermes_pilot", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
pkg = importlib.util.module_from_spec(spec)
sys.modules["hermes_pilot"] = pkg
spec.loader.exec_module(pkg)

from hermes_pilot import pilot_tmux as tmux  # noqa: E402

SRC = Path(__file__).resolve().parent / "src"


def caret(raw: str) -> str:
    out = []
    for ch in raw:
        code = ord(ch)
        if ch == "\r":
            out.append("^M")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\x1b":
            out.append("^[")
        elif code < 32:
            out.append("^" + chr(code + 64))
        elif code == 127:
            out.append("^?")
        else:
            out.append(ch)
    return "".join(out)


def wrap_soup(text: str, width: int = 96, lines: int = 20) -> str:
    text = text.lstrip()  # htop opens with a clear-screen run of spaces
    text = re.sub(r"[ ]{3,}", lambda m: " " * max(1, len(m.group(0)) // 6), text)
    chunks = [text[i : i + width] for i in range(0, min(len(text), width * lines), width)]
    return "\n".join(chunk.rstrip() for chunk in chunks if chunk.strip())


def run_shell(command: str, timeout: str = "3") -> str:
    """Capture what a pipe-based terminal returns for one interactive program."""
    proc = subprocess.run(
        ["timeout", timeout, "sh", "-c", command],
        capture_output=True,
        text=True,
        env={**os.environ, "TERM": "dumb"},
    )
    return (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    raw_path = SRC / "htop_raw.txt"
    if not raw_path.exists() or raw_path.stat().st_size == 0:
        raw_path.write_text(run_shell("htop", "2"), encoding="utf-8")

    soup = wrap_soup(caret(raw_path.read_text(errors="replace")))
    vim = run_shell("printf '' | vim -Nu NONE -n /tmp/pilot-pipe.txt")
    fzf = run_shell("printf 'a\\nb\\n' | fzf")
    vim_lines = [
        line.strip()
        for line in caret(vim).split("\\n")
        if line.strip() and ("Warning" in line or "Error" in line)
    ]
    fail_blocks = [
        ("htop", soup),
        ("vim notes.txt", "\n".join(vim_lines[:3])),
        ("fzf", next((ln.strip() for ln in caret(fzf).split("\\n") if ln.strip()), "")),
    ]
    fail_text = "\n\n".join(f"$ {cmd}\n{out}" for cmd, out in fail_blocks if out)
    (SRC / "fail.txt").write_text(html.escape(fail_text), encoding="utf-8")

    tmux.close_all()
    tmux.open_session("htop", name="art", cols=88, rows=24, wait_ms=2500)
    clean = tmux.screen("art", lines=40)
    tmux.close("art")
    (SRC / "tty.txt").write_text(html.escape(clean), encoding="utf-8")

    print(
        "fail blocks:", len(fail_blocks),
        "· tty lines:", len(clean.splitlines()),
        "· tty chars:", len(clean),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
