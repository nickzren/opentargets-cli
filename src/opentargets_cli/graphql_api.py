from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from graphql import build_client_schema, get_introspection_query
from graphql.type import GraphQLSchema

from opentargets_cli.config import CACHE_TTL_SECONDS, RETRYABLE_STATUS_CODES

META_QUERY = """
query Meta {
  meta {
    name
    product
    dataPrefix
    enableDataReleasePrefix
    downloads
    apiVersion { x y z suffix }
    dataVersion { year month iteration }
  }
}
""".strip()

INTROSPECTION_QUERY = get_introspection_query(descriptions=False)


class CLIError(Exception):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None, exit_code: int = 1) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.exit_code = exit_code


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


_CACHE: dict[tuple[str, str], CacheEntry] = {}


def _cache_get(endpoint: str, key: str) -> Any | None:
    entry = _CACHE.get((endpoint, key))
    if entry is None:
        return None
    if entry.expires_at < time.time():
        _CACHE.pop((endpoint, key), None)
        return None
    return entry.value


def _cache_set(endpoint: str, key: str, value: Any) -> None:
    _CACHE[(endpoint, key)] = CacheEntry(value=value, expires_at=time.time() + CACHE_TTL_SECONDS)


def _sleep_for_retry(retry_after: str | None) -> None:
    if retry_after:
        try:
            delay = max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                delay = max(0.0, (retry_at - datetime.now(tz=UTC)).total_seconds())
            except (TypeError, ValueError, IndexError, OverflowError):
                delay = 1.0
    else:
        delay = 1.0
    time.sleep(delay)


def _parse_http_error_body(exc: urllib.error.HTTPError) -> dict[str, Any] | None:
    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def compact_http_error_details(status_code: int, response: dict[str, Any] | None) -> dict[str, Any]:
    details: dict[str, Any] = {"status_code": status_code}
    if response is not None:
        details["response"] = response
    return details


class OpenTargetsClient:
    def __init__(self, endpoint: str, timeout: int, user_agent: str) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.user_agent = user_agent

    def execute(
        self,
        query: str,
        *,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        payload = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name
        body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
        )

        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise CLIError(
                        "malformed_response",
                        "Open Targets returned a non-object JSON response.",
                        exit_code=5,
                    )
                return parsed
            except urllib.error.HTTPError as exc:
                parsed = _parse_http_error_body(exc)
                if exc.code in RETRYABLE_STATUS_CODES and attempt == 0:
                    _sleep_for_retry(exc.headers.get("Retry-After"))
                    continue
                raise CLIError(
                    "network",
                    f"Open Targets returned HTTP {exc.code}.",
                    details=compact_http_error_details(exc.code, parsed),
                    exit_code=3,
                ) from exc
            except urllib.error.URLError as exc:
                if attempt == 0:
                    _sleep_for_retry(None)
                    continue
                reason = getattr(exc, "reason", exc)
                if isinstance(reason, TimeoutError | socket.timeout):
                    raise CLIError("timeout", "Open Targets request timed out.", exit_code=4) from exc
                raise CLIError(
                    "network",
                    "Open Targets request failed.",
                    details={"reason": str(reason)},
                    exit_code=3,
                ) from exc
            except socket.timeout as exc:
                raise CLIError("timeout", "Open Targets request timed out.", exit_code=4) from exc
            except json.JSONDecodeError as exc:
                raise CLIError(
                    "malformed_response",
                    "Open Targets returned invalid JSON.",
                    exit_code=5,
                ) from exc

        raise CLIError("network", "Open Targets request failed after retry.", exit_code=3)

    def fetch_meta(self) -> dict[str, Any]:
        cached = _cache_get(self.endpoint, "meta")
        if cached is not None:
            return cached
        response = self.execute(META_QUERY)
        meta = response.get("data", {}).get("meta")
        if not isinstance(meta, dict):
            raise CLIError(
                "graphql",
                "Open Targets meta query did not return a meta object.",
                details={"response": response},
                exit_code=5,
            )
        _cache_set(self.endpoint, "meta", meta)
        return meta

    def fetch_schema(self) -> GraphQLSchema:
        cached = _cache_get(self.endpoint, "schema")
        if cached is not None:
            return cached
        response = self.execute(INTROSPECTION_QUERY)
        data = response.get("data")
        if not isinstance(data, dict):
            raise CLIError(
                "graphql",
                "Open Targets introspection query did not return data.",
                details={"response": response},
                exit_code=5,
            )
        schema = build_client_schema(data)
        _cache_set(self.endpoint, "schema", schema)
        return schema
