#!/usr/bin/env python3
"""Drive a real SSH session through Pilot and capture the before/after screens.

The remote host is whatever you pass; this script does not care whether it is a
second laptop over Tailscale or a local sshd. It fixes a typo in
``~/pilot-demo/app.conf`` with vim, over ssh, and captures both states.

    python3 scripts/ssh_demo.py --host msi --user lakshaya
    python3 scripts/ssh_demo.py --host 127.0.0.1 --port 2222 --key /tmp/pilot-sshd/id

Writes art/src/ssh-before.txt and art/src/ssh-after.txt (real capture-pane text).
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hermes_pilot", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
pkg = importlib.util.module_from_spec(spec)
sys.modules["hermes_pilot"] = pkg
spec.loader.exec_module(pkg)

from hermes_pilot import pilot_tmux as tmux  # noqa: E402

SRC = ROOT / "art" / "src"
REMOTE_DIR = "pilot-demo"
REMOTE_FILE = f"{REMOTE_DIR}/app.conf"


def build_ssh(args) -> str:
    parts = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if args.key:
        parts += ["-i", args.key]
    if args.port:
        parts += ["-p", str(args.port)]
    target = f"{args.user}@{args.host}" if args.user else args.host
    parts.append(target)
    return " ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--user", default="")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--key", default="")
    ap.add_argument("--name", default="ssh1")
    ap.add_argument("--keep", action="store_true", help="leave the session open")
    args = ap.parse_args()

    if not tmux.available():
        print("tmux required")
        return 1
    SRC.mkdir(parents=True, exist_ok=True)

    command = build_ssh(args)
    print("opening:", command)
    tmux.close_all()
    tmux.open_session(command, name=args.name, cols=100, rows=28, wait_ms=2500)
    tmux.wait(args.name, r"[$#] $|[$#]$", timeout=15)

    # Make a broken file on the remote, then read it.
    tmux.send(args.name, text=f"mkdir -p ~/{REMOTE_DIR} && printf 'porrt = 8080\\n' > ~/{REMOTE_FILE}")
    tmux.send(args.name, text=f"cat ~/{REMOTE_FILE}")
    before = tmux.wait(args.name, "porrt", timeout=10)["screen"]
    (SRC / "ssh-before.txt").write_text(html.escape(before), encoding="utf-8")

    # Fix it in vim, by keystrokes, over the ssh session.
    tmux.send(args.name, text=f"vim -Nu NONE -n ~/{REMOTE_FILE}")
    tmux.wait(args.name, r"app\.conf|~", timeout=10, quiet_ms=600)
    time.sleep(0.4)
    tmux.send(args.name, keys=["c", "w"], enter=False)  # change word at col 1
    time.sleep(0.2)
    tmux.send(args.name, text="port", enter=False)
    time.sleep(0.2)
    tmux.send(args.name, keys=["Escape"], enter=False)
    time.sleep(0.3)
    tmux.send(args.name, text=":wq", enter=True)
    time.sleep(0.6)
    tmux.wait(args.name, r"[$#] $|[$#]$", timeout=10)

    tmux.send(args.name, text=f"cat ~/{REMOTE_FILE}")
    after = tmux.wait(args.name, "port = 8080", timeout=10)["screen"]
    (SRC / "ssh-after.txt").write_text(html.escape(after), encoding="utf-8")

    print("before has typo:", "porrt" in before)
    print("after has fix :", "port = 8080" in after)
    print("saved:", SRC / "ssh-before.txt", "and", SRC / "ssh-after.txt")
    if not args.keep:
        tmux.close(args.name)
    return 0 if ("porrt" in before and "port = 8080" in after) else 1


if __name__ == "__main__":
    raise SystemExit(main())
