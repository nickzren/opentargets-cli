from __future__ import annotations

from pathlib import Path

from opentargets_cli import __version__


def fake_path(tmp_path: Path, monkeypatch, names: tuple[str, ...]) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in names:
        command = bin_dir / name
        command.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))


def test_install_skills_all_installs_both_and_backs_up_existing(tmp_path, monkeypatch, offline_cli, cli):
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    fake_path(tmp_path, monkeypatch, ())

    existing = home / ".claude" / "skills" / "opentargets-cli"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("user-edited skill\n", encoding="utf-8")

    exit_code, envelope = cli(["install-skills", "--agent", "all"])

    assert exit_code == 0
    assert envelope["status"] == "ok"
    assert envelope["meta"]["template"] == "install-skills"
    assert envelope["request"]["args"] == {"agent": "all"}
    installed = {row["agent"]: row for row in envelope["data"]["installed"]}
    assert set(installed) == {"claude", "codex"}
    assert installed["claude"]["version"] == __version__
    assert installed["codex"]["version"] == __version__
    assert (existing / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: opentargets-cli")
    backup_path = Path(installed["claude"]["backup_path"])
    assert backup_path.parent == home / ".claude" / "skill-backups"
    assert (backup_path / "SKILL.md").read_text(encoding="utf-8") == "user-edited skill\n"
    assert [p.name for p in (home / ".claude" / "skills").iterdir()] == ["opentargets-cli"]
    assert (codex_home / "skills" / "opentargets-cli" / "SKILL.md").is_file()


def test_install_skills_auto_uses_detected_agent_only(tmp_path, monkeypatch, offline_cli, cli):
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    fake_path(tmp_path, monkeypatch, ("codex",))

    exit_code, envelope = cli(["install-skills"])

    assert exit_code == 0
    assert envelope["status"] == "ok"
    assert envelope["request"]["args"] == {"agent": "auto"}
    assert envelope["request"]["resolved"]["detected_agents"] == {"claude": False, "codex": True}
    assert envelope["request"]["resolved"]["selected_agents"] == ["codex"]
    assert envelope["warnings"] == []
    assert not (home / ".claude" / "skills" / "opentargets-cli").exists()
    assert (codex_home / "skills" / "opentargets-cli" / "SKILL.md").is_file()


def test_install_skills_auto_installs_both_when_no_agent_detected(tmp_path, monkeypatch, offline_cli, cli):
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    fake_path(tmp_path, monkeypatch, ())

    exit_code, envelope = cli(["install-skills"])

    assert exit_code == 0
    assert envelope["status"] == "ok"
    assert envelope["request"]["resolved"]["selected_agents"] == ["claude", "codex"]
    assert envelope["warnings"] == [
        "No Claude Code or Codex command detected; installed both skill targets for future use."
    ]
    assert (home / ".claude" / "skills" / "opentargets-cli" / "SKILL.md").is_file()
    assert (codex_home / "skills" / "opentargets-cli" / "SKILL.md").is_file()
