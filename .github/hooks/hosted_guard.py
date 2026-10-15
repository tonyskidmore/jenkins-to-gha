"""Copilot preToolUse hook: ask the user before an agent starts a j2gha run on GitHub-hosted runners.

Hosted runs spend the repository owner's GitHub Actions minutes, so the agent should not start one on its own. This
hook answers "ask" for a shell command that runs `j2gha run` or `j2gha pipeline` with `hosted` among its tiers:
Copilot CLI then prompts the user, and non-interactive runs and the cloud agent treat it as a deny. Set
J2GHA_AGENT_HOSTED=1 in the environment Copilot starts from to let the agent start hosted runs itself.

It is a backstop, not the control: the harness's budget guard still decides whether a hosted run may spend minutes.
Any error lets the call through: a hook that crashes would deny every tool call.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

RUN = re.compile(r"\bj2gha\b.*\b(run|pipeline)\b")


def hosted_tiers(command: str) -> bool:
    if not RUN.search(command):
        return False
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        words = command.split()
    for i, word in enumerate(words):
        value = None
        if word == "--tier" and i + 1 < len(words):
            value = words[i + 1]
        elif word.startswith("--tier="):
            value = word.split("=", 1)[1]
        if value is not None and "hosted" in (t.strip() for t in value.split(",")):
            return True
    return False


def command_of(event: dict) -> str:
    args = event.get("toolArgs", event.get("tool_input"))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return args
    return str(args.get("command", "")) if isinstance(args, dict) else ""


def decide(event: dict, env: dict) -> dict | None:
    tool = str(event.get("toolName", event.get("tool_name", ""))).lower()
    if tool not in ("bash", "powershell", "shell") or env.get("J2GHA_AGENT_HOSTED") == "1":
        return None
    if not hosted_tiers(command_of(event)):
        return None
    return {"permissionDecision": "ask",
            "permissionDecisionReason": "j2gha: a GitHub-hosted run spends the repository owner's Actions minutes. "
                                        "Ask the user first and run `uv run j2gha budget`; prefer `--tier selfhosted` "
                                        "(no minutes). The user can run it themselves or set J2GHA_AGENT_HOSTED=1."}


def main() -> int:
    try:
        decision = decide(json.load(sys.stdin), dict(os.environ))
    except Exception:  # noqa: BLE001 - never block a tool call because of this hook
        return 0
    if decision:
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
