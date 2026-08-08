"""Review scope — which files the agent is allowed to modify.

Derived from the git diff: the agent may *read* anywhere in the repo but may
only *write* to files that are part of the change under review.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReviewScope:
    """The set of paths a review run may modify."""

    root: Path
    changed_files: frozenset[Path]

    def allows(self, path: Path) -> bool:
        """Whether ``path`` is a changed file (absolute, normalized)."""
        return path in self.changed_files

    @classmethod
    def unrestricted(cls, root: Path) -> "ReviewScope":
        """Scope that allows everything (used before the diff is computed)."""
        return cls(root=root, changed_files=frozenset())
