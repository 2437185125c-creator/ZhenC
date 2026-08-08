"""Unit tests for the AST static analyzer."""
from __future__ import annotations

from code_review_harness.review.static_analyzer import analyze_source
from code_review_harness.review.models import FindingCategory, Severity


def rule_ids(source: str) -> set[str]:
    return {f.rule_id for f in analyze_source(source, "app.py")}


def test_bare_except():
    ids = rule_ids("try:\n    pass\nexcept:\n    pass\n")
    assert "PY-BARE-EXCEPT" in ids


def test_typed_except_not_flagged():
    ids = rule_ids("try:\n    pass\nexcept ValueError:\n    pass\n")
    assert "PY-BARE-EXCEPT" not in ids


def test_mutable_default_arg():
    ids = rule_ids("def f(x=[]):\n    return x\n")
    assert "PY-MUTABLE-DEFAULT" in ids


def test_immutable_default_not_flagged():
    ids = rule_ids("def f(x=None):\n    return x\n")
    assert "PY-MUTABLE-DEFAULT" not in ids


def test_eval_call_flagged_security():
    findings = analyze_source("value = eval(user_input)\n", "app.py")
    flagged = [f for f in findings if f.rule_id == "PY-DANGEROUS-CALL"]
    assert len(flagged) == 1
    assert flagged[0].severity == Severity.HIGH
    assert flagged[0].category == FindingCategory.SECURITY


def test_subprocess_shell_true_flagged():
    ids = rule_ids("import subprocess\nsubprocess.run('ls', shell=True)\n")
    assert "PY-DANGEROUS-CALL" in ids


def test_subprocess_shell_false_not_flagged():
    ids = rule_ids("import subprocess\nsubprocess.run(['ls'], shell=False)\n")
    assert "PY-DANGEROUS-CALL" not in ids


def test_undefined_name():
    findings = analyze_source("print(missing_variable)\n", "app.py")
    flagged = [f for f in findings if f.rule_id == "PY-UNDEFINED-NAME" and "missing_variable" in f.message]
    assert len(flagged) == 1


def test_defined_name_not_flagged():
    ids = rule_ids("x = 1\nprint(x)\n")
    assert "PY-UNDEFINED-NAME" not in ids


def test_unused_import():
    findings = analyze_source("import os\nx = 1\n", "app.py")
    flagged = [f for f in findings if f.rule_id == "PY-UNUSED-IMPORT"]
    assert len(flagged) == 1
    assert flagged[0].severity == Severity.INFO


def test_used_import_not_flagged():
    ids = rule_ids("import os\nprint(os.getcwd())\n")
    assert "PY-UNUSED-IMPORT" not in ids


def test_is_literal_comparison():
    findings = analyze_source("if x is True:\n    pass\n", "app.py")
    flagged = [f for f in findings if f.rule_id == "PY-IS-LITERAL"]
    assert len(flagged) == 1


def test_syntax_error_produces_critical_finding():
    findings = analyze_source("def broken(:\n", "app.py")
    assert any(f.rule_id == "PY-SYNTAX" and f.severity == Severity.CRITICAL for f in findings)


def test_file_path_stamped():
    findings = analyze_source("except:\n    pass\n", "src/x.py")
    assert all(f.file_path == "src/x.py" for f in findings)
