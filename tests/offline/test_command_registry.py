from __future__ import annotations

from typing import Any

from opentargets_cli import cli as cli_module
from opentargets_cli.graphql_api import CLIError
from opentargets_cli.specs import COMMAND_SPECS, describe_payload, tools_payload


class UnreachableClient:
    def __init__(self, endpoint: str, timeout: int, user_agent: str) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch_meta(self) -> dict[str, Any]:
        raise CLIError("network", "stub network failure", exit_code=3)

    def fetch_schema(self) -> Any:
        raise CLIError("network", "stub network failure", exit_code=3)

    def execute(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise CLIError("network", "stub network failure", exit_code=3)


def test_tools_lists_every_registered_command():
    listed = {entry["name"] for entry in tools_payload()["commands"]}
    assert listed == set(COMMAND_SPECS.keys())


def test_every_tool_has_resolvable_describe():
    for entry in tools_payload()["commands"]:
        name = entry["name"]
        payload = describe_payload(name)
        assert payload is not None, f"describe_payload({name!r}) returned None"
        assert payload["command"] == name
        assert entry["describe_command"] == f"ot describe {name}"


def test_describe_payload_none_for_unknown_command():
    assert describe_payload("definitely-not-a-command") is None


def test_status_values_match_between_tools_and_describe():
    for entry in tools_payload()["commands"]:
        name = entry["name"]
        payload = describe_payload(name)
        assert payload is not None
        assert entry["status_values"] == payload["status_values"], f"status drift for {name}"


def test_local_discovery_commands_work_without_live_api(monkeypatch, cli):
    monkeypatch.setattr(cli_module, "OpenTargetsClient", UnreachableClient)

    for argv in (["tools"], ["describe", "gql"], ["schema"], ["schema", "--list-categories"]):
        exit_code, envelope = cli(argv)
        assert exit_code == 0, envelope
        assert envelope["status"] == "ok"
        assert envelope["request"]["command"] == argv[0]
        assert "api_version" not in envelope["meta"]
        assert "data_version" not in envelope["meta"]


def test_schema_rejects_unknown_category_without_live_api(monkeypatch, cli):
    monkeypatch.setattr(cli_module, "OpenTargetsClient", UnreachableClient)

    exit_code, envelope = cli(["schema", "--category", "not_a_category"])

    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"
    assert "available_categories" in envelope["error"]["details"]
