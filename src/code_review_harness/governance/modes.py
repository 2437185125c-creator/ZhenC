"""Permission mode definitions."""

from __future__ import annotations

from enum import Enum


class PermissionMode(str, Enum):
    """Supported permission modes.

    - ``DEFAULT``:  read-only tools run freely; mutating tools ask the user.
    - ``PLAN``:     no mutating tools at all (review-only).
    - ``FULL_AUTO``: everything runs automatically (use with care / in CI).
    """

    DEFAULT = "default"
    PLAN = "plan"
    FULL_AUTO = "full_auto"
