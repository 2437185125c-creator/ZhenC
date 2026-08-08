"""Python AST static analysis.

The static analyzer is the *deterministic* half of the review: it finds issues
that need no judgment (bare ``except``, mutable default args, dangerous calls,
undefined names) and hands them to the LLM as structured hints.  Findings are
reported as ``INFO``/``LOW`` where the analyzer is heuristic, so a false
positive never masquerades as a high-severity bug.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import replace
from pathlib import Path

from code_review_harness.review.models import Finding, FindingCategory, Severity

_BASE_BUILTINS = set(dir(builtins))


class _DefinedNameVisitor(ast.NodeVisitor):
    """Collect every name bound anywhere in the module."""

    def __init__(self) -> None:
        self.defined: set[str] = set()

    def _add(self, name: str | None) -> None:
        if name:
            self.defined.add(name)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            for name in ast.walk(target):
                if isinstance(name, ast.Name):
                    self._add(name.id)
        self.generic_visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            self._add(node.target.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add(node.name)
        args = node.args
        for arg in (
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
            args.vararg,
            args.kwarg,
        ):
            if arg is not None:
                self._add(arg.arg)
        for default in node.args.defaults + node.args.kw_defaults:
            if default is not None:
                self.visit(default)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._add(alias.asname or alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        for name in ast.walk(node.target):
            if isinstance(name, ast.Name):
                self._add(name.id)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        for name in ast.walk(node.target):
            if isinstance(name, ast.Name):
                self._add(name.id)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if item.optional_vars:
                for name in ast.walk(item.optional_vars):
                    if isinstance(name, ast.Name):
                        self._add(name.id)
        self.generic_visit(node)


class _UseVisitor(ast.NodeVisitor):
    """Collect every loaded name (Name with ctx=Load)."""

    def __init__(self) -> None:
        self.used: set[str] = set()
        self.locations: list[tuple[int, str]] = []

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.used.add(node.id)
            self.locations.append((node.lineno, node.id))


class _ImportTracker(ast.NodeVisitor):
    """Map bound names to their import location for unused-import detection."""

    def __init__(self) -> None:
        self.imports: dict[str, tuple[int, str]] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self.imports[bound] = (node.lineno, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name
            self.imports[bound] = (node.lineno, f"from {node.module} import {alias.name}")
        self.generic_visit(node)


def _find_lines(node: ast.AST) -> int:
    return getattr(node, "lineno", 0) or 0


def _check_bare_except(tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(
                Finding(
                    rule_id="PY-BARE-EXCEPT",
                    category=FindingCategory.BUG,
                    severity=Severity.MEDIUM,
                    file_path="",
                    line=_find_lines(node),
                    message="Bare except clause catches every exception, including KeyboardInterrupt and SystemExit.",
                    suggestion="Use `except Exception as exc:` or catch specific exception types.",
                )
            )
    return findings


def _check_mutable_default_args(tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if default is None:
                    continue
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(
                        Finding(
                            rule_id="PY-MUTABLE-DEFAULT",
                            category=FindingCategory.BUG,
                            severity=Severity.MEDIUM,
                            file_path="",
                            line=_find_lines(node),
                            message=f"Mutable default argument in {node.name} shared across calls.",
                            suggestion="Use `None` and initialize inside the function.",
                        )
                    )
    return findings


def _check_dangerous_calls(tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Direct dangerous builtins: eval/exec/__import__.
        if isinstance(func, ast.Name) and func.id in {"eval", "exec", "__import__"}:
            findings.append(
                Finding(
                    rule_id="PY-DANGEROUS-CALL",
                    category=FindingCategory.SECURITY,
                    severity=Severity.HIGH,
                    file_path="",
                    line=_find_lines(node),
                    message=f"Call to {func.id}() with dynamic code; risk of code injection.",
                    suggestion="Avoid eval/exec; use a safe parser or whitelist validation.",
                )
            )
        # Attribute calls: os.system, os.popen, subprocess with shell=True, pickle.load(s).
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = func.value.id
            attr = func.attr
            if module == "os" and attr in {"system", "popen"}:
                findings.append(
                    Finding(
                        rule_id="PY-DANGEROUS-CALL",
                        category=FindingCategory.SECURITY,
                        severity=Severity.HIGH,
                        file_path="",
                        line=_find_lines(node),
                        message=f"os.{attr}() executes a shell command; risk of command injection.",
                        suggestion="Prefer subprocess with a list of arguments and shell=False.",
                    )
                )
            if module == "subprocess" and attr in {"call", "run", "Popen"}:
                shell_arg = next(
                    (kw.value for kw in node.keywords if kw.arg == "shell"),
                    None,
                )
                if isinstance(shell_arg, ast.Constant) and shell_arg.value is True:
                    findings.append(
                        Finding(
                            rule_id="PY-DANGEROUS-CALL",
                            category=FindingCategory.SECURITY,
                            severity=Severity.HIGH,
                            file_path="",
                            line=_find_lines(node),
                            message=f"subprocess.{attr}() called with shell=True; risk of command injection.",
                            suggestion="Use shell=False and pass arguments as a list.",
                        )
                    )
            if module == "pickle" and attr in {"load", "loads"}:
                findings.append(
                    Finding(
                        rule_id="PY-UNSAFE-PICKLE",
                        category=FindingCategory.SECURITY,
                        severity=Severity.MEDIUM,
                        file_path="",
                        line=_find_lines(node),
                        message="pickle.load(s) can execute arbitrary code on untrusted data.",
                        suggestion="Use a safe format (JSON) or verify data provenance.",
                    )
                )
            if module == "yaml" and attr == "load":
                loader_arg = next((kw.value for kw in node.keywords if kw.arg == "Loader"), None)
                if loader_arg is None:
                    findings.append(
                        Finding(
                            rule_id="PY-UNSAFE-YAML",
                            category=FindingCategory.SECURITY,
                            severity=Severity.MEDIUM,
                            file_path="",
                            line=_find_lines(node),
                            message="yaml.load() without an explicit Loader is unsafe.",
                            suggestion="Use `yaml.safe_load()` instead.",
                        )
                    )
    return findings


def _check_is_literal(tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op, right in zip(node.ops, node.comparators):
                if isinstance(op, ast.Is) and isinstance(right, ast.Constant):
                    findings.append(
                        Finding(
                            rule_id="PY-IS-LITERAL",
                            category=FindingCategory.BUG,
                            severity=Severity.LOW,
                            file_path="",
                            line=_find_lines(node),
                            message="Using `is` to compare against a literal value.",
                            suggestion="Use `==` for value comparison; `is` checks identity.",
                        )
                    )
    return findings


def _check_undefined_names(tree: ast.AST) -> list[Finding]:
    defined = _DefinedNameVisitor()
    defined.visit(tree)
    use = _UseVisitor()
    use.visit(tree)
    findings: list[Finding] = []
    for lineno, name in use.locations:
        if name in defined.defined or name in _BASE_BUILTINS:
            continue
        findings.append(
            Finding(
                rule_id="PY-UNDEFINED-NAME",
                category=FindingCategory.BUG,
                severity=Severity.LOW,
                file_path="",
                line=lineno,
                message=f"Name {name!r} may be undefined in this file.",
                suggestion="Verify the name is defined or imported before use.",
            )
        )
    return findings


def _check_unused_imports(tree: ast.AST) -> list[Finding]:
    tracker = _ImportTracker()
    tracker.visit(tree)
    use = _UseVisitor()
    use.visit(tree)
    findings: list[Finding] = []
    for bound, (lineno, import_text) in tracker.imports.items():
        if bound not in use.used:
            findings.append(
                Finding(
                    rule_id="PY-UNUSED-IMPORT",
                    category=FindingCategory.MAINTAINABILITY,
                    severity=Severity.INFO,
                    file_path="",
                    line=lineno,
                    message=f"Unused import: {import_text}",
                    suggestion="Remove the unused import.",
                )
            )
    return findings


def analyze_source(source: str, file_path: str) -> list[Finding]:
    """Run all AST checks on one source file."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [
            Finding(
                rule_id="PY-SYNTAX",
                category=FindingCategory.BUG,
                severity=Severity.CRITICAL,
                file_path=file_path,
                line=exc.lineno or 0,
                message=f"Syntax error: {exc.msg}",
            )
        ]
    checks = (
        _check_bare_except,
        _check_mutable_default_args,
        _check_dangerous_calls,
        _check_is_literal,
        _check_undefined_names,
        _check_unused_imports,
    )
    findings: list[Finding] = []
    for check in checks:
        findings.extend(check(tree))
    # The analyzer runs per-file; stamp the path on every finding.
    return [replace(finding, file_path=file_path) for finding in findings]


def analyze_file(path: Path) -> list[Finding]:
    """Analyze a file on disk (returns [] for unreadable/binary files)."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return analyze_source(source, str(path))
