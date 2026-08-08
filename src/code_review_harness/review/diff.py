"""Git diff extraction and parsing.

The review agent works on *changes*, not whole files: we parse the working-tree
diff (staged + unstaged + untracked) into a list of :class:`ChangedFile`, which
both feeds the review prompt and defines the review scope (what the agent may
modify later).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

from code_review_harness.governance.scope import ReviewScope

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class DiffHunk:
    """A ``@@ -old +new @@`` hunk inside a file diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int


@dataclass
class ChangedFile:
    """A file touched by the change under review."""

    path: Path
    status: str  # A=added, M=modified, D=deleted, ?=untracked
    hunks: list[DiffHunk] = field(default_factory=list)

    @property
    def is_python(self) -> bool:
        return self.path.suffix == ".py"

    @property
    def added_line_numbers(self) -> list[int]:
        """Line numbers (1-based, new file) of lines added by the diff."""
        lines: list[int] = []
        for hunk in self.hunks:
            new_line = hunk.new_start
            # We can't reconstruct exact added lines without the hunk body, so
            # approximate with the full hunk span — good enough for scoping.
            lines.extend(range(new_line, new_line + hunk.new_count))
        return lines


def parse_diff(diff_text: str) -> list[ChangedFile]:
    """Parse a unified ``git diff`` output into changed files."""
    files: list[ChangedFile] = []
    current: ChangedFile | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            if current is not None:
                files.append(current)
            parts = raw_line[len("diff --git ") :].split()
            if parts:
                current = ChangedFile(path=Path(parts[-1][2:] if parts[-1].startswith("b/") else parts[-1]), status="M")
            continue
        if current is None:
            continue
        if raw_line.startswith("new file mode"):
            current.status = "A"
            continue
        if raw_line.startswith("deleted file mode"):
            current.status = "D"
            continue
        if raw_line.startswith("rename from "):
            current.status = "R"
            continue
        match = HUNK_RE.match(raw_line)
        if match:
            old_start = int(match.group(1))
            old_count = int(match.group(2) or 1)
            new_start = int(match.group(3))
            new_count = int(match.group(4) or 1)
            current.hunks.append(DiffHunk(old_start, old_count, new_start, new_count))
    if current is not None:
        files.append(current)
    return files


async def _git(cwd: Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode("utf-8", errors="replace")


async def changed_files_from_repo(cwd: Path) -> list[ChangedFile]:
    """Collect changed files from the working tree: staged + unstaged + untracked."""
    combined = (
        await _git(cwd, "diff", "HEAD")
        + "\n"
        + await _git(cwd, "diff", "--cached")
    )
    files = parse_diff(combined)

    # Untracked files: ``git status --porcelain`` lists them as "?? path".
    status = await _git(cwd, "status", "--porcelain")
    for line in status.splitlines():
        if line.startswith("??"):
            name = line[3:].strip()
            if name:
                files.append(ChangedFile(path=Path(name), status="?"))
    return files


async def repo_diff_text(cwd: Path) -> str:
    """Full diff text (staged + unstaged) for the review prompt."""
    parts = [
        await _git(cwd, "diff", "HEAD"),
        await _git(cwd, "diff", "--cached"),
    ]
    return "\n".join(p for p in parts if p.strip())


def build_scope(cwd: Path, files: list[ChangedFile]) -> ReviewScope:
    """Build the review scope from the changed files (absolute paths)."""
    root = cwd.resolve()
    changed = frozenset(
        (root / f.path).resolve() for f in files if f.status != "D"
    )
    return ReviewScope(root=root, changed_files=changed)
