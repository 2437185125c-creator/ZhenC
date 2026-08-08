"""File-change application with backup and rollback.

The fix pipeline snapshots every file before the agent touches it, so a failed
fix run can restore the repository to its prior state — the harness's
rollback safety net.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class ChangeSet:
    """Tracks modified files and their pre-change content."""

    root: Path
    backups: dict[Path, str] = field(default_factory=dict)
    written: list[Path] = field(default_factory=list)

    def backup(self, path: Path) -> None:
        """Snapshot a file's current content if we haven't already."""
        resolved = path.resolve()
        if resolved in self.backups:
            return
        try:
            self.backups[resolved] = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            self.backups[resolved] = ""  # new file — rollback = delete

    def record_write(self, path: Path) -> None:
        self.backup(path)
        self.written.append(path.resolve())

    def changed_python_files(self) -> list[Path]:
        return [p for p in self.written if p.suffix == ".py"]

    def detect_writes(self) -> list[Path]:
        """Find backed-up files whose current content differs from the snapshot."""
        for path, content in self.backups.items():
            if path in self.written:
                continue
            try:
                current = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                if content:
                    self.written.append(path)  # file was deleted
                continue
            if current != content:
                self.written.append(path)
        return list(self.written)

    def rollback(self) -> list[Path]:
        """Restore all files to their backup content; return restored paths."""
        restored: list[Path] = []
        for path, content in self.backups.items():
            try:
                if content:
                    path.write_text(content, encoding="utf-8")
                elif path.exists():
                    path.unlink()
                restored.append(path)
            except OSError as exc:
                log.error("rollback failed for %s: %s", path, exc)
        self.written.clear()
        return restored
