"""Governance layer: permission modes, checker, scope, approval gate, executor."""

from code_review_harness.governance.approval import (
    ApprovalGate,
    auto_approve,
    auto_deny,
    console_approval,
)
from code_review_harness.governance.executor import GovernedToolExecutor
from code_review_harness.governance.modes import PermissionMode
from code_review_harness.governance.permissions import (
    SENSITIVE_PATH_PATTERNS,
    PathRule,
    PermissionChecker,
    PermissionDecision,
)
from code_review_harness.governance.scope import ReviewScope

__all__ = [
    "ApprovalGate",
    "GovernedToolExecutor",
    "PathRule",
    "PermissionChecker",
    "PermissionDecision",
    "PermissionMode",
    "ReviewScope",
    "SENSITIVE_PATH_PATTERNS",
    "auto_approve",
    "auto_deny",
    "console_approval",
]
