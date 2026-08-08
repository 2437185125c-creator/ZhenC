"""Unit tests for the ChangeSet backup/rollback logic."""
from __future__ import annotations

from code_review_harness.fix.applier import ChangeSet


def test_backup_snapshots_content(tmp_path):
    (tmp_path / "a.py").write_text("old", encoding="utf-8")
    changeset = ChangeSet(root=tmp_path)
    changeset.backup(tmp_path / "a.py")
    (tmp_path / "a.py").write_text("new", encoding="utf-8")

    assert changeset.detect_writes() == [tmp_path / "a.py"]
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "new"


def test_rollback_restores_content(tmp_path):
    (tmp_path / "a.py").write_text("old", encoding="utf-8")
    changeset = ChangeSet(root=tmp_path)
    changeset.backup(tmp_path / "a.py")
    (tmp_path / "a.py").write_text("new", encoding="utf-8")

    changeset.rollback()
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "old"
    assert changeset.written == []


def test_rollback_deletes_new_files(tmp_path):
    changeset = ChangeSet(root=tmp_path)
    changeset.backup(tmp_path / "new.py")  # doesn't exist yet -> backup ""
    (tmp_path / "new.py").write_text("content", encoding="utf-8")

    changeset.detect_writes()
    changeset.rollback()
    assert not (tmp_path / "new.py").exists()


def test_backup_is_idempotent(tmp_path):
    (tmp_path / "a.py").write_text("v1", encoding="utf-8")
    changeset = ChangeSet(root=tmp_path)
    changeset.backup(tmp_path / "a.py")
    (tmp_path / "a.py").write_text("v2", encoding="utf-8")
    changeset.backup(tmp_path / "a.py")  # should keep v1

    changeset.rollback()
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "v1"
