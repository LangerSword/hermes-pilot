"""send() must not double-press Enter when keys already carry the intent.

keys=['Enter'] with the old default enter=True sent TWO Enters — observed
live jumping two picker stages in one call. New contract: enter defaults
to auto (true for text-only sends, false when keys are given); explicit
true/false always wins.

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

# Isolate the tmux socket: socket_name() digests HERMES_HOME, and these tests
# call close_all() — on the live profile socket that kills every concurrent
# Hermes task's terminal session, including the backend running the suite.
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="pilot-test-home.")

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
from hermes_pilot import pilot_toolset as toolset  # noqa: E402

HAVE_TMUX = shutil.which("tmux") is not None
# Prints 1, 2, 3... — one number per Enter-terminated line it receives.
COUNTER = "python3 -u -c 'import sys; [print(i) for i, _ in enumerate(sys.stdin, 1)]'"


def counts(screen: str) -> list[str]:
    return [line.strip() for line in screen.splitlines() if line.strip().isdigit()]


@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class SendEnterTest(unittest.TestCase):
    def setUp(self):
        self.name = f"cnt-{uuid.uuid4().hex[:6]}"
        tmux.open_session(COUNTER, name=self.name, wait_ms=900)

    def tearDown(self):
        tmux.close(self.name, missing_ok=True)

    def settled_screen(self) -> str:
        time.sleep(0.5)
        return tmux.screen(self.name, lines=40)

    def test_keys_enter_is_not_doubled(self):
        tmux.send(self.name, keys=["Enter"])
        tmux.wait(self.name, "1", timeout=5)
        self.assertEqual(counts(self.settled_screen()), ["1"])

    def test_explicit_enter_true_still_appends(self):
        tmux.send(self.name, keys=["Enter"], enter=True)
        tmux.wait(self.name, "2", timeout=5)
        self.assertEqual(counts(self.settled_screen()), ["1", "2"])

    def test_text_only_still_enters(self):
        tmux.send(self.name, text="hello")
        tmux.wait(self.name, "1", timeout=5)
        self.assertEqual(counts(self.settled_screen()), ["1"])

    def test_send_tool_keys_enter_not_doubled(self):
        result = toolset._send({"name": self.name, "keys": ["Enter"]})
        self.assertTrue(result["ok"])
        tmux.wait(self.name, "1", timeout=5)
        self.assertEqual(counts(self.settled_screen()), ["1"])


if __name__ == "__main__":
    unittest.main()
