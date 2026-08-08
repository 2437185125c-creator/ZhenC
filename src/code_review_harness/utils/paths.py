"""Path-safety helpers shared by tools and governance.

Tools must not be able to reach files outside the reviewed repository: a
review agent should only ever touch what the harness owns.  ``safe_resolve``
enforces that boundary in one place.
"""

from __future__ import annotations

from pathlib import Path


class PathEscapeError(ValueError):
    """Raised when a path resolves outside the allowed root."""


def safe_resolve(cwd: Path, path: str) -> Path:
    """Resolve ``path`` relative to ``cwd`` and require the result to stay inside it."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    resolved = candidate.resolve()
    root = cwd.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathEscapeError(f"path escapes the repository root: {path}") from exc
    return resolved
