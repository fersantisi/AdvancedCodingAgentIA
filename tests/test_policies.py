"""Tests for the agent.config.json policy engine and its harness integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from coding_agent.config.policies import AgentPolicies, PolicyViolation
from coding_agent.models import AssistantTurn, ToolCall
from coding_agent.tools import Tool
from coding_agent.tools.run_command import RunCommandTool
from tests.conftest import FakeIO, make_harness

EXAMPLE_CONFIG = {
    "workspace": ".",
    "permissions": {
        "read": {"deny": [".env", "**/*.pem", "secrets/**"]},
        "write": {"deny": [".github/**", "package-lock.json"]},
    },
    "commands": {
        "deny": ["rm -rf", "git push"],
        "require_approval": ["npm install", "pip install", "git commit"],
    },
}


class ReadProbeTool(Tool):
    """Read-only tool with a path argument, for policy tests."""

    name = "read_probe"
    description = "Pretend to read a path."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    read_only = True

    def execute(self, arguments: dict[str, Any]) -> str:
        return f"read {arguments['path']}"


def write_config(tmp_path: Path, data: dict) -> Path:
    config = tmp_path / "agent.config.json"
    config.write_text(json.dumps(data), encoding="utf-8")
    return config


def load_example(tmp_path: Path) -> AgentPolicies:
    return AgentPolicies.load(write_config(tmp_path, EXAMPLE_CONFIG), base_dir=tmp_path)


class TestLoading:
    def test_loads_the_pdf_example_schema(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        assert policies.workspace == tmp_path.resolve()
        assert ".env" in policies.read_deny
        assert ".github/**" in policies.write_deny
        assert "rm -rf" in policies.command_deny
        assert "pip install" in policies.command_require_approval

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PolicyViolation, match="not found"):
            AgentPolicies.load(tmp_path / "nope.json")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        config = tmp_path / "agent.config.json"
        config.write_text("{broken", encoding="utf-8")
        with pytest.raises(PolicyViolation, match="Invalid JSON"):
            AgentPolicies.load(config)

    def test_wrong_types_raise(self, tmp_path: Path) -> None:
        config = write_config(tmp_path, {"commands": {"deny": "rm -rf"}})
        with pytest.raises(PolicyViolation, match="commands.deny"):
            AgentPolicies.load(config)

    def test_permissive_allows_everything(self) -> None:
        policies = AgentPolicies.permissive()
        policies.validate("read_file", {"path": ".env"}, read_only=True)
        assert not policies.approval_required("run_command", {"command": "pip install x"})


class TestPathRules:
    def test_read_deny_blocks_bare_name_anywhere(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        nested = tmp_path / "sub" / ".env"
        with pytest.raises(PolicyViolation, match=".env"):
            policies.validate("read_file", {"path": str(nested)}, read_only=True)

    def test_read_deny_blocks_double_star_glob(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        for candidate in (tmp_path / "key.pem", tmp_path / "certs" / "deep" / "key.pem"):
            with pytest.raises(PolicyViolation, match="pem"):
                policies.validate("read_file", {"path": str(candidate)}, read_only=True)

    def test_read_deny_blocks_directory_glob(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        with pytest.raises(PolicyViolation, match="secrets"):
            policies.validate(
                "read_file", {"path": str(tmp_path / "secrets" / "token.txt")}, read_only=True
            )

    def test_write_deny_only_applies_to_mutating_tools(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        workflow = tmp_path / ".github" / "workflows" / "ci.yml"
        policies.validate("read_file", {"path": str(workflow)}, read_only=True)
        with pytest.raises(PolicyViolation, match="may not be modified"):
            policies.validate("write_file", {"path": str(workflow)}, read_only=False)

    def test_workspace_escape_is_blocked(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        outside = tmp_path.parent / "outside.txt"
        with pytest.raises(PolicyViolation, match="outside the configured workspace"):
            policies.validate("read_file", {"path": str(outside)}, read_only=True)

    def test_allowed_paths_pass(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        policies.validate("read_file", {"path": str(tmp_path / "src" / "app.php")}, read_only=True)
        policies.validate("write_file", {"path": str(tmp_path / "src" / "app.php")}, read_only=False)


class TestCommandRules:
    def test_denied_command_substring(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        with pytest.raises(PolicyViolation, match="forbidden"):
            policies.validate("run_command", {"command": "git   PUSH origin main"}, read_only=False)

    def test_require_approval_matches_normalized_substring(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        assert policies.approval_required("run_command", {"command": "PIP   install requests"})
        assert not policies.approval_required("run_command", {"command": "pytest -q"})
        assert not policies.approval_required("write_file", {"path": "x"})


class TestHarnessIntegration:
    def test_policy_block_becomes_error_result(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        call = ToolCall(id="1", name="read_probe", arguments={"path": str(tmp_path / ".env")})
        turns = [
            AssistantTurn(text=None, tool_calls=(call,)),
            AssistantTurn(text="adapted"),
        ]
        io = FakeIO()
        harness, _, history = make_harness(turns, io, tools=[ReadProbeTool()], policies=policies)

        assert harness.run_turn("read the env") == "adapted"
        tool_message = history.messages()[3]
        assert tool_message.content.startswith("ERROR: Blocked by policy:")

    def test_require_approval_prompts_even_with_supervision_off(self, tmp_path: Path) -> None:
        policies = load_example(tmp_path)
        call = ToolCall(id="1", name="run_command", arguments={"command": "pip install httpx"})
        turns = [
            AssistantTurn(text=None, tool_calls=(call,)),
            AssistantTurn(text="ok, not installing"),
        ]
        io = FakeIO(confirm_answers=[False])
        harness, _, history = make_harness(
            turns, io, tools=[RunCommandTool()], policies=policies, supervision_enabled=False
        )

        harness.run_turn("install httpx")
        assert io.confirm_questions, "policy-required approval must prompt"
        tool_message = history.messages()[3]
        assert "Denied by the user" in tool_message.content
