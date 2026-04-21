from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from opentargets_cli import cli as cli_module

GOLDENS_DIR = Path(__file__).parent / "goldens"

STUB_META = {
    "name": "Open Targets GraphQL & REST API Beta",
    "product": "platform",
    "dataPrefix": "stub-prefix",
    "enableDataReleasePrefix": True,
    "downloads": "stubbed-downloads",
    "apiVersion": {"x": "99", "y": "99", "z": "0", "suffix": None},
    "dataVersion": {"year": "9999", "month": "99", "iteration": None},
}

STUB_TIMESTAMP = "2000-01-01T00:00:00Z"


class StubClient:
    """Offline stub client that never touches the network."""

    def __init__(self, endpoint: str, timeout: int, user_agent: str) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch_meta(self) -> dict[str, Any]:
        return dict(STUB_META)

    def fetch_schema(self) -> Any:
        raise AssertionError("Offline tests must not call fetch_schema")

    def execute(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Offline tests must not call execute")


@pytest.fixture
def offline_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the CLI module to use stub transport and a fixed timestamp."""
    monkeypatch.setattr(cli_module, "OpenTargetsClient", StubClient)
    monkeypatch.setattr(cli_module, "utc_now", lambda: STUB_TIMESTAMP)


class _EmptyTTYStdin(io.StringIO):
    """Stand-in for sys.stdin that reports as a TTY so read_query_text skips it."""

    def isatty(self) -> bool:
        return True


def run_cli(argv: list[str]) -> tuple[int, dict[str, Any]]:
    """Run `ot` in-process. Returns (exit_code, parsed_envelope_or_raw_dict)."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    original_stdin = sys.stdin
    sys.stdin = _EmptyTTYStdin()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli_module.main(argv)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 2
    finally:
        sys.stdin = original_stdin
    out = stdout.getvalue().strip()
    err = stderr.getvalue().strip()
    raw = err if exit_code else out
    try:
        envelope = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return exit_code, {"raw_stdout": out, "raw_stderr": err}
    return exit_code, envelope


@pytest.fixture
def cli() -> Any:
    return run_cli
