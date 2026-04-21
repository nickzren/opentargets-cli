from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


def test_resolve_brca1_as_target_returns_ensg(cli):
    exit_code, envelope = cli(["resolve", "BRCA1", "--entity", "target", "--limit", "5"])
    assert exit_code == 0
    assert envelope["status"] in {"ok", "ambiguous"}
    candidates = envelope["data"]["candidates"]
    assert candidates, "expected at least one candidate for BRCA1"
    ids = [row["id"] for row in candidates]
    assert "ENSG00000012048" in ids, f"BRCA1 canonical ID missing from candidates: {ids}"
    top = candidates[0]
    assert top["entity"] == "target"


def test_resolve_known_ensembl_id_uses_direct_id(cli):
    exit_code, envelope = cli(["resolve", "ENSG00000012048", "--entity", "target"])
    assert exit_code == 0
    assert envelope["status"] == "ok"
    assert envelope["data"]["resolution_method"] == "direct-id"
    top = envelope["data"]["candidates"][0]
    assert top["id"] == "ENSG00000012048"
    assert top["score"] == 1.0


def test_resolve_unknown_term_returns_not_found(cli):
    exit_code, envelope = cli(
        ["resolve", "zzzqxynotarealthing12345", "--entity", "target", "--limit", "5"]
    )
    assert exit_code == 0
    assert envelope["status"] == "not_found"
    assert envelope["data"]["candidates"] == []


def test_resolve_records_entity_filter_in_request(cli):
    _, envelope = cli(["resolve", "BRCA1", "--entity", "target"])
    assert envelope["request"]["args"]["entity"] == "target"
    assert envelope["request"]["resolved"]["entity_filter"] == "target"
