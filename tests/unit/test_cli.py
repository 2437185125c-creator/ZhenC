"""CLI tests — run the sync entry points end-to-end on temp repos."""
from __future__ import annotations

from pathlib import Path

from code_review_harness.cli import main


def make_buggy_repo(repo: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    (repo / "app.py").write_text("def f():\n    try:\n        return 1\n    except:\n        pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    (repo / "app.py").write_text("def f():\n    try:\n        return 1\n    except:\n        pass\n\nx = missing\n", encoding="utf-8")


def test_cli_review_static(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    make_buggy_repo(repo)

    code = main(["review", "--repo", str(repo), "--static", "--output-dir", str(tmp_path / "out")])
    captured = capsys.readouterr()

    assert code == 0
    assert "PY-BARE-EXCEPT" in captured.out
    # JSON output file written.
    assert (tmp_path / "out" / "repo-report.json").exists()


def test_cli_review_static_json(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    make_buggy_repo(repo)

    code = main(["review", "--repo", str(repo), "--static", "--json"])
    captured = capsys.readouterr()

    assert code == 0
    import json

    data = json.loads(captured.out)
    assert data["repo_path"] == str(repo.resolve())


def test_cli_review_requires_api_key_without_static(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    code = main(["review", "--repo", str(repo), "--provider", "openai", "--json"])
    captured = capsys.readouterr()
    assert code != 0
    assert "No API key" in captured.err or "No API key" in captured.out


def test_cli_eval(tmp_path, capsys):
    code = main(["eval", "--work-dir", str(tmp_path / "eval")])
    captured = capsys.readouterr()
    assert code == 0
    assert "detection_rate" in captured.out
    assert "fix_rate" in captured.out
