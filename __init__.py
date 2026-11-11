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

__version__ = "0.1.0"


def register(ctx) -> None:
    """Plugin entry point, called by the Hermes plugin loader."""
    from .pilot_cli import handle_cli, handle_slash, setup_cli
    from .pilot_tools import TOOL_NAME, TOOLSET, handle, tool_schema

    def tool_handler(args: dict, **_kw) -> str:
        return handle(args or {})

    ctx.register_tool(
        name=TOOL_NAME,
        toolset=TOOLSET,
        schema=tool_schema(),
        handler=tool_handler,
        description=(
            "Drive a real interactive terminal: ssh, vim, htop, fzf, installers and REPLs, "
            "by typing keys and reading the screen."
        ),
        emoji="🕹️",
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
