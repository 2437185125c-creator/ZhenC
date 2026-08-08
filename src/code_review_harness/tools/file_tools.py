"""Read-only file tools: read_file and grep.

Both tools resolve paths against the repository root and refuse to escape it.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from code_review_harness.tools.base import BaseTool, ToolExecutionContext, ToolOutcome
from code_review_harness.utils.paths import safe_resolve

# Guard against accidentally loading a huge file into the conversation.
MAX_READ_CHARS = 200_000


class ReadFileInput(BaseModel):
    path: str = Field(description="Path to the file, relative to the repo root.")
    offset: int = Field(default=0, ge=0, description="Line offset (0-based) to start from.")
    limit: int = Field(default=200, ge=1, le=2000, description="Number of lines to read.")


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a UTF-8 text file and return the requested line range with line numbers."
    read_only = True

    input_model = ReadFileInput

    async def execute(self, arguments: ReadFileInput, context: ToolExecutionContext) -> ToolOutcome:
        try:
            resolved = safe_resolve(context.cwd, arguments.path)
            raw = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolOutcome(output=f"Could not read {arguments.path}: {exc}", is_error=True)

        lines = raw.splitlines()
        start = arguments.offset
        end = min(len(lines), start + arguments.limit)
        if start >= len(lines):
            return ToolOutcome(
                output=f"File has {len(lines)} lines; offset {start} is out of range.",
                is_error=True,
            )

        block = "\n".join(f"{i + 1:6d}\t{line}" for i, line in enumerate(lines[start:end], start=start))
        truncated = len(raw) > MAX_READ_CHARS
        note = f"\n# {resolved.relative_to(context.cwd)} lines {start + 1}-{end} of {len(lines)}"
        if truncated:
            note += "\n# (file truncated)"
        return ToolOutcome(output=block + note)


class WriteFileInput(BaseModel):
    path: str = Field(description="Path to the file, relative to the repo root.")
    content: str = Field(description="Full new file content.")


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Replace a file's full content. Mutating — requires approval in default mode."

    input_model = WriteFileInput

    async def execute(self, arguments: WriteFileInput, context: ToolExecutionContext) -> ToolOutcome:
        try:
            resolved = safe_resolve(context.cwd, arguments.path)
        except ValueError as exc:
            return ToolOutcome(output=str(exc), is_error=True)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        try:
            resolved.write_text(arguments.content, encoding="utf-8")
        except OSError as exc:
            return ToolOutcome(output=f"Could not write {arguments.path}: {exc}", is_error=True)
        return ToolOutcome(output=f"Wrote {resolved.relative_to(context.cwd)} ({len(arguments.content)} chars)")


class GrepInput(BaseModel):
    pattern: str = Field(description="Regular expression to search for.")
    root: str = Field(default=".", description="Directory to search under, relative to the repo root.")
    glob: str | None = Field(default="*.py", description="Only search files matching this glob (e.g. '*.py').")
    max_matches: int = Field(default=50, ge=1, le=500, description="Cap on the number of matches returned.")


class GrepTool(BaseTool):
    name = "grep"
    description = "Search source files under a directory for a regex and report file:line:match hits."
    read_only = True

    input_model = GrepInput

    async def execute(self, arguments: GrepInput, context: ToolExecutionContext) -> ToolOutcome:
        try:
            root = safe_resolve(context.cwd, arguments.root)
        except ValueError as exc:
            return ToolOutcome(output=str(exc), is_error=True)
        if not root.is_dir():
            return ToolOutcome(output=f"{arguments.root} is not a directory", is_error=True)

        try:
            regex = re.compile(arguments.pattern)
        except re.error as exc:
            return ToolOutcome(output=f"Invalid regex {arguments.pattern!r}: {exc}", is_error=True)

        hits: list[str] = []
        for path in sorted(root.rglob(arguments.glob or "*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    relative = path.relative_to(context.cwd)
                    hits.append(f"{relative}:{lineno}: {line.strip()}")
                    if len(hits) >= arguments.max_matches:
                        break
            if len(hits) >= arguments.max_matches:
                break

        if not hits:
            return ToolOutcome(output=f"No matches for {arguments.pattern!r} under {arguments.root}.")
        body = "\n".join(hits)
        note = f"\n# {len(hits)} match(es)"
        return ToolOutcome(output=body + note)
