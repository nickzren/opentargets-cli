from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "query",
    [
        "mutation DoThing { __typename }",
        "subscription Watch { __typename }",
    ],
)
def test_mutation_and_subscription_are_rejected(query, offline_cli, cli):
    exit_code, envelope = cli(["gql", "--query", query])
    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"
    assert "read-only" in envelope["error"]["message"].lower()


def test_unparseable_graphql_returns_usage_error(offline_cli, cli):
    exit_code, envelope = cli(["gql", "--query", "this is not graphql"])
    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"


def test_missing_query_source_returns_usage_error(offline_cli, cli):
    exit_code, envelope = cli(["gql"])
    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"
