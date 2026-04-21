from __future__ import annotations


def test_missing_subcommand_exits_nonzero(offline_cli, cli):
    exit_code, _ = cli([])
    assert exit_code == 2


def test_describe_requires_command_name(offline_cli, cli):
    exit_code, _ = cli(["describe"])
    assert exit_code == 2


def test_resolve_requires_term(offline_cli, cli):
    exit_code, _ = cli(["resolve"])
    assert exit_code == 2


def test_resolve_rejects_unknown_entity(offline_cli, cli):
    exit_code, _ = cli(["resolve", "foo", "--entity", "galaxy"])
    assert exit_code == 2


def test_type_requires_graphql_type(offline_cli, cli):
    exit_code, _ = cli(["type"])
    assert exit_code == 2


def test_gql_rejects_conflicting_variable_sources(offline_cli, cli):
    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            "query { __typename }",
            "--variables",
            "{}",
            "--variables-file",
            "nope.json",
        ]
    )
    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"
