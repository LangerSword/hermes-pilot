"""Regression tests for the 20K head-truncation wedge (#157099).

The completion marker prints at the TAIL of the pane. trim_screen used to
keep the HEAD of an over-long capture, chopping the marker: _wait then
reported a false timeout and _pending_finished kept the session busy forever.

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
MARKER = "__PILOT_TERM_END__deadbeef"


def big_screen(tail: str = f"\n{MARKER}__0__/home/user\n", lines: int = 2500) -> str:
    """~50K of scrollback with the completion marker at the very end."""
    return ("line of build output\n" * lines) + tail


class TrimScreenTest(unittest.TestCase):
    def test_marker_survives_large_scrollback(self):
        trimmed = tmux.trim_screen(big_screen())
        self.assertIn(MARKER, trimmed)

    def test_trim_keeps_tail_not_head(self):
        screen = "OLD-HISTORY-HEAD\n" + ("filler line\n" * 3000) + "NEW-OUTPUT-TAIL\n"
        trimmed = tmux.trim_screen(screen)
        self.assertIn("NEW-OUTPUT-TAIL", trimmed)
        self.assertNotIn("OLD-HISTORY-HEAD", trimmed)

    def test_small_screen_unchanged(self):
        screen = "just a short screen\nwith two lines"
        self.assertEqual(tmux.trim_screen(screen), screen)

    def test_parse_completes_on_trimmed_screen(self):
        env = pilot_env.PilotEnvironment(cwd="/tmp", task_id="unit-trim")
        env._busy_marker = MARKER
        parsed = env._parse(tmux.trim_screen(big_screen()), ". /run.sh")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["returncode"], 0)
        self.assertEqual(parsed["cwd"], "/home/user")
        self.assertTrue(parsed["cwd_observed"])

    def test_pending_finished_sees_marker_through_trim(self):
        env = pilot_env.PilotEnvironment(cwd="/tmp", task_id="unit-trim")
        env._busy_marker = MARKER
        # _pending_finished consults the live pane; emulate its capture path.
        self.assertIn(env._busy_marker, tmux.trim_screen(big_screen()))

    def test_slice_fallback_never_returns_head_history(self):
        # When the run line is outside the capture window (current output
        # alone exceeds it), the fallback must not dump unrelated old
        # scrollback into the tool result — only the current output's tail.
        screen = tmux.trim_screen(
            "OLD-HISTORY-HEAD\n" + ("filler line\n" * 3000) + "CURRENT-OUTPUT\n"
        )
        body = pilot_env.PilotEnvironment._slice(screen, ". /run-missing.sh")
        self.assertIn("CURRENT-OUTPUT", body)
        self.assertNotIn("OLD-HISTORY-HEAD", body)


@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class LargeOutputExecuteTest(unittest.TestCase):
    def setUp(self):
        self.task = f"trunc-{uuid.uuid4().hex[:8]}"
        self.env = pilot_env.PilotEnvironment(cwd="/tmp", timeout=15, task_id=self.task)

    def tearDown(self):
        self.env.cleanup()
        tmux.close(pilot_env.session_name(self.task), missing_ok=True)

    def test_large_output_completes_without_wedge(self):
        # ~66K of output: far past the 20K capture trim. The command finishes
        # in milliseconds; the backend must report rc 0, not a false timeout.
        result = self.env.execute("python3 -c \"print('filler-line-0123456789\\n' * 3000)\"")
        self.assertEqual(result["returncode"], 0)
        self.assertIn("filler-line", result["output"])
        self.assertNotIn("__PILOT_TERM_END__", result["output"])
        followup = self.env.execute("echo after-large")
        self.assertEqual(followup["returncode"], 0)
        self.assertIn("after-large", followup["output"])

    def test_timeout_then_late_finish_recovers_with_large_scrollback(self):
        # The exact #157099 scenario: big scrollback, a command that outlives
        # its timeout, then finishes on its own. The next call must recover
        # WITHOUT a manual close.
        self.env.execute("python3 -c \"print('filler-line-0123456789\\n' * 3000)\"")
        timed_out = self.env.execute("sleep 2", timeout=0.5)
        self.assertEqual(timed_out["returncode"], 124)
        time.sleep(3)
        recovered = self.env.execute("echo recovered")
        self.assertEqual(recovered["returncode"], 0)
        self.assertIn("recovered", recovered["output"])

    def test_output_cannot_spoof_completion(self):
        # A command printing a lookalike marker must neither complete the run
        # early nor spoof the observed cwd: the run token is unguessable.
        result = self.env.execute(
            "echo __PILOT_TERM_END__fakefake__0__/evil; echo real-output"
        )
        self.assertEqual(result["returncode"], 0)
        self.assertTrue(result["cwd_observed"])
        self.assertNotEqual(result["cwd"], "/evil")
        self.assertIn("real-output", result["output"])


if __name__ == "__main__":
    unittest.main()
