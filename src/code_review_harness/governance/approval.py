"""Human-in-the-loop approval gate.

The approval gate is the workflow-control hook where a human decides whether a
mutating action may proceed.  The interface is a simple async predicate so
tests can inject deterministic fakes and the CLI can prompt interactively.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

# async fn(tool_name: str, reason: str) -> bool
ApprovalGate = Callable[[str, str], Awaitable[bool]]


async def auto_approve(tool_name: str, reason: str) -> bool:
    """Approval gate that always approves (full_auto / CI)."""
    del tool_name, reason
    return True


async def auto_deny(tool_name: str, reason: str) -> bool:
    """Approval gate that always rejects (used in tests)."""
    del tool_name, reason
    return False


async def console_approval(tool_name: str, reason: str) -> bool:
    """Interactive approval gate for the CLI.

    Blocks the agent loop and asks the user to type ``y``/``n`` (or an empty
    line for yes) before the tool may run.
    """
    prompt = (
        f"\n[approval required] {tool_name}\n"
        f"  reason: {reason}\n"
        f"  proceed? [y/N] "
    )
    line = await asyncio.to_thread(input, prompt)
    return line.strip().lower() in {"y", "yes", ""}
