"""Allow ``python -m code_review_harness`` to invoke the CLI."""

from __future__ import annotations

from code_review_harness.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
