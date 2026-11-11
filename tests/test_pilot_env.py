"""Tests for Pilot as a terminal backend (real tmux; skipped without it).

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import unittest
import uuid
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

from hermes_pilot import pilot_env  # noqa: E402
from hermes_pilot import pilot_tmux as tmux  # noqa: E402

HAVE_TMUX = shutil.which("tmux") is not None


class FakeCtx:
    def __init__(self) -> None:
        self.providers: list[object] = []
        self.tools: list[dict] = []
        self.commands: list[str] = []
        self.cli_commands: list[str] = []
        self.prompt_sections: list[str] = []

    def register_terminal_environment_provider(self, provider):
        self.providers.append(provider)

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_hook(self, *args, **kwargs):
        pass

    def register_command(self, name, *_a, **_kw):
        self.commands.append(name)

    def register_cli_command(self, name, *_a, **_kw):
        self.cli_commands.append(name)

    def register_system_prompt_section(self, *args, **kwargs):
        self.prompt_sections.append(args[0] if args else "")

    def get_config(self, key, default=None):
        return default


class ProviderTest(unittest.TestCase):
    def test_registered_as_terminal_backend(self):
        ctx = FakeCtx()
        import hermes_pilot

        hermes_pilot.register(ctx)
        self.assertEqual([p.name for p in ctx.providers], ["pilot"])
        provider = ctx.providers[0]
        self.assertTrue(provider.is_available() if HAVE_TMUX else not provider.is_available())
        self.assertFalse(provider.is_remote)
        self.assertFalse(provider.is_container)

    def test_provider_inherits_counterpart_abc_when_hermes_is_importable(self):
        """Hermes ignores a terminal backend provider that does not inherit its ABC."""
        try:
            from agent.terminal_env_provider import TerminalEnvironmentProvider
        except ImportError:
            self.skipTest("hermes-agent not on sys.path")
        self.assertTrue(issubclass(pilot_env.PilotTerminalProvider, TerminalEnvironmentProvider))

    def test_session_name_is_stable_and_unique(self):
        self.assertEqual(pilot_env.session_name("abc"), pilot_env.session_name("abc"))
        self.assertNotEqual(pilot_env.session_name("abc"), pilot_env.session_name("abd"))
        self.assertTrue(pilot_env.session_name("abc").startswith("term-abc-"))


@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class ExecuteTest(unittest.TestCase):
    def setUp(self):
        self.task = f"t-{uuid.uuid4().hex[:8]}"
        self.env = pilot_env.PilotEnvironment(cwd="/tmp", timeout=10, task_id=self.task)

    def tearDown(self):
        self.env.cleanup()
        tmux.close(pilot_env.session_name(self.task), missing_ok=True)

    def run_cmd(self, command, **kw):
        return self.env.execute(command, **kw)

    def test_echo_and_exit_code(self):
        result = self.run_cmd("echo hello-pilot")
        self.assertEqual(result["returncode"], 0)
        self.assertIn("hello-pilot", result["output"])
        self.assertNotIn("__PILOT_TERM_END__", result["output"])

    def test_failure_exit_code(self):
        self.assertEqual(self.run_cmd("false")["returncode"], 1)

    def test_cwd_persists_and_is_observed(self):
        self.run_cmd("cd /usr")
        result = self.run_cmd("pwd")
        self.assertTrue(result["cwd_observed"])
        self.assertEqual(result["cwd"], "/usr")
        self.assertIn("/usr", result["output"])

    def test_env_persists(self):
        self.run_cmd("export PILOT_TEST_VAR=carried")
        self.assertIn("carried", self.run_cmd("echo $PILOT_TEST_VAR")["output"])

    def test_multiline_command(self):
        result = self.run_cmd("printf 'a\\nb\\n' | wc -l")
        self.assertEqual(result["output"].strip(), "2")

    def test_bad_cwd_reports_99(self):
        result = self.run_cmd("echo nope", cwd="/definitely/not/here")
        self.assertEqual(result["returncode"], 99)

    def test_timeout_leaves_session_attachable(self):
        result = self.run_cmd("sleep 5", timeout=1)
        self.assertEqual(result["returncode"], 124)
        self.assertTrue(result.get("hermes_timed_out"))
        self.assertIn(self.env.name, result["output"])
        # The next call must not type into the sleeping program.
        busy = self.run_cmd("echo next")
        self.assertEqual(busy["returncode"], pilot_env.BUSY_RC)
        self.assertIn("still running", busy["output"])

    def test_cleanup_resets_session(self):
        self.run_cmd("export GONE=1")
        self.env.cleanup()
        result = self.run_cmd("echo back")
        self.assertEqual(result["returncode"], 0)
        self.assertIn("back", result["output"])
        self.assertNotIn("1", result["output"])


@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class ReuseTest(unittest.TestCase):
    def test_same_task_reuses_shell_state(self):
        task = f"reuse-{uuid.uuid4().hex[:8]}"
        first = pilot_env.PilotTerminalProvider().create_environment(cwd="/tmp", timeout=10, task_id=task)
        first.execute("export SHARED=yes")
        second = pilot_env.PilotTerminalProvider().create_environment(cwd="/tmp", timeout=10, task_id=task)
        try:
            self.assertIn("yes", second.execute("echo $SHARED")["output"])
        finally:
            first.cleanup()
            second.cleanup()
            tmux.close(pilot_env.session_name(task), missing_ok=True)


if __name__ == "__main__":
    unittest.main()
