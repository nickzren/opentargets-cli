"""Regenerate deterministic golden JSON fixtures under tests/goldens/.

Run with:

    .venv/bin/python -m tests.generate_goldens

These goldens cover commands whose output is driven entirely by the local
command registry (no OT schema drift): `tools`, `describe *`, and
`schema --list-categories`. Network calls are stubbed, so the output is
fully deterministic.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

from opentargets_cli import cli as cli_module

from tests.conftest import STUB_TIMESTAMP, StubClient

GOLDENS_DIR = Path(__file__).parent / "goldens"

GOLDEN_CASES: list[tuple[list[str], str]] = [
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


def _install_offline_stubs() -> None:
    cli_module.OpenTargetsClient = StubClient  # type: ignore[assignment]
    cli_module.utc_now = lambda: STUB_TIMESTAMP  # type: ignore[assignment]


def _run(argv: list[str]) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        exit_code = cli_module.main(argv)
    if exit_code != 0:
        raise SystemExit(f"Command {argv} exited with {exit_code}: {buf.getvalue()}")
    return json.loads(buf.getvalue())


def main() -> int:
    _install_offline_stubs()
    GOLDENS_DIR.mkdir(exist_ok=True)
    for argv, filename in GOLDEN_CASES:
        envelope = _run(list(argv))
        path = GOLDENS_DIR / filename
        path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
