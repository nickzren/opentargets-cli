from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


def test_meta_returns_release_provenance(cli):
    exit_code, envelope = cli(["meta"])
    assert exit_code == 0
    assert envelope["status"] == "ok"
    data = envelope["data"]
    for key in (
        "name",
        "product",
        "data_prefix",
        "api_version",
        "api_version_parts",
        "data_version",
        "data_version_parts",
        "downloads",
    ):
        assert key in data, f"missing {key!r} in meta data"
    assert envelope["request"]["args"] == {"no_downloads": False}


def test_meta_no_downloads_omits_downloads(cli):
    exit_code, envelope = cli(["meta", "--no-downloads"])
    assert exit_code == 0
    assert envelope["status"] == "ok"
    assert "downloads" not in envelope["data"]
    assert envelope["request"]["args"] == {"no_downloads": True}


def test_meta_metadata_block_is_populated(cli):
    _, envelope = cli(["meta"])
    meta = envelope["meta"]
    assert meta["tool"] == "ot"
    assert meta["template"] == "meta"
    assert meta["api_version"]
    assert meta["data_version"]
