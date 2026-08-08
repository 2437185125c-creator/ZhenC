"""Permission checking for tool execution.

Evaluation order (first match wins):

1. sensitive credential paths → always deny (defence in depth, not overridable)
2. explicit tool deny list → deny
3. explicit tool allow list → allow
4. path-level rules → deny / allow
5. command deny patterns → deny
6. mutating tool outside the review scope → deny (scope is a hard boundary)
7. FULL_AUTO mode → allow
8. read-only tools → allow
9. PLAN mode → block mutating tools
10. DEFAULT mode → mutating tools require user confirmation
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path

from code_review_harness.governance.modes import PermissionMode
from code_review_harness.governance.scope import ReviewScope

log = logging.getLogger(__name__)

# Paths that are always denied regardless of permission mode or scope.  These
# protect high-value credential material from LLM-directed access (including
# prompt injection).  Patterns use fnmatch syntax.
SENSITIVE_PATH_PATTERNS: tuple[str, ...] = (
    "*/.ssh/*",
    "*/.aws/credentials",
    "*/.aws/config",
    "*/.config/gcloud/*",
    "*/.azure/*",
    "*/.gnupg/*",
    "*/.docker/config.json",
    "*/.kube/config",
)


@dataclass(frozen=True)
class PermissionDecision:
    """Result of checking whether a tool invocation may run."""

    allowed: bool
    requires_confirmation: bool = False
    reason: str = ""


@dataclass(frozen=True)
class PathRule:
    """A glob-based path allow/deny rule."""

    pattern: str
    allow: bool = True


def _path_forms(file_path: str) -> tuple[str, ...]:
    """Path forms that should participate in policy matching.

    Directory-scoped tools (grep/glob) may operate on a root; appending a
    trailing slash lets deny patterns like ``*/.ssh/*`` match the directory
    root itself.  Relative paths get a ``./``-prefixed form so glob patterns
    that require a leading directory segment also match bare roots such as
    ``.ssh/id_rsa``.
    """
    normalized = file_path.rstrip("/")
    if not normalized:
        return (file_path,)
    forms = [normalized, normalized + "/"]
    if not normalized.startswith("/"):
        forms.append("./" + normalized)
        forms.append("./" + normalized + "/")
    return tuple(forms)


class PermissionChecker:
    """Evaluate tool usage against the configured mode, rules and scope."""

    def __init__(
        self,
        *,
        mode: PermissionMode = PermissionMode.DEFAULT,
        denied_tools: set[str] | None = None,
        allowed_tools: set[str] | None = None,
        path_rules: list[PathRule] | None = None,
        denied_commands: tuple[str, ...] = (),
    ) -> None:
        self._mode = mode
        self._denied_tools = set(denied_tools or ())
        self._allowed_tools = set(allowed_tools or ())
        self._path_rules = list(path_rules or [])
        self._denied_commands = tuple(denied_commands)
        self._scope: ReviewScope | None = None

    @property
    def mode(self) -> PermissionMode:
        return self._mode

    def set_mode(self, mode: PermissionMode) -> None:
        self._mode = mode

    def set_scope(self, scope: ReviewScope | None) -> None:
        self._scope = scope

    def evaluate(
        self,
        tool_name: str,
        *,
        is_read_only: bool,
        file_path: str | None = None,
        command: str | None = None,
    ) -> PermissionDecision:
        # 1. Built-in sensitive path protection — always active.
        if file_path:
            for candidate in _path_forms(file_path):
                for pattern in SENSITIVE_PATH_PATTERNS:
                    if fnmatch.fnmatch(candidate, pattern):
                        return PermissionDecision(
                            allowed=False,
                            reason=f"access denied: {file_path} is a sensitive credential path",
                        )

        # 2. Explicit tool deny list.
        if tool_name in self._denied_tools:
            return PermissionDecision(allowed=False, reason=f"{tool_name} is explicitly denied")

        # 3. Explicit tool allow list.
        if tool_name in self._allowed_tools:
            return PermissionDecision(allowed=True, reason=f"{tool_name} is explicitly allowed")

        # 4. Path-level rules.
        if file_path and self._path_rules:
            for candidate in _path_forms(file_path):
                for rule in self._path_rules:
                    if fnmatch.fnmatch(candidate, rule.pattern):
                        if not rule.allow:
                            return PermissionDecision(
                                allowed=False,
                                reason=f"path {file_path} matches deny rule {rule.pattern!r}",
                            )

        # 5. Command deny patterns (e.g. deny "rm -rf").
        if command:
            for pattern in self._denied_commands:
                if fnmatch.fnmatch(command, pattern):
                    return PermissionDecision(
                        allowed=False,
                        reason=f"command matches deny pattern {pattern!r}",
                    )

        # 6. Scope is a hard boundary for mutating tools: you may only modify
        #    files that are part of the change under review.
        if not is_read_only and file_path and self._scope is not None:
            resolved = Path(file_path)
            if not self._scope.allows(resolved):
                return PermissionDecision(
                    allowed=False,
                    reason=f"path {file_path} is outside the review scope (only changed files may be modified)",
                )

        # 7. FULL_AUTO: allow everything.
        if self._mode == PermissionMode.FULL_AUTO:
            return PermissionDecision(allowed=True, reason="auto mode allows all tools")

        # 8. Read-only tools always allowed.
        if is_read_only:
            return PermissionDecision(allowed=True, reason="read-only tools are allowed")

        # 9. PLAN mode blocks mutating tools.
        if self._mode == PermissionMode.PLAN:
            return PermissionDecision(
                allowed=False,
                reason="plan mode blocks mutating tools until the user exits plan mode",
            )

        # 10. DEFAULT mode: mutating tools require confirmation.
        return PermissionDecision(
            allowed=False,
            requires_confirmation=True,
            reason=(
                f"{tool_name} modifies the repository and requires your approval "
                "(default mode). Approve it, or run in full_auto mode to allow automatically."
            ),
        )
