"""close_all / pilot_killall must not kill live Hermes tasks' backend shells.

The tmux socket is per-profile, shared by every concurrent task. term-*
sessions are terminal-backend shells with live state; a blanket killall
drops other tasks mid-command (observed as a multi-session outage).

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
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
TERM_NAME = "term-keepme-12345678"


@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class KillallScopeTest(unittest.TestCase):
    def tearDown(self):
        tmux.close_all(include_terminal=True)

    def test_close_all_preserves_terminal_sessions(self):
        tmux.open_session("bash --norc -i", name="work1", wait_ms=300)
        tmux.open_session("bash --norc -i", name=TERM_NAME, wait_ms=300)
        self.assertEqual(tmux.close_all(), 1)
        self.assertIsNone(tmux.status("work1"))
        self.assertIsNotNone(tmux.status(TERM_NAME))

    def test_close_all_include_terminal_is_full_reset(self):
        tmux.open_session("bash --norc -i", name=TERM_NAME, wait_ms=300)
        self.assertEqual(tmux.close_all(include_terminal=True), 1)
        self.assertIsNone(tmux.status(TERM_NAME))

    def test_killall_tool_preserves_terminal_by_default(self):
        tmux.open_session("bash --norc -i", name=TERM_NAME, wait_ms=300)
        result = json.loads(toolset._killall({}))
        self.assertTrue(result["ok"])
        self.assertEqual(result["closed"], 0)
        self.assertIsNotNone(tmux.status(TERM_NAME))

    def test_killall_tool_include_terminal_opt_in(self):
        tmux.open_session("bash --norc -i", name=TERM_NAME, wait_ms=300)
        result = json.loads(toolset._killall({"include_terminal": True}))
        self.assertEqual(result["closed"], 1)
        self.assertIsNone(tmux.status(TERM_NAME))


if __name__ == "__main__":
    unittest.main()
