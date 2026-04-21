from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


def test_type_target_returns_ok(cli):
    exit_code, envelope = cli(["type", "Target"])
    assert exit_code == 0
    assert envelope["status"] == "ok"
    data = envelope["data"]
    assert data["requested_type"] == "Target"
    assert "type Target" in data["schema_text"]


def test_type_with_dependencies_contains_referenced_types(cli):
    exit_code, envelope = cli(["type", "AssociatedDisease", "--with-dependencies"])
    assert exit_code == 0
    schema_text = envelope["data"]["schema_text"]
    assert "type AssociatedDisease" in schema_text
    assert "type Disease" in schema_text


def test_type_unknown_returns_not_found(cli):
    exit_code, envelope = cli(["type", "DefinitelyNotAGraphQLType12345"])
    assert exit_code == 0
    assert envelope["status"] == "not_found"
    assert envelope["data"]["requested_type"] == "DefinitelyNotAGraphQLType12345"
