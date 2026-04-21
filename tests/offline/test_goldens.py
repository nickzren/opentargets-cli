from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import GOLDENS_DIR

GOLDEN_CASES = [
    (["tools"], "tools.json"),
    (["describe", "meta"], "describe_meta.json"),
    (["describe", "tools"], "describe_tools.json"),
    (["describe", "doctor"], "describe_doctor.json"),
    (["describe", "install-skills"], "describe_install_skills.json"),
    (["describe", "describe"], "describe_describe.json"),
    (["describe", "resolve"], "describe_resolve.json"),
    (["describe", "schema"], "describe_schema.json"),
    (["describe", "type"], "describe_type.json"),
    (["describe", "gql"], "describe_gql.json"),
    (["schema", "--list-categories"], "schema_list_categories.json"),
]


@pytest.mark.parametrize("argv,golden_name", GOLDEN_CASES, ids=[name for _, name in GOLDEN_CASES])
def test_golden_envelope(argv, golden_name, offline_cli, cli):
    exit_code, envelope = cli(argv)
    golden_path: Path = GOLDENS_DIR / golden_name
    assert golden_path.exists(), f"Missing golden {golden_path}; regenerate with `python -m tests.generate_goldens`."
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert exit_code == 0, envelope
    assert envelope == expected, f"Envelope drift for `ot {' '.join(argv)}`"
