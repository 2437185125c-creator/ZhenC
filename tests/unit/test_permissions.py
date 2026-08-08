"""Tests for the permission checker — the governance core."""
from __future__ import annotations

from pathlib import Path

from code_review_harness.governance.modes import PermissionMode
from code_review_harness.governance.permissions import PathRule, PermissionChecker
from code_review_harness.governance.scope import ReviewScope


def make_checker(**kwargs):
    return PermissionChecker(**kwargs)


def test_read_only_always_allowed():
    checker = make_checker(mode=PermissionMode.PLAN)
    decision = checker.evaluate("read_file", is_read_only=True, file_path="app.py")
    assert decision.allowed
    assert not decision.requires_confirmation


def test_mutating_denied_in_plan_mode():
    checker = make_checker(mode=PermissionMode.PLAN)
    decision = checker.evaluate("apply_patch", is_read_only=False, file_path="app.py")
    assert not decision.allowed
    assert not decision.requires_confirmation


def test_mutating_requires_confirmation_in_default_mode():
    checker = make_checker(mode=PermissionMode.DEFAULT)
    decision = checker.evaluate("apply_patch", is_read_only=False, file_path="app.py")
    assert not decision.allowed
    assert decision.requires_confirmation


def test_mutating_allowed_in_full_auto():
    checker = make_checker(mode=PermissionMode.FULL_AUTO)
    decision = checker.evaluate("apply_patch", is_read_only=False, file_path="app.py")
    assert decision.allowed


def test_sensitive_path_denied_even_in_full_auto():
    checker = make_checker(mode=PermissionMode.FULL_AUTO)
    decision = checker.evaluate("read_file", is_read_only=True, file_path=".ssh/id_rsa")
    assert not decision.allowed
    assert "sensitive" in decision.reason


def test_sensitive_path_denied_with_absolute_path():
    checker = make_checker(mode=PermissionMode.FULL_AUTO)
    decision = checker.evaluate("read_file", is_read_only=True, file_path="/home/u/.aws/credentials")
    assert not decision.allowed


def test_denied_tools_always_blocked():
    checker = make_checker(denied_tools={"rm_rf"})
    decision = checker.evaluate("rm_rf", is_read_only=False)
    assert not decision.allowed


def test_allowed_tools_bypass_mode():
    checker = make_checker(mode=PermissionMode.PLAN, allowed_tools={"apply_patch"})
    decision = checker.evaluate("apply_patch", is_read_only=False, file_path="app.py")
    assert decision.allowed


def test_path_deny_rule_blocks_read():
    checker = make_checker(path_rules=[PathRule(pattern="secret/*", allow=False)])
    decision = checker.evaluate("read_file", is_read_only=True, file_path="secret/key.txt")
    assert not decision.allowed


def test_command_deny_pattern():
    checker = make_checker(denied_commands=("*rm -rf*",))
    decision = checker.evaluate("bash", is_read_only=False, command="rm -rf /")
    assert not decision.allowed


def test_scope_blocks_mutation_outside_changed_files(tmp_path):
    root = Path(tmp_path)
    changed = root / "changed.py"
    outside = root / "outside.py"
    scope = ReviewScope(root=root, changed_files=frozenset({changed.resolve()}))
    checker = make_checker(mode=PermissionMode.FULL_AUTO)
    checker.set_scope(scope)

    # Inside scope: allowed even in full_auto.
    decision = checker.evaluate("apply_patch", is_read_only=False, file_path=str(changed.resolve()))
    assert decision.allowed

    # Outside scope: denied even in full_auto (hard boundary).
    decision = checker.evaluate("apply_patch", is_read_only=False, file_path=str(outside.resolve()))
    assert not decision.allowed
    assert "outside the review scope" in decision.reason


def test_scope_does_not_restrict_reads(tmp_path):
    root = Path(tmp_path)
    scope = ReviewScope(root=root, changed_files=frozenset())
    checker = make_checker(mode=PermissionMode.FULL_AUTO)
    checker.set_scope(scope)
    decision = checker.evaluate("read_file", is_read_only=True, file_path=str((root / "anywhere.py").resolve()))
    assert decision.allowed
