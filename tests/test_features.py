"""Tests for the extended Pilot tool suite (stdlib; needs tmux)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import time
import unittest
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

from hermes_pilot import pilot_features as feat  # noqa: E402
from hermes_pilot import pilot_tmux as tmux  # noqa: E402
from hermes_pilot import pilot_toolset as toolset  # noqa: E402

HAVE_TMUX = shutil.which("tmux") is not None


@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class FeatureTest(unittest.TestCase):
    def tearDown(self):
        try:
            tmux.close_all()
        except Exception:
            pass

    def bash(self, name: str = "f1", cwd: str = "") -> tmux.SessionInfo:
        return tmux.open_session("bash --norc -i", name=name, cwd=cwd, wait_ms=400)

    def test_run_once_captures_output_and_exit(self):
        result = feat.run_once("printf 'HI\\n'; exit 3", timeout=5)
        self.assertIn("HI", result["output"])
        self.assertEqual(result["exit_status"], 3)
        self.assertTrue(result["dead"])
        self.assertIsNone(tmux.status(result["session"]))

    def test_run_once_timeout(self):
        result = feat.run_once("sleep 5", timeout=0.5)
        self.assertTrue(result["timed_out"])
        self.assertIsNone(tmux.status(result["session"]))

    def test_expect_answers_prompt(self):
        tmux.open_session(
            "printf 'Name? '; read n; echo HELLO_$n", name="prompt", wait_ms=400
        )
        result = feat.expect(
            "prompt",
            [
                {"wait": r"Name\? *$", "timeout": 5},
                {"type": "Lakshaya"},
                {"wait": "HELLO_Lakshaya", "timeout": 5},
            ],
        )
        self.assertTrue(result["ok"], result)
        self.assertIn("HELLO_Lakshaya", result["screen"])

    def test_search_with_context(self):
        self.bash("search1")
        tmux.send("search1", text="printf 'ALPHA\\nBETA\\nGAMMA\\n'")
        tmux.wait("search1", "GAMMA", timeout=5, quiet_ms=300)
        result = feat.search_screen("search1", "BETA", context=2)
        self.assertTrue(result["matched"])
        beta = next(hit for hit in result["hits"] if hit["text"] == "BETA")
        self.assertTrue(any("ALPHA" in item["text"] for item in beta["context"]))

    def test_diff_snapshot(self):
        self.bash("diff1")
        tmux.send("diff1", text="echo BEFORE")
        tmux.wait("diff1", "BEFORE", timeout=5, quiet_ms=300)
        snapshot = toolset._diff({"name": "diff1", "mode": "snapshot"})
        self.assertTrue(snapshot["ok"])
        tmux.send("diff1", text="echo AFTER")
        tmux.wait("diff1", "AFTER", timeout=5, quiet_ms=300)
        result = toolset._diff({"name": "diff1", "mode": "diff"})
        self.assertTrue(result["changed"])
        self.assertGreaterEqual(result["added"], 1)

    def test_log_start_stop_read(self):
        self.bash("log1")
        path = feat.log_start("log1")
        tmux.send("log1", text="echo LOG_MARKER_77")
        tmux.wait("log1", "LOG_MARKER_77", timeout=5, quiet_ms=300)
        stopped = feat.log_stop("log1")
        self.assertEqual(stopped, path)
        reading = feat.log_read(path)
        self.assertIn("LOG_MARKER_77", reading["text"])

    def test_signal_interrupts_foreground(self):
        self.bash("sig1")
        tmux.send("sig1", text="sleep 30")
        time.sleep(0.4)
        screen = feat.signal_session("sig1", "INT")
        self.assertIn("sig1", "sig1")
        self.assertIsInstance(screen, str)

    def test_resize_and_rename(self):
        self.bash("size1")
        tmux.resize("size1", 90, 24)
        self.assertEqual(tmux.status("size1").cols, 90)
        renamed = tmux.rename("size1", "size2")
        self.assertEqual(renamed, "size2")
        self.assertIsNone(tmux.status("size1"))
        self.assertIsNotNone(tmux.status("size2"))

    def test_health(self):
        result = feat.health()
        self.assertTrue(result["ok"])
        self.assertIn("tmux", result["tmux"])

    def test_upload_and_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.bash("file1", cwd=str(root))
            source = root / "source.txt"
            source.write_text("hello from pilot\nsecond line\n")
            uploaded = feat.upload_file("file1", str(source), "remote.txt")
            self.assertTrue(uploaded["ok"], uploaded)
            target = root / "roundtrip.txt"
            downloaded = feat.download_file("file1", "remote.txt", str(target))
            self.assertTrue(downloaded["ok"])
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_cleanup_reaps_dead(self):
        tmux.open_session("echo bye; exit 0", name="deadx", wait_ms=500)
        self.assertEqual(tmux.reap_dead(ttl_seconds=0), 1)
        self.assertIsNone(tmux.status("deadx"))

    def test_tool_specs_are_unique_and_complete(self):
        names = [spec["name"] for spec in toolset.TOOL_SPECS]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 24)
        for required in ("pilot_run", "pilot_expect", "pilot_send", "pilot_snapshot"):
            self.assertIn(required, names)
        for spec in toolset.TOOL_SPECS:
            self.assertIn("schema", spec)
            self.assertEqual(spec["schema"]["name"], spec["name"])

    def test_tool_handlers(self):
        handlers = {spec["name"]: spec["handler"] for spec in toolset.TOOL_SPECS}
        opened = json.loads(handlers["pilot_open"]({"command": "bash --norc -i", "name": "wrap1", "wait_ms": 400}))
        self.assertTrue(opened["ok"])
        screen = json.loads(handlers["pilot_screen"]({"name": "wrap1"}))
        self.assertTrue(screen["ok"])
        run = json.loads(handlers["pilot_run"]({"command": "printf 'TOOLRUN\\n'"}))
        self.assertIn("TOOLRUN", run["output"])
        sent = json.loads(handlers["pilot_send"]({"name": "wrap1", "text": "echo SENT_MARK", "wait_for": "SENT_MARK"}))
        self.assertTrue(sent["matched"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "screen.txt"
            saved = json.loads(handlers["pilot_snapshot"]({"name": "wrap1", "path": str(path)}))
            self.assertTrue(saved["ok"])
            self.assertIn("SENT_MARK", path.read_text())
        health = json.loads(handlers["pilot_health"]({}))
        self.assertTrue(health["ok"])
        closed = json.loads(handlers["pilot_close"]({"name": "wrap1"}))
        self.assertTrue(closed["ok"])


if __name__ == "__main__":
    unittest.main()
