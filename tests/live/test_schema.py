from __future__ import annotations

import pytest

from opentargets_cli.config import CATEGORY_SPECS

pytestmark = pytest.mark.live


def test_schema_category_meta_includes_meta_type(cli):
    exit_code, envelope = cli(["schema", "--category", "meta", "--schema-format", "sdl"])
    assert exit_code == 0
    assert envelope["status"] == "ok"
    data = envelope["data"]
    assert data["requested_categories"] == ["meta"]
    assert data["schema_format"] == "sdl"
    assert "type Meta" in data["schema_text"]


def test_schema_category_targets_includes_target_type(cli):
    _, envelope = cli(["schema", "--category", "targets"])
    assert "type Target" in envelope["data"]["schema_text"]


def test_schema_category_json_format_returns_structured_payload(cli):
    exit_code, envelope = cli(["schema", "--category", "meta", "--schema-format", "json"])
    assert exit_code == 0
    data = envelope["data"]
    assert data["schema_format"] == "json"
    schema_json = data["schema_json"]
    assert isinstance(schema_json, dict)
    type_names = {entry["name"] for entry in schema_json.get("types", [])}
    assert "Meta" in type_names


def test_schema_list_categories_matches_registry(cli):
    _, envelope = cli(["schema", "--list-categories"])
    names = [row["name"] for row in envelope["data"]["categories"]]
    assert set(names) == set(CATEGORY_SPECS.keys())
