"""Evaluation dataset — git repos with injected, known bugs.

Each :class:`BugCase` builds a throwaway git repository whose *working-tree
change* introduces one planted bug.  The repo commits a correct version plus a
failing test, then overwrites the source with the buggy version — so the bug is
exactly the diff the review agent should find, and the fix is exactly the
correct version (making fix validation meaningful).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BugCase:
    """One eval scenario: a repo change that injects a known bug."""

    name: str
    description: str
    expected_rule: str
    filename: str
    correct: str
    buggy: str
    test: str

    def build(self, root: Path) -> Path:
        """Create a git repo whose working-tree change introduces the bug."""
        repo = root / self.name
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "eval@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Eval"], cwd=repo, check=True)

        (repo / self.filename).write_text(self.correct, encoding="utf-8")
        (repo / f"test_{Path(self.filename).stem}.py").write_text(self.test, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)

        (repo / self.filename).write_text(self.buggy, encoding="utf-8")
        return repo


def default_dataset() -> list[BugCase]:
    """The standard planted-bug suite used by ``crh eval``."""
    return [
        BugCase(
            name="bare_except",
            description="bare except swallows TypeError",
            expected_rule="PY-BARE-EXCEPT",
            filename="calc.py",
            correct=(
                "def safe_divide(a, b):\n"
                "    try:\n"
                "        return a / b\n"
                "    except ZeroDivisionError:\n"
                "        return None\n"
            ),
            buggy=(
                "def safe_divide(a, b):\n"
                "    try:\n"
                "        return a / b\n"
                "    except:\n"
                "        return None\n"
            ),
            test=(
                "import pytest\n"
                "from calc import safe_divide\n"
                "\n"
                "def test_type_error_propagates():\n"
                "    with pytest.raises(TypeError):\n"
                "        safe_divide('a', 1)\n"
            ),
        ),
        BugCase(
            name="mutable_default",
            description="mutable default argument shared across calls",
            expected_rule="PY-MUTABLE-DEFAULT",
            filename="utils.py",
            correct=(
                "def append_unique(item, items=None):\n"
                "    if items is None:\n"
                "        items = []\n"
                "    if item not in items:\n"
                "        items.append(item)\n"
                "    return items\n"
            ),
            buggy=(
                "def append_unique(item, items=[]):\n"
                "    if item not in items:\n"
                "        items.append(item)\n"
                "    return items\n"
            ),
            test=(
                "from utils import append_unique\n"
                "\n"
                "def test_fresh_list_per_call():\n"
                "    first = append_unique(1)\n"
                "    second = append_unique(2)\n"
                "    assert second == [2]\n"
            ),
        ),
        BugCase(
            name="is_literal",
            description="identity comparison against a literal",
            expected_rule="PY-IS-LITERAL",
            filename="flags.py",
            correct=(
                "def is_enabled(status):\n"
                "    return bool(status)\n"
            ),
            buggy=(
                "def is_enabled(status):\n"
                "    return status is True\n"
            ),
            test=(
                "from flags import is_enabled\n"
                "\n"
                "def test_truthy_value_enabled():\n"
                "    assert is_enabled(1) is True\n"
            ),
        ),
        BugCase(
            name="undefined_name",
            description="reference to an undefined name",
            expected_rule="PY-UNDEFINED-NAME",
            filename="greet.py",
            correct=(
                "def greeting():\n"
                "    name = 'world'\n"
                "    return f'Hello, {name}'\n"
            ),
            buggy=(
                "def greeting():\n"
                "    return f'Hello, {name}'\n"
            ),
            test=(
                "from greet import greeting\n"
                "\n"
                "def test_greeting():\n"
                "    assert greeting() == 'Hello, world'\n"
            ),
        ),
        BugCase(
            name="eval_call",
            description="dynamic code execution via eval()",
            expected_rule="PY-DANGEROUS-CALL",
            filename="config.py",
            correct=(
                "import json\n"
                "\n"
                "def parse_config(text):\n"
                "    return json.loads(text)\n"
            ),
            buggy=(
                "def parse_config(text):\n"
                "    return eval(text)\n"
            ),
            test=(
                "from config import parse_config\n"
                "\n"
                "def test_parse_json():\n"
                "    assert parse_config('{\"a\": 1}')['a'] == 1\n"
            ),
        ),
        BugCase(
            name="syntax_error",
            description="file does not even parse",
            expected_rule="PY-SYNTAX",
            filename="parse_me.py",
            correct=(
                "def total(values):\n"
                "    return sum(values)\n"
            ),
            buggy=(
                "def total(values:\n"
                "    return sum(values)\n"
            ),
            test=(
                "from parse_me import total\n"
                "\n"
                "def test_total():\n"
                "    assert total([1, 2, 3]) == 6\n"
            ),
        ),
    ]
