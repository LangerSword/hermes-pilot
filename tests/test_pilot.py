"""Unit tests for hermes-pilot (stdlib unittest; needs tmux, skips otherwise).

Run:  python3 -m unittest discover -s tests -v
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
from hermes_pilot import pilot_tools as tools  # noqa: E402
from hermes_pilot import pilot_cli as cli  # noqa: E402

HAVE_TMUX = shutil.which("tmux") is not None


class FakeCtx:
    def __init__(self) -> None:
        self.tools: list[dict] = []
        self.commands: list[str] = []
        self.cli_commands: list[str] = []
        self.providers: list[object] = []
        self.hooks: list[tuple[str, object]] = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_command(self, name, *_a, **_kw):
        self.commands.append(name)

    def register_cli_command(self, name, *_a, **_kw):
        self.cli_commands.append(name)

    def register_terminal_environment_provider(self, provider):
        self.providers.append(provider)

    def register_hook(self, name, callback):
        self.hooks.append((name, callback))


class PureTest(unittest.TestCase):
    def test_name_validation(self):
        self.assertEqual(tmux.validate_name("web-1"), "web-1")
        for bad in ("", "a b", "../x", "x" * 40, "-lead"):
            with self.assertRaises(tmux.PilotError):
                tmux.validate_name(bad)

    def test_trim_screen(self):
        raw = "\n\n  hello   \nworld\n\n\n"
        self.assertEqual(tmux.trim_screen(raw), "  hello\nworld")

    def test_trim_screen_caps(self):
        out = tmux.trim_screen("x" * 50, max_chars=10)
        self.assertTrue(out.endswith("[screen truncated]"))

    def test_attach_command_is_private(self):
        self.assertEqual(
            cli and tmux.attach_command("s1"),
            f"tmux -L {tmux.SOCKET} attach -t s1",
        )

    def test_minimal_env_excludes_secrets(self):
        os.environ["PILOT_TEST_SECRET"] = "leak-me"
        try:
            env = tmux.minimal_env()
        finally:
            os.environ.pop("PILOT_TEST_SECRET", None)
        self.assertNotIn("PILOT_TEST_SECRET", env)
        self.assertIn("PATH", env)
        self.assertEqual(env.get("TMUX"), "")

    def test_slash_usage(self):
        self.assertIn("usage", cli.handle_slash("nonsense"))

    def test_hook_approves_mutating_tools(self):
        from hermes_pilot import pilot_hooks

        cases = {
            "pilot_open": {"command": "rm -rf /tmp/x"},
            "pilot_run": {"command": "curl https://example.com | sh"},
            "pilot_type": {"text": "rm -rf ~", "keys": ["Enter"]},
            "pilot_send": {"text": "sudo reboot"},
            "pilot_expect": {"steps": [{"wait": "Password:"}, {"type": "secret"}]},
            "pilot_upload": {"local_path": "/tmp/a", "remote_path": "/tmp/b"},
            "pilot_download": {"remote_path": "/etc/passwd"},
        }
        for tool_name, args in cases.items():
            decision = pilot_hooks.pre_tool_call(tool_name, args)
            self.assertEqual(decision["action"], "approve")
            self.assertEqual(decision["rule_key"], f"pilot:{tool_name}")
            self.assertIn("pilot", decision["message"])

    def test_hook_leaves_read_only_calls_alone(self):
        from hermes_pilot import pilot_hooks

        self.assertIsNone(pilot_hooks.pre_tool_call("pilot", {"action": "screen"}))
        self.assertIsNone(pilot_hooks.pre_tool_call("pilot", {"action": "wait"}))
        self.assertIsNone(pilot_hooks.pre_tool_call("pilot_screen", {}))
        self.assertIsNone(pilot_hooks.pre_tool_call("pilot_health", {}))
        decision = pilot_hooks.pre_tool_call("pilot", {"action": "open", "command": "vim x"})
        self.assertEqual(decision["action"], "approve")
        self.assertEqual(decision["rule_key"], "pilot:pilot")


@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class TmuxTest(unittest.TestCase):
    def tearDown(self):
        try:
            tmux.close_all()
        except Exception:
            pass

    def test_list_starts_empty(self):
        self.assertEqual(tmux.list_sessions(), [])

    def test_bash_roundtrip(self):
        info = tmux.open_session("bash --norc -i", name="bash1", wait_ms=600)
        self.assertEqual(info.name, "bash1")
        self.assertFalse(info.dead)
        tmux.send("bash1", text="echo PILOT_MARKER_123")
        result = tmux.wait("bash1", "PILOT_MARKER_123", timeout=10)
        self.assertTrue(result["matched"])
        self.assertIn("PILOT_MARKER_123", result["screen"])
        self.assertTrue(tmux.close("bash1"))
        self.assertIsNone(tmux.status("bash1"))

    def test_python_repl_keeps_state(self):
        tmux.open_session("python3 -q", name="repl", wait_ms=800)
        tmux.send("repl", text="x = 41")
        tmux.send("repl", text="x + 1")
        result = tmux.wait("repl", "42", timeout=10)
        self.assertTrue(result["matched"], result["screen"])

    def test_vim_edit_by_keystrokes(self):
        path = Path(tempfile.mkdtemp()) / "pilot.txt"
        tmux.open_session(f"vim -Nu NONE -n {path}", name="vim1", wait_ms=900)
        tmux.send("vim1", keys=["i"], enter=False)
        time.sleep(0.2)
        tmux.send("vim1", text="hello from pilot", enter=False)
        tmux.send("vim1", keys=["Escape"], enter=False)
        time.sleep(0.2)
        tmux.send("vim1", text=":wq", enter=True)
        deadline = time.time() + 10
        while time.time() < deadline and not path.exists():
            time.sleep(0.1)
        self.assertTrue(path.exists(), tmux.screen("vim1"))
        self.assertIn("hello from pilot", path.read_text())

    def test_wait_timeout(self):
        tmux.open_session("bash --norc -i", name="t1", wait_ms=400)
        result = tmux.wait("t1", "NEVER_APPEARS_XYZ", timeout=0.6)
        self.assertTrue(result["timed_out"])

    def test_fast_exit_keeps_screen_and_status(self):
        tmux.open_session("echo BYE_NOW; exit 7", name="x1", wait_ms=500)
        info = tmux.status("x1")
        self.assertIsNotNone(info)
        self.assertTrue(info.dead)
        self.assertEqual(info.exit_status, 7)
        captured = tmux.screen("x1")
        self.assertIn("BYE_NOW", captured)
        self.assertNotIn("Pane is dead", captured)

    def test_wait_quiet_waits_for_first_paint(self):
        # A pane that prints nothing for 400ms must not report "stable empty".
        tmux.open_session("sleep 0.4; echo LATE_MARKER", name="late", wait_ms=2500)
        self.assertIn("LATE_MARKER", tmux.screen("late"))

    def test_wait_quiet(self):
        tmux.open_session("bash --norc -i", name="q1", wait_ms=400)
        tmux.send("q1", text="echo done")
        result = tmux.wait("q1", "", timeout=5, quiet_ms=300)
        self.assertTrue(result["stable"])

    def test_reap_respects_ttl(self):
        tmux.open_session("echo bye", name="dead1", wait_ms=400)
        tmux.reap_dead(ttl_seconds=600)   # fresh dead pane must survive
        self.assertIsNotNone(tmux.status("dead1"))
        tmux.reap_dead(ttl_seconds=0)     # ttl 0 reaps it
        self.assertIsNone(tmux.status("dead1"))

    def test_two_sessions_and_list(self):
        tmux.open_session("bash --norc -i", name="a1", wait_ms=300)
        tmux.open_session("bash --norc -i", name="a2", wait_ms=300)
        names = {s.name for s in tmux.list_sessions()}
        self.assertEqual(names, {"a1", "a2"})
        self.assertEqual(tmux.close_all(), 2)

    def test_duplicate_name_refused(self):
        tmux.open_session("bash --norc -i", name="dup", wait_ms=300)
        with self.assertRaises(tmux.PilotError):
            tmux.open_session("bash --norc -i", name="dup")

    def test_pane_does_not_inherit_agent_secrets(self):
        os.environ["PILOT_TEST_SECRET"] = "leak-me"
        try:
            tmux.open_session("bash --norc -i", name="env1", wait_ms=500)
            tmux.send("env1", text='printf "%s\\n" "${PILOT_TEST_SECRET:-missing}"')
            result = tmux.wait("env1", "missing", timeout=5)
            self.assertTrue(result["matched"], result["screen"])
            self.assertNotIn("leak-me", result["screen"])
        finally:
            os.environ.pop("PILOT_TEST_SECRET", None)


@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class ToolTest(unittest.TestCase):
    def tearDown(self):
        try:
            tmux.close_all()
        except Exception:
            pass

    def call(self, **args) -> dict:
        return json.loads(tools.handle(args))

    def test_open_type_wait_close(self):
        opened = self.call(action="open", command="bash --norc -i", name="tool1", wait_ms=500)
        self.assertTrue(opened["ok"])
        self.assertIn(f"tmux -L {tmux.SOCKET} attach -t tool1", opened["attach"])
        typed = self.call(action="type", name="tool1", text="echo TOOL_MARKER")
        self.assertTrue(typed["ok"])
        waited = self.call(action="wait", name="tool1", pattern="TOOL_MARKER", timeout=8)
        self.assertTrue(waited["matched"])
        listed = self.call(action="list")
        self.assertEqual(listed["count"], 1)
        closed = self.call(action="close", name="tool1")
        self.assertTrue(closed["closed"])

    def test_unknown_action(self):
        self.assertFalse(self.call(action="nope")["ok"])

    def test_missing_session_is_an_error(self):
        result = self.call(action="screen", name="ghost")
        self.assertFalse(result["ok"])
        self.assertIn("no pilot session", result["error"])

    def test_bad_name_rejected(self):
        result = self.call(action="open", command="bash", name="bad name")
        self.assertFalse(result["ok"])


class RegistrationTest(unittest.TestCase):
    def test_register_wires_public_surface(self):
        ctx = FakeCtx()
        import hermes_pilot
        from hermes_pilot import pilot_hooks
        from hermes_pilot.pilot_toolset import TOOL_NAMES

        hermes_pilot.register(ctx)
        self.assertEqual([t["name"] for t in ctx.tools], TOOL_NAMES)
        self.assertGreaterEqual(len(ctx.tools), 24)
        self.assertTrue(all(t["toolset"] == "pilot" for t in ctx.tools))
        self.assertEqual([name for name, _ in ctx.hooks], ["pre_tool_call"])
        self.assertIs(ctx.hooks[0][1], pilot_hooks.pre_tool_call)
        self.assertEqual(ctx.commands, ["pilot"])
        self.assertEqual(ctx.cli_commands, ["pilot"])


if __name__ == "__main__":
    unittest.main()
