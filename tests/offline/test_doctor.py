from __future__ import annotations

from pathlib import Path

from opentargets_cli import __version__
from opentargets_cli import cli as cli_module


def write_skill(path: Path, version: str = __version__) -> None:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: opentargets-cli\nversion: {version}\n---\n# Skill\n",
        encoding="utf-8",
    )


def make_commands_on_path(tmp_path: Path, monkeypatch, names: tuple[str, ...] = ("ot",)) -> dict[str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    commands = {}
    for name in names:
        command = bin_dir / name
        command.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        commands[name] = command
    monkeypatch.setenv("PATH", str(bin_dir))
    return commands


def test_doctor_ok_with_both_skills_installed(tmp_path, monkeypatch, offline_cli, cli):
    commands = make_commands_on_path(tmp_path, monkeypatch, ("ot", "claude", "codex"))
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    write_skill(home / ".claude" / "skills" / "opentargets-cli")
    write_skill(codex_home / "skills" / "opentargets-cli")

    exit_code, envelope = cli(["doctor"])

    assert exit_code == 0
    assert envelope["status"] == "ok"
    assert envelope["meta"]["template"] == "doctor"
    assert envelope["request"]["command"] == "doctor"
    assert envelope["data"]["cli"] == {
        "version": __version__,
        "on_path": True,
        "path": str(commands["ot"]),
        "python": envelope["data"]["cli"]["python"],
    }
    assert envelope["data"]["agents"]["claude"] == {
        "detected": True,
        "command": str(commands["claude"]),
    }
    assert envelope["data"]["agents"]["codex"] == {
        "detected": True,
        "command": str(commands["codex"]),
    }
    assert envelope["data"]["api"]["reachable"] is True
    assert envelope["data"]["claude_skill"]["version_matches"] is True
    assert envelope["data"]["codex_skill"]["version_matches"] is True
    assert envelope["warnings"] == []


def test_doctor_warns_when_one_skill_is_missing(tmp_path, monkeypatch, offline_cli, cli):
    make_commands_on_path(tmp_path, monkeypatch, ("ot", "codex"))
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    write_skill(home / ".claude" / "skills" / "opentargets-cli")

    exit_code, envelope = cli(["doctor"])

    assert exit_code == 0
    assert envelope["status"] == "ok"
    assert envelope["data"]["claude_skill"]["installed"] is True
    assert envelope["data"]["codex_skill"]["installed"] is False
    assert envelope["data"]["codex_skill"]["version_matches"] is None
    assert envelope["data"]["agents"]["claude"]["detected"] is False
    assert envelope["data"]["agents"]["codex"]["detected"] is True
    assert envelope["warnings"] == ["codex_skill not installed; run ot install-skills to enable chat-anywhere in Codex"]


def test_doctor_fails_on_skill_version_mismatch(tmp_path, monkeypatch, offline_cli, cli):
    make_commands_on_path(tmp_path, monkeypatch)
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    write_skill(home / ".claude" / "skills" / "opentargets-cli", version="0.0.0")
    write_skill(codex_home / "skills" / "opentargets-cli")

    exit_code, envelope = cli(["doctor"])

    assert exit_code == 1
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "doctor_failed"
    assert "claude_skill version does not match CLI version" in envelope["error"]["details"]["failures"]


def test_doctor_fails_when_ot_is_not_on_path(tmp_path, monkeypatch, offline_cli, cli):
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setattr(
        cli_module,
        "repo_local_check",
        lambda cwd: {"cwd": str(cwd), "agents_md": False, "claude_md": False, "available": False},
    )
    write_skill(home / ".claude" / "skills" / "opentargets-cli")
    write_skill(codex_home / "skills" / "opentargets-cli")

    exit_code, envelope = cli(["doctor"])

    assert exit_code == 1
    assert envelope["status"] == "error"
    assert "ot is not on PATH" in envelope["error"]["details"]["failures"]


def test_doctor_warns_when_repo_local_without_ot_on_path(tmp_path, monkeypatch, offline_cli, cli):
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setattr(
        cli_module,
        "repo_local_check",
        lambda cwd: {"cwd": str(cwd), "agents_md": True, "claude_md": True, "available": True},
    )

    exit_code, envelope = cli(["doctor"])

    assert exit_code == 0
    assert envelope["status"] == "ok"
    assert "ot is not on PATH; repo-local agents must use .venv/bin/ot or run scripts/install.sh" in envelope["warnings"]
    assert "claude_skill not installed; chat-anywhere unavailable in Claude Code" not in envelope["warnings"]
    assert "codex_skill not installed; chat-anywhere unavailable in Codex" not in envelope["warnings"]
