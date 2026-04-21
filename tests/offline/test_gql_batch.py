from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opentargets_cli import cli as cli_module
from opentargets_cli.graphql_api import CLIError
from tests.conftest import STUB_META


class BatchStubClient:
    def __init__(self, endpoint: str, timeout: int, user_agent: str) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch_meta(self) -> dict[str, Any]:
        return dict(STUB_META)

    def fetch_schema(self) -> Any:
        raise AssertionError("Batch tests must not call fetch_schema")

    def execute(self, query: str, *, variables: dict[str, Any] | None = None, operation_name: str | None = None) -> dict[str, Any]:
        assert variables is not None
        target_id = variables["id"]
        if target_id == "partial":
            return {
                "data": {"target": None},
                "errors": [{"message": "field failed"}],
            }
        if target_id == "error":
            return {"errors": [{"message": "bad id"}]}
        return {"data": {"target": {"id": target_id, "approvedSymbol": target_id.upper()}}}


class TransportFailClient(BatchStubClient):
    calls = 0

    def execute(self, query: str, *, variables: dict[str, Any] | None = None, operation_name: str | None = None) -> dict[str, Any]:
        self.__class__.calls += 1
        raise CLIError("network", "Open Targets request failed.", details={"reason": "stub outage"}, exit_code=3)


def write_ndjson(path: Path, rows: list[dict[str, Any] | str]) -> None:
    lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_gql_batch_returns_per_row_statuses(tmp_path, monkeypatch, offline_cli, cli):
    monkeypatch.setattr(cli_module, "OpenTargetsClient", BatchStubClient)
    variables_path = tmp_path / "vars.ndjson"
    write_ndjson(
        variables_path,
        [
            {"id": "brca1"},
            {"id": "partial"},
            {"wrong": "missing-key"},
            {"id": "error"},
        ],
    )

    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            "query Q($id: String!) { target(ensemblId: $id) { id approvedSymbol } }",
            "--variables-list",
            str(variables_path),
            "--key-field",
            "id",
            "--emit-query",
        ]
    )

    assert exit_code == 0
    assert envelope["status"] == "partial"
    assert envelope["meta"]["template"] == "gql.batch"
    assert envelope["request"]["resolved"]["batch"] is True
    assert "rendered_query" in envelope["request"]["resolved"]
    assert envelope["data"]["summary"] == {
        "total": 4,
        "successful": 1,
        "partial": 1,
        "failed": 2,
    }
    rows = envelope["data"]["results"]
    assert rows[0]["status"] == "ok"
    assert rows[0]["key"] == "brca1"
    assert rows[1]["status"] == "partial"
    assert rows[1]["warnings"] == [{"message": "field failed"}]
    assert rows[2]["status"] == "error"
    assert rows[2]["error"]["code"] == "usage"
    assert rows[2]["error"]["details"] == {"key_field": "id"}
    assert rows[3]["status"] == "error"
    assert rows[3]["error"]["code"] == "graphql"


def test_gql_batch_transport_error_fails_fast_at_top_level(tmp_path, monkeypatch, offline_cli, cli):
    TransportFailClient.calls = 0
    monkeypatch.setattr(cli_module, "OpenTargetsClient", TransportFailClient)
    variables_path = tmp_path / "vars.ndjson"
    write_ndjson(variables_path, [{"id": "one"}, {"id": "two"}])

    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            "query Q($id: String!) { target(ensemblId: $id) { id } }",
            "--variables-list",
            str(variables_path),
            "--key-field",
            "id",
        ]
    )

    assert exit_code == 3
    assert TransportFailClient.calls == 1
    assert envelope["status"] == "error"
    assert envelope["meta"]["template"] == "gql.batch"
    assert envelope["request"]["args"]["variables_source"] == "list"
    assert envelope["request"]["args"]["variables_list"] == str(variables_path)
    assert envelope["error"]["code"] == "network"
    assert envelope["error"]["details"] == {"reason": "stub outage"}


def test_gql_batch_invalid_ndjson_halts_before_execution(tmp_path, monkeypatch, offline_cli, cli):
    monkeypatch.setattr(cli_module, "OpenTargetsClient", BatchStubClient)
    variables_path = tmp_path / "vars.ndjson"
    write_ndjson(variables_path, [{"id": "brca1"}, "{not-json"])

    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            "query Q($id: String!) { target(ensemblId: $id) { id } }",
            "--variables-list",
            str(variables_path),
            "--key-field",
            "id",
        ]
    )

    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"
    assert envelope["error"]["details"]["line"] == 2


def test_gql_batch_requires_key_field(tmp_path, monkeypatch, offline_cli, cli):
    monkeypatch.setattr(cli_module, "OpenTargetsClient", BatchStubClient)
    variables_path = tmp_path / "vars.ndjson"
    write_ndjson(variables_path, [{"id": "brca1"}])

    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            "query Q($id: String!) { target(ensemblId: $id) { id } }",
            "--variables-list",
            str(variables_path),
        ]
    )

    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"
    assert "--key-field" in envelope["error"]["message"]


def test_gql_batch_respects_max_items(tmp_path, monkeypatch, offline_cli, cli):
    monkeypatch.setattr(cli_module, "OpenTargetsClient", BatchStubClient)
    variables_path = tmp_path / "vars.ndjson"
    write_ndjson(variables_path, [{"id": "one"}, {"id": "two"}])

    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            "query Q($id: String!) { target(ensemblId: $id) { id } }",
            "--variables-list",
            str(variables_path),
            "--key-field",
            "id",
            "--max-items",
            "1",
        ]
    )

    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"
    assert envelope["error"]["details"] == {"max_items": 1}


def test_gql_batch_all_rows_failed_has_top_level_error(tmp_path, monkeypatch, offline_cli, cli):
    monkeypatch.setattr(cli_module, "OpenTargetsClient", BatchStubClient)
    variables_path = tmp_path / "vars.ndjson"
    write_ndjson(variables_path, [{"id": "error"}])

    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            "query Q($id: String!) { target(ensemblId: $id) { id } }",
            "--variables-list",
            str(variables_path),
            "--key-field",
            "id",
        ]
    )

    assert exit_code == 5
    assert envelope["status"] == "error"
    assert envelope["error"] == {
        "code": "batch_failed",
        "message": "All batch rows failed.",
        "details": {
            "summary": {
                "total": 1,
                "successful": 0,
                "partial": 0,
                "failed": 1,
            }
        },
    }
    assert envelope["data"]["results"][0]["error"]["code"] == "graphql"
