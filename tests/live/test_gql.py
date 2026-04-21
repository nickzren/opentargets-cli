from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.live


def test_gql_simple_meta_query_returns_ok(cli):
    exit_code, envelope = cli(["gql", "--query", "query { meta { name } }"])
    assert exit_code == 0
    assert envelope["status"] == "ok"
    name = envelope["data"]["graphql_data"]["meta"]["name"]
    assert "Open Targets" in name


def test_gql_with_variables_resolves_target(cli):
    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            "query Q($id: String!) { target(ensemblId: $id) { id approvedSymbol } }",
            "--variables",
            '{"id":"ENSG00000012048"}',
            "--operation-name",
            "Q",
        ]
    )
    assert exit_code == 0
    assert envelope["status"] == "ok"
    target = envelope["data"]["graphql_data"]["target"]
    assert target["id"] == "ENSG00000012048"
    assert target["approvedSymbol"] == "BRCA1"


def test_gql_mutation_is_rejected_against_live_endpoint(cli):
    exit_code, envelope = cli(["gql", "--query", "mutation { __typename }"])
    assert exit_code == 2
    assert envelope["error"]["code"] == "usage"


def test_gql_batch_with_variables_list_returns_summary(cli, tmp_path):
    variables_path = tmp_path / "vars.ndjson"
    variables_path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"id": "ENSG00000012048"},
                {"id": "ENSG00000141510"},
            ]
        )
        + "\n",
        encoding="utf-8",
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
        ]
    )

    assert exit_code == 0
    assert envelope["status"] == "ok"
    assert envelope["meta"]["template"] == "gql.batch"
    assert envelope["data"]["summary"] == {
        "total": 2,
        "successful": 2,
        "partial": 0,
        "failed": 0,
    }
    by_key = {row["key"]: row for row in envelope["data"]["results"]}
    assert by_key["ENSG00000012048"]["graphql_data"]["target"]["approvedSymbol"] == "BRCA1"
    assert by_key["ENSG00000141510"]["graphql_data"]["target"]["approvedSymbol"] == "TP53"
