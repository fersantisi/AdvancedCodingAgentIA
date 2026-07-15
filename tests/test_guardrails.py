"""Unit tests for guardrails loading and validation."""

from __future__ import annotations

import json

import pytest

from coding_agent.config.guardrails import Guardrails, GuardrailViolation


@pytest.fixture
def guardrails(tmp_path):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "secrets").mkdir()
    config = tmp_path / "guardrails.json"
    config.write_text(
        json.dumps(
            {
                "allowed_directories": ["workspace"],
                "blocked_directories": ["secrets"],
                "blocked_files": [".env"],
                "blocked_commands": ["rm -rf", "git push"],
            }
        ),
        encoding="utf-8",
    )
    return Guardrails.load(config, base_dir=tmp_path)


class TestPathRules:
    def test_allowed_path_passes(self, guardrails, tmp_path):
        guardrails.validate("read_file", {"path": str(tmp_path / "workspace" / "a.py")})

    def test_outside_allowed_directories_blocked(self, guardrails, tmp_path):
        with pytest.raises(GuardrailViolation, match="outside the allowed"):
            guardrails.validate("read_file", {"path": str(tmp_path / "other" / "a.py")})

    def test_blocked_directory_wins_over_allowed(self, guardrails, tmp_path):
        with pytest.raises(GuardrailViolation, match="blocked directory"):
            guardrails.validate("write_file", {"path": str(tmp_path / "secrets" / "k.txt")})

    def test_path_escape_with_dotdot_blocked(self, guardrails, tmp_path):
        sneaky = str(tmp_path / "workspace" / ".." / "secrets" / "k.txt")
        with pytest.raises(GuardrailViolation):
            guardrails.validate("read_file", {"path": sneaky})

    def test_blocked_file_by_name_anywhere(self, guardrails, tmp_path):
        with pytest.raises(GuardrailViolation, match="blocked file"):
            guardrails.validate("read_file", {"path": str(tmp_path / "workspace" / ".env")})


class TestCommandRules:
    def test_safe_command_passes(self, guardrails):
        guardrails.validate("run_command", {"command": "pytest -q"})

    def test_blocked_command_substring(self, guardrails):
        with pytest.raises(GuardrailViolation, match="forbidden pattern"):
            guardrails.validate("run_command", {"command": "rm -rf /"})

    def test_blocked_command_is_case_and_space_insensitive(self, guardrails):
        with pytest.raises(GuardrailViolation):
            guardrails.validate("run_command", {"command": "GIT   PUSH origin main"})

    def test_command_rule_only_applies_to_run_command(self, guardrails, tmp_path):
        # 'command' argument on other tools is not a shell command
        guardrails.validate("read_file", {"path": str(tmp_path / "workspace" / "x"), "command": "rm -rf"})


class TestLoading:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(GuardrailViolation, match="not found"):
            Guardrails.load(tmp_path / "missing.json")

    def test_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(GuardrailViolation, match="Invalid JSON"):
            Guardrails.load(bad)

    def test_permissive_allows_everything(self, tmp_path):
        Guardrails.permissive().validate("run_command", {"command": "rm -rf /"})
        Guardrails.permissive().validate("read_file", {"path": str(tmp_path / "anything")})
