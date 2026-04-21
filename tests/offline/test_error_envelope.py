from __future__ import annotations


def test_error_envelope_has_required_shape(offline_cli, cli):
    exit_code, envelope = cli(["resolve", "foo", "--limit", "0"])
    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["meta"]["tool"] == "ot"
    assert "endpoint" in envelope["meta"]
    assert "queried_at_utc" in envelope["meta"]
    assert "template" in envelope["meta"]
    assert envelope["request"]["command"] == "resolve"
    assert envelope["error"]["code"] == "usage"
    assert envelope["error"]["message"]
    assert isinstance(envelope["error"]["details"], dict)
    assert envelope["warnings"] == []


def test_timeout_validation_returns_usage_error(offline_cli, cli):
    exit_code, envelope = cli(["--timeout", "0", "meta"])
    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"
    assert envelope["request"]["args"] == {"no_downloads": False}


def test_error_envelope_preserves_normalized_command_args(offline_cli, cli):
    exit_code, envelope = cli(["resolve", "BRCA1", "--entity", "target", "--limit", "0"])
    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["request"]["args"] == {
        "term": "BRCA1",
        "entity": "target",
        "limit": 0,
        "search_fallback": True,
    }


def test_schema_conflicting_flags_returns_usage_error(offline_cli, cli):
    exit_code, envelope = cli(["schema", "--full", "--category", "meta"])
    assert exit_code == 2
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "usage"
