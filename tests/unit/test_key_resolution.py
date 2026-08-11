"""Tests for API-key resolution priority (--api-key > --env-file > env > project .env > ~/.crh/.env)."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from code_review_harness.cli import _resolve_api_key


def make_args(**kwargs) -> Namespace:
    base = {"api_key": None, "env_file": None}
    base.update(kwargs)
    return Namespace(**base)


def setup_env(tmp_path, monkeypatch, *, project_env: dict | None = None, user_env: dict | None = None):
    """chdir into a fake project dir and point ~/.crh at tmp home."""
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    monkeypatch.chdir(project)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    for name, values in ((".env", project_env), (".crh/.env", user_env)):
        if values is None:
            continue
        path = (home if name.startswith(".crh") else project) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")

    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return project


def test_command_line_api_key_highest(tmp_path, monkeypatch):
    setup_env(
        tmp_path,
        monkeypatch,
        project_env={"API_KEY": "proj"},
        user_env={"API_KEY": "user"},
    )
    key, source = _resolve_api_key(make_args(api_key="cli"))
    assert key == "cli"
    assert "command line" in source


def test_project_env_beats_user_env(tmp_path, monkeypatch):
    setup_env(
        tmp_path,
        monkeypatch,
        project_env={"API_KEY": "proj"},
        user_env={"API_KEY": "user"},
    )
    key, source = _resolve_api_key(make_args())
    assert key == "proj"
    assert "project .env" in source


def test_user_env_used_when_no_project_env(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch, user_env={"API_KEY": "user"})
    key, source = _resolve_api_key(make_args())
    assert key == "user"
    assert "user config" in source


def test_real_environment_variable_beats_env_files(tmp_path, monkeypatch):
    setup_env(
        tmp_path,
        monkeypatch,
        project_env={"API_KEY": "proj"},
        user_env={"API_KEY": "user"},
    )
    monkeypatch.setenv("API_KEY", "envkey")
    key, source = _resolve_api_key(make_args())
    assert key == "envkey"
    assert "environment variable" in source


def test_env_file_overrides(tmp_path, monkeypatch):
    setup_env(
        tmp_path,
        monkeypatch,
        project_env={"API_KEY": "proj"},
        user_env={"API_KEY": "user"},
    )
    explicit = tmp_path / "explicit.env"
    explicit.write_text("API_KEY=explicit\n", encoding="utf-8")
    key, source = _resolve_api_key(make_args(env_file=str(explicit)))
    assert key == "explicit"
    assert "--env-file" in source


def test_missing_env_file_raises(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    try:
        _resolve_api_key(make_args(env_file=str(tmp_path / "nope.env")))
        raise AssertionError("should have raised SystemExit")
    except SystemExit:
        pass


def test_no_key_returns_none(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    key, source = _resolve_api_key(make_args())
    assert key is None
    assert source == ""


def test_openai_env_var_name_also_works(tmp_path, monkeypatch):
    setup_env(
        tmp_path,
        monkeypatch,
        project_env={"OPENAI_API_KEY": "proj"},
    )
    key, source = _resolve_api_key(make_args())
    assert key == "proj"
