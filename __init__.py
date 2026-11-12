"""Pilot: give Hermes hands on a real interactive terminal.

A private tmux server hosts every session, so the agent can drive programs that
need a TTY (ssh, vim, htop, fzf, installers, REPLs) and read the screen back as
text. The human can attach to the same pane at any time and take over.

Wiring goes through the public plugin API: ``ctx.register_tool``,
``ctx.register_command`` and ``ctx.register_cli_command``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__version__ = "0.3.2"


def register(ctx) -> None:
    """Plugin entry point, called by the Hermes plugin loader."""
    from .pilot_cli import handle_cli, handle_slash, setup_cli
    from .pilot_env import PilotTerminalProvider
    from .pilot_hooks import pre_tool_call
    from .pilot_toolset import TOOLSET, TOOL_SPECS

    # The regular `terminal` tool can run inside Pilot: persistent cwd/env, a
    # real TTY, and interactive commands left attachable instead of killed.
    ctx.register_terminal_environment_provider(PilotTerminalProvider())

    # A second shell needs the same approval gate as the built-in terminal.
    # Read-only calls pass through; mutating calls go to the human gate.
    ctx.register_hook("pre_tool_call", pre_tool_call)

    for spec in TOOL_SPECS:
        def tool_handler(args: dict, _run=spec["handler"], **_kw) -> str:
            return _run(args or {})

        ctx.register_tool(
            name=spec["name"],
            toolset=TOOLSET,
            schema=spec["schema"],
            handler=tool_handler,
            description=spec["description"],
            emoji=spec.get("emoji", "🕹️"),
        )

    ctx.register_command(
        "pilot",
        handle_slash,
        description="Live pilot sessions: list | screen <name> | attach <name> | kill <name>",
        args_hint="[list|screen|attach|kill]",
    )

    ctx.register_cli_command(
        "pilot",
        help="Inspect, attach to, or close the agent's interactive terminal sessions",
        description=(
            "Pilot keeps a private tmux server of interactive terminals the agent can drive. "
            "List them, read a pane, attach from a real terminal, or close them."
        ),
        setup_fn=setup_cli,
        handler_fn=handle_cli,
    )


__all__ = ["register", "__version__"]
