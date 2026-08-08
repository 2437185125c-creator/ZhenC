"""Synchronous wrapper around the async pipeline for CLI entry points."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, TypeVar

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """Run a coroutine to completion in the current thread.

    The harness core is fully async (asyncio); this wrapper is the only place
    a sync caller (the CLI) touches an event loop.
    """
    return asyncio.run(coro)
