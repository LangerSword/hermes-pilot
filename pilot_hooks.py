"""Approval policy for Pilot's mutating tools.

Hermes's own terminal tool asks before it runs a model-authored command. Pilot
is a second shell, so it must ask too. This hook escalates mutating calls to
the human-approval gate; read-only screen/list/wait calls stay silent. Hermes
fails closed for cron and other unattended runs.
"""

from __future__ import annotations

import json

APPROVAL_TOOLS = frozenset(
    {
        "pilot_open",
        "pilot_run",
        "pilot_type",
        "pilot_send",
        "pilot_expect",
        "pilot_upload",
        "pilot_download",
    }
)
PILOT_READ_ONLY_ACTIONS = frozenset({"screen", "wait", "list", "status", "attach"})


def _text(args: dict) -> str:
    text = str(args.get("text") or "")
    keys = args.get("keys") or []
    if keys:
        return f"{text} [keys: {', '.join(str(k) for k in keys)}]".strip()
    return text


def _detail(tool_name: str, args: dict) -> str:
    if tool_name == "pilot_open":
        return str(args.get("command") or "")
    if tool_name == "pilot_run":
        return str(args.get("command") or "")
    if tool_name in {"pilot_type", "pilot_send"}:
        return _text(args)
    if tool_name == "pilot_expect":
        return json.dumps(args.get("steps") or [], ensure_ascii=False)
    if tool_name == "pilot_upload":
        return f"{args.get('local_path') or ''} -> {args.get('remote_path') or '(default)'}"
    if tool_name == "pilot_download":
        return f"{args.get('remote_path') or ''} -> {args.get('local_path') or '(default)'}"
    return ""


def pre_tool_call(tool_name: str, args: dict | None = None, **_kwargs):
    """Escalate mutating Pilot calls; return None for read-only calls."""
    args = args if isinstance(args, dict) else {}
    if tool_name == "pilot":
        action = str(args.get("action") or "").strip().lower()
        if action in PILOT_READ_ONLY_ACTIONS:
            return None
        detail = str(args.get("command") or args.get("text") or args.get("name") or "")
        message = f"pilot {action or '?'}: {detail}".strip()
    elif tool_name in APPROVAL_TOOLS:
        detail = _detail(tool_name, args)
        message = f"{tool_name}: {detail}".strip()
    else:
        return None
    return {
        "action": "approve",
        "message": message,
        "rule_key": f"pilot:{tool_name}",
    }


__all__ = ["APPROVAL_TOOLS", "PILOT_READ_ONLY_ACTIONS", "pre_tool_call"]
