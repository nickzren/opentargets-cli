from __future__ import annotations

import io
import urllib.error

import pytest

from opentargets_cli.graphql_api import CLIError, OpenTargetsClient


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _http_error(status_code: int, body: bytes, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.test/graphql",
        code=status_code,
        msg="HTTP error",
        hdrs=headers or {},
        fp=io.BytesIO(body),
    )


def test_retryable_http_json_body_retries_before_returning(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    sleeps = []

    def fake_urlopen(request: object, timeout: int) -> _Response:
        calls.append((request, timeout))
        if len(calls) == 1:
            raise _http_error(429, b'{"errors":[{"message":"rate limited"}]}', {"Retry-After": "0"})
        return _Response(b'{"data":{"ok":true}}')

    monkeypatch.setattr("opentargets_cli.graphql_api.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("opentargets_cli.graphql_api.time.sleep", lambda delay: sleeps.append(delay))

    client = OpenTargetsClient("https://example.test/graphql", timeout=7, user_agent="ot-test")
    response = client.execute("query { ok }")

    assert response == {"data": {"ok": True}}
    assert len(calls) == 2
    assert sleeps == [0.0]


def test_retryable_http_json_body_exhaustion_is_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_urlopen(request: object, timeout: int) -> _Response:
        calls.append((request, timeout))
        raise _http_error(503, b'{"errors":[{"message":"temporarily unavailable"}]}')

    monkeypatch.setattr("opentargets_cli.graphql_api.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("opentargets_cli.graphql_api.time.sleep", lambda delay: None)

    client = OpenTargetsClient("https://example.test/graphql", timeout=7, user_agent="ot-test")
    with pytest.raises(CLIError) as exc_info:
        client.execute("query { ok }")

    error = exc_info.value
    assert error.code == "network"
    assert error.exit_code == 3
    assert error.details["status_code"] == 503
    assert error.details["response"] == {"errors": [{"message": "temporarily unavailable"}]}
    assert len(calls) == 2
