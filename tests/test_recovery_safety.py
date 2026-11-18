"""Recovery must never re-execute a command that may already have run.

Copilot review on catalog PR #157565: the 0.4.0 recovery retried the same
command after ANY mid-call PilotError — including session loss after the
command started or finished, duplicating non-idempotent side effects.

Contract:
- failure BEFORE Enter delivery (or Enter rejected) -> recreate, retry once;
- Enter delivery uncertain (tmux timeout) or loss AFTER delivery ->
  indeterminate result (rc -1, pilot_indeterminate), NEVER auto-retried.

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import shutil
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

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
class RecoverySafetyTest(unittest.TestCase):
    def setUp(self):
        self.task = f"safe-{uuid.uuid4().hex[:8]}"
        self.env = pilot_env.PilotEnvironment(cwd="/tmp", timeout=15, task_id=self.task)
        self.side = Path(tempfile.mkdtemp(prefix="pilot-effects-")) / "effects"
        self.run_cmd("echo warmup")

    def tearDown(self):
        self.env.cleanup()
        tmux.close(pilot_env.session_name(self.task), missing_ok=True)
        shutil.rmtree(self.side.parent, ignore_errors=True)

    def run_cmd(self, command, **kw):
        return self.env.execute(command, **kw)

    def effect_command(self, tail="echo done"):
        return f"printf x >> {shlex.quote(str(self.side))}; sleep 1; {tail}"

    def test_post_delivery_loss_is_indeterminate_not_retried(self):
        # Kill lands while the command runs (after delivery). It may have
        # partially or fully executed: report indeterminate, run it ONCE.
        killer = threading.Timer(0.4, lambda: tmux.close(self.env.name, missing_ok=True))
        killer.start()
        try:
            result = self.run_cmd(self.effect_command())
        finally:
            killer.cancel()
        self.assertEqual(result["returncode"], -1)
        self.assertTrue(result.get("pilot_indeterminate"))
        self.assertIn("NOT retried", result["output"])
        self.assertEqual(self.side.read_text(), "x")

    def test_pre_enter_failure_retries_once(self):
        # A send failure before Enter means nothing executed; recreating the
        # shell wipes any partial input, so one retry is safe.
        real_send = tmux.send
        calls = {"n": 0}

        def flaky_send(name, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise tmux.PilotError(f"no pilot session named {name!r}")
            return real_send(name, **kw)

        with patch.object(pilot_env.tmux, "send", side_effect=flaky_send):
            result = self.run_cmd(self.effect_command(tail="echo ok"))
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(self.side.read_text(), "x")

    def test_delivery_uncertain_is_indeterminate(self):
        with patch.object(
            pilot_env.tmux, "send", side_effect=tmux.DeliveryUncertain("tmux timed out after 15s")
        ):
            result = self.run_cmd(self.effect_command())
        self.assertEqual(result["returncode"], -1)
        self.assertTrue(result.get("pilot_indeterminate"))
        self.assertFalse(self.side.exists())

    def test_send_enter_timeout_raises_delivery_uncertain(self):
        real_tmux = tmux._tmux

        def fake(args, **kw):
            if list(args[:2]) == ["send-keys", "-t"] and list(args)[-1] == "Enter":
                raise tmux.TmuxTimeout("tmux timed out after 15s")
            return real_tmux(args, **kw)

        with patch.object(tmux, "_tmux", side_effect=fake):
            with self.assertRaises(tmux.DeliveryUncertain):
                tmux.send(self.env.name, text="echo hi", enter=True, capture=False)

    def test_send_capture_false_skips_screen(self):
        out = tmux.send(self.env.name, text="echo no-capture", enter=True, capture=False)
        self.assertEqual(out, "")
        self.assertIn("no-capture", tmux.screen(self.env.name, lines=20))


if __name__ == "__main__":
    unittest.main()
