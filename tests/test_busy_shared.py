"""Busy state belongs to the session, not to one environment instance.

Hermes can hold several PilotEnvironment instances for one task (terminal
tool, execute_code sandbox). A fresh instance must not type into a pane
where another instance's command is still running.

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
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

from hermes_pilot import pilot_env  # noqa: E402
from hermes_pilot import pilot_tmux as tmux  # noqa: E402

HAVE_TMUX = shutil.which("tmux") is not None


@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class SharedBusyTest(unittest.TestCase):
    def setUp(self):
        self.task = f"busy-{uuid.uuid4().hex[:8]}"
        self.a = pilot_env.PilotEnvironment(cwd="/tmp", timeout=12, task_id=self.task)
        self.b = pilot_env.PilotEnvironment(cwd="/tmp", timeout=12, task_id=self.task)

    def tearDown(self):
        self.a.cleanup()
        tmux.close(pilot_env.session_name(self.task), missing_ok=True)

    def test_fresh_instance_sees_busy_session(self):
        timed_out = self.a.execute("sleep 5", timeout=1)
        self.assertEqual(timed_out["returncode"], 124)
        # b never saw the timeout, but the pane is still running sleep:
        # typing into it would violate the backend contract.
        busy = self.b.execute("echo should-not-run")
        self.assertEqual(busy["returncode"], pilot_env.BUSY_RC)
        self.assertIn("still running", busy["output"])

    def test_fresh_instance_recovers_when_command_finishes(self):
        self.a.execute("sleep 2", timeout=0.5)
        time.sleep(3)
        recovered = self.b.execute("echo recovered-via-b")
        self.assertEqual(recovered["returncode"], 0)
        self.assertIn("recovered-via-b", recovered["output"])

    def test_cleanup_clears_shared_busy_state(self):
        self.a.execute("sleep 5", timeout=1)
        self.a.cleanup()
        fresh = self.b.execute("echo after-cleanup")
        self.assertEqual(fresh["returncode"], 0)
        self.assertIn("after-cleanup", fresh["output"])


if __name__ == "__main__":
    unittest.main()
