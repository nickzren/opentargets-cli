from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import sysconfig
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graphql import OperationType, parse

from opentargets_cli import __version__
from opentargets_cli.config import (
    AMBIGUITY_MARGIN,
    AMBIGUITY_THRESHOLD,
    CATEGORY_SPECS,
    DISEASE_ID_PATTERN,
    DRUG_ID_PATTERN,
    ENTITY_TYPES,
    STUDY_ID_PATTERN,
    TARGET_ID_PATTERN,
    VARIANT_ID_PATTERN,
    default_endpoint,
    default_timeout,
    default_user_agent,
)
from opentargets_cli.graphql_api import CLIError, OpenTargetsClient
from opentargets_cli.schema_tools import build_category_slice, build_full_schema, build_type_view, suggest_types
from opentargets_cli.specs import COMMAND_SPECS, describe_payload, tools_payload

MAP_IDS_QUERY = """
query ResolveMapIds($terms: [String!]!, $entityNames: [String!]) {
  mapIds(queryTerms: $terms, entityNames: $entityNames) {
    total
    mappings {
      term
      hits {
        id
        entity
        name
        category
        description
        score
      }
    }
  }
}
""".strip()

SEARCH_QUERY = """
query ResolveSearch($queryString: String!, $entityNames: [String!], $page: Pagination) {
  search(queryString: $queryString, entityNames: $entityNames, page: $page) {
    total
    hits {
      id
      entity
      name
      category
      description
      score
    }
  }
}
""".strip()

TRANSPORT_ERROR_CODES = {"network", "timeout", "malformed_response"}

@dataclass(frozen=True)
class DirectIdQuery:
    query: str
    field_name: str
    id_key: str


DIRECT_ID_QUERIES: dict[str, DirectIdQuery] = {
    "target": DirectIdQuery(
        query="""
        query ValidateTarget($id: String!) {
          target(ensemblId: $id) {
            id
            approvedSymbol
            approvedName
          }
        }
        """.strip(),
        field_name="target",
        id_key="id",
    ),
    "disease": DirectIdQuery(
        query="""
        query ValidateDisease($id: String!) {
          disease(efoId: $id) {
            id
            name
            description
          }
        }
        """.strip(),
        field_name="disease",
        id_key="id",
    ),
    "drug": DirectIdQuery(
        query="""
        query ValidateDrug($id: String!) {
          drug(chemblId: $id) {
            id
            name
            maximumClinicalStage
          }
        }
        """.strip(),
        field_name="drug",
        id_key="id",
    ),
    "variant": DirectIdQuery(
        query="""
        query ValidateVariant($id: String!) {
          variant(variantId: $id) {
            id
            variantDescription
            hgvsId
          }
        }
        """.strip(),
        field_name="variant",
        id_key="id",
    ),
    "study": DirectIdQuery(
        query="""
        query ValidateStudy($id: String!) {
          study(studyId: $id) {
            studyId
            traitReported
          }
        }
        """.strip(),
        field_name="study",
        id_key="studyId",
    ),
}

DIRECT_ID_PATTERNS = (
    ("target", TARGET_ID_PATTERN),
    ("drug", DRUG_ID_PATTERN),
    ("variant", VARIANT_ID_PATTERN),
    ("study", STUDY_ID_PATTERN),
    ("disease", DISEASE_ID_PATTERN),
)


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def version_string(parts: dict[str, Any]) -> str:
    base = ".".join(str(parts[key]) for key in ("x", "y", "z"))
    suffix = parts.get("suffix")
    return f"{base}-{suffix}" if suffix else base


def data_version_string(parts: dict[str, Any]) -> str:
    base = ".".join(str(parts[key]) for key in ("year", "month"))
    iteration = parts.get("iteration")
    return f"{base}.{iteration}" if iteration else base


def version_pair(meta: dict[str, Any]) -> dict[str, str]:
    return {
        "api_version": version_string(meta["apiVersion"]),
        "data_version": data_version_string(meta["dataVersion"]),
    }


def static_meta_block(endpoint: str, template: str) -> dict[str, Any]:
    return {
        "tool": "ot",
        "endpoint": endpoint,
        "queried_at_utc": utc_now(),
        "template": template,
    }


def build_meta_block(client: OpenTargetsClient, template: str) -> dict[str, Any]:
    meta = client.fetch_meta()
    static = static_meta_block(client.endpoint, template)
    versions = version_pair(meta)
    return {
        "tool": static["tool"],
        "endpoint": static["endpoint"],
        "api_version": versions["api_version"],
        "data_version": versions["data_version"],
        "product": meta["product"],
        "queried_at_utc": static["queried_at_utc"],
        "template": static["template"],
    }


def build_envelope(
    *,
    status: str,
    meta: dict[str, Any],
    command: str,
    args: dict[str, Any],
    resolved: dict[str, Any] | None = None,
    warnings: list[Any] | None = None,
    data: dict[str, Any] | None = None,
    error: CLIError | None = None,
) -> dict[str, Any]:
    envelope = {
        "status": status,
        "meta": meta,
        "request": {
            "command": command,
            "args": args,
            "resolved": resolved or {},
        },
        "warnings": warnings or [],
    }
    if error is not None:
        envelope["error"] = {
            "code": error.code,
            "message": error.message,
            "details": error.details,
        }
    else:
        envelope["data"] = data or {}
    return envelope


def build_success_envelope(
    *,
    client: OpenTargetsClient,
    command: str,
    template: str,
    args: dict[str, Any],
    resolved: dict[str, Any] | None = None,
    status: str = "ok",
    warnings: list[Any] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_envelope(
        status=status,
        meta=build_meta_block(client, template),
        command=command,
        args=args,
        resolved=resolved,
        warnings=warnings,
        data=data,
    )


def build_error_envelope(
    *,
    endpoint: str,
    command: str,
    template: str,
    args: dict[str, Any],
    resolved: dict[str, Any] | None,
    error: CLIError,
) -> dict[str, Any]:
    return build_envelope(
        status="error",
        meta=static_meta_block(endpoint, template),
        command=command,
        args=args,
        resolved=resolved,
        warnings=[],
        error=error,
    )


def build_local_success_envelope(
    *,
    endpoint: str,
    command: str,
    template: str,
    args: dict[str, Any],
    resolved: dict[str, Any] | None = None,
    status: str = "ok",
    warnings: list[Any] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_envelope(
        status=status,
        meta=static_meta_block(endpoint, template),
        command=command,
        args=args,
        resolved=resolved,
        warnings=warnings,
        data=data,
    )


def gql_query_source(args: argparse.Namespace, *, stdin_label: str | None) -> str | None:
    if getattr(args, "query", None):
        return "inline"
    if getattr(args, "query_file", None):
        return "file"
    return stdin_label


def error_args_from_namespace(args: argparse.Namespace) -> dict[str, Any]:
    command = getattr(args, "command", "unknown")
    if command == "meta":
        return {"no_downloads": getattr(args, "no_downloads", False)}
    if command == "tools":
        return {}
    if command == "doctor":
        return {}
    if command == "install-skills":
        return {"agent": getattr(args, "agent", "auto")}
    if command == "describe":
        return {"command": getattr(args, "command_name", None)}
    if command == "resolve":
        return compact_dict(
            {
                "term": getattr(args, "term", None),
                "entity": getattr(args, "entity", None),
                "limit": getattr(args, "limit", None),
                "search_fallback": getattr(args, "search_fallback", None),
            }
        )
    if command == "schema":
        return {
            "list_categories": getattr(args, "list_categories", False),
            "category": getattr(args, "category", []),
            "full": getattr(args, "full", False),
            "schema_format": getattr(args, "schema_format", "sdl"),
        }
    if command == "type":
        return compact_dict(
            {
                "graphql_type": getattr(args, "graphql_type", None),
                "with_dependencies": getattr(args, "with_dependencies", False),
                "schema_format": getattr(args, "schema_format", "sdl"),
            }
        )
    if command == "gql":
        return compact_dict(
            {
                "query_source": gql_query_source(args, stdin_label=None),
                "variables_source": "inline"
                if getattr(args, "variables", None)
                else "file"
                if getattr(args, "variables_file", None)
                else "list"
                if getattr(args, "variables_list", None)
                else None,
                "operation_name": getattr(args, "operation_name", None),
                "variables_list": getattr(args, "variables_list", None),
                "key_field": getattr(args, "key_field", None),
                "max_items": getattr(args, "max_items", None) if getattr(args, "variables_list", None) else None,
            }
        )
    return {}


def template_from_namespace(args: argparse.Namespace) -> str:
    command = getattr(args, "command", "unknown")
    if command == "gql" and getattr(args, "variables_list", None):
        return "gql.batch"
    return command if command in COMMAND_SPECS else "unknown"


def emit_output(envelope: dict[str, Any], output_format: str, exit_code: int) -> int:
    if output_format == "json":
        text = json.dumps(envelope, indent=2)
    elif output_format == "table":
        text = render_table(envelope)
    else:
        text = render_text(envelope)
    stream = sys.stderr if exit_code else sys.stdout
    print(text, file=stream)
    return exit_code


def render_table(envelope: dict[str, Any]) -> str:
    command = envelope["request"]["command"]
    data = envelope.get("data", {})
    if command == "resolve":
        rows = data.get("candidates", [])
        headers = ("id", "name", "entity", "score")
        lines = ["\t".join(headers)]
        for row in rows:
            lines.append("\t".join(str(row.get(header, "")) for header in headers))
        return "\n".join(lines)
    if command == "tools":
        lines = ["name\tsummary"]
        for row in data.get("commands", []):
            lines.append(f"{row['name']}\t{row['summary']}")
        return "\n".join(lines)
    if command == "schema" and "categories" in data:
        lines = ["name\tsummary"]
        for row in data["categories"]:
            lines.append(f"{row['name']}\t{row['summary']}")
        return "\n".join(lines)
    return render_text(envelope)


def render_text(envelope: dict[str, Any]) -> str:
    status = envelope["status"]
    command = envelope["request"]["command"]
    lines = [f"status: {status}", f"command: {command}"]
    if status == "error":
        error = envelope["error"]
        lines.append(f"error: {error['code']} - {error['message']}")
        return "\n".join(lines)
    meta = envelope["meta"]
    if "api_version" in meta:
        lines.append(f"api_version: {meta['api_version']}")
    if "data_version" in meta:
        lines.append(f"data_version: {meta['data_version']}")
    lines.append(json.dumps(envelope["data"], indent=2))
    return "\n".join(lines)


def normalize_entity(entity: str) -> str:
    return "credibleSet" if entity == "credible_set" else entity


def parse_json_object(text: str, *, invalid_message: str, object_message: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CLIError("usage", invalid_message, exit_code=2) from exc
    if not isinstance(parsed, dict):
        raise CLIError("usage", object_message, exit_code=2)
    return parsed


def read_json_arg(raw: str | None, path: str | None) -> dict[str, Any] | None:
    if raw and path:
        raise CLIError("usage", "Choose either --variables or --variables-file, not both.", exit_code=2)
    if raw:
        return parse_json_object(
            raw,
            invalid_message="Invalid JSON passed to --variables.",
            object_message="--variables must decode to a JSON object.",
        )
    if path:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise CLIError("usage", f"Variables file not found: {path}", exit_code=2) from exc
        return parse_json_object(
            text,
            invalid_message=f"Variables file is not valid JSON: {path}",
            object_message="--variables-file must contain a JSON object.",
        )
    return None


def read_variables_list(path: str, max_items: int) -> list[dict[str, Any]]:
    if max_items <= 0:
        raise CLIError("usage", "--max-items must be a positive integer.", exit_code=2)
    variables_list: list[dict[str, Any]] = []
    try:
        with Path(path).open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                if len(variables_list) >= max_items:
                    raise CLIError(
                        "usage",
                        "Variables list exceeds --max-items.",
                        details={"max_items": max_items},
                        exit_code=2,
                    )
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise CLIError(
                        "usage",
                        "Variables list file contains invalid JSON.",
                        details={"line": line_number, "reason": str(exc)},
                        exit_code=2,
                    ) from exc
                if not isinstance(parsed, dict):
                    raise CLIError(
                        "usage",
                        "Each variables list line must decode to a JSON object.",
                        details={"line": line_number},
                        exit_code=2,
                    )
                variables_list.append(parsed)
    except FileNotFoundError as exc:
        raise CLIError("usage", f"Variables list file not found: {path}", exit_code=2) from exc
    if not variables_list:
        raise CLIError("usage", "Variables list file cannot be empty.", exit_code=2)
    return variables_list


def read_query_text(inline: str | None, file_path: str | None) -> str:
    provided_sources = sum(bool(value) for value in (inline, file_path))
    stdin_text = ""
    if not sys.stdin.isatty():
        stdin_text = sys.stdin.read()
        if stdin_text.strip():
            provided_sources += 1
    if provided_sources != 1:
        raise CLIError(
            "usage",
            "Provide exactly one GraphQL source: --query, --query-file, or stdin.",
            exit_code=2,
        )
    if inline:
        return inline
    if file_path:
        try:
            return Path(file_path).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise CLIError("usage", f"Query file not found: {file_path}", exit_code=2) from exc
    return stdin_text


def validate_query_is_read_only(query_text: str) -> None:
    try:
        document = parse(query_text)
    except Exception as exc:
        raise CLIError("usage", "GraphQL document could not be parsed.", details={"reason": str(exc)}, exit_code=2) from exc
    for definition in document.definitions:
        operation = getattr(definition, "operation", None)
        if operation in {OperationType.MUTATION, OperationType.SUBSCRIPTION}:
            raise CLIError(
                "usage",
                "ot is read-only and rejects mutation and subscription operations.",
                exit_code=2,
            )


def infer_direct_entity(term: str, entity_filter: str | None) -> str | None:
    for entity, pattern in DIRECT_ID_PATTERNS:
        if entity_filter in (None, entity) and pattern.match(term):
            return entity
    return None


def candidate_from_direct_hit(entity: str, record: dict[str, Any]) -> dict[str, Any]:
    if entity == "target":
        return {
            "id": record["id"],
            "name": record.get("approvedSymbol") or record["id"],
            "entity": entity,
            "category": [],
            "score": 1.0,
            "description": record.get("approvedName"),
        }
    if entity == "study":
        return {
            "id": record["studyId"],
            "name": record["studyId"],
            "entity": entity,
            "category": ["study"],
            "score": 1.0,
            "description": record.get("traitReported"),
        }
    description = record.get("description") or record.get("variantDescription") or record.get("maximumClinicalStage")
    return {
        "id": record["id"],
        "name": record.get("name") or record["id"],
        "entity": entity,
        "category": [],
        "score": 1.0,
        "description": description,
    }


def normalize_hit(hit: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "id": hit["id"],
        "name": hit["name"],
        "entity": "credible_set" if hit["entity"] == "credibleSet" else hit["entity"],
        "category": hit.get("category") or [],
        "score": round(score, 6),
        "description": hit.get("description"),
    }


def choose_resolution_status(candidates: list[dict[str, Any]], entity_filter: str | None) -> str:
    if not candidates:
        return "not_found"
    if len(candidates) == 1:
        return "ok"
    top = candidates[0]
    runner_up = candidates[1]
    if entity_filter and top["entity"] != entity_filter:
        return "ambiguous"
    if top["score"] < AMBIGUITY_THRESHOLD:
        return "ambiguous"
    if (top["score"] - runner_up["score"]) < AMBIGUITY_MARGIN:
        return "ambiguous"
    return "ok"


def resolve_direct_id(client: OpenTargetsClient, entity: str, term: str) -> list[dict[str, Any]]:
    spec = DIRECT_ID_QUERIES[entity]
    response = client.execute(spec.query, variables={"id": term})
    record = response.get("data", {}).get(spec.field_name)
    if not isinstance(record, dict):
        return []
    return [candidate_from_direct_hit(entity, record)]


def resolve_map_ids(client: OpenTargetsClient, term: str, entity_filter: str | None) -> list[dict[str, Any]]:
    variables: dict[str, Any] = {"terms": [term]}
    if entity_filter:
        variables["entityNames"] = [normalize_entity(entity_filter)]
    response = client.execute(MAP_IDS_QUERY, variables=variables)
    mappings = response.get("data", {}).get("mapIds", {}).get("mappings", [])
    if not mappings:
        return []
    hits = mappings[0].get("hits", [])
    return [normalize_hit(hit, 1.0) for hit in hits]


def resolve_search(client: OpenTargetsClient, term: str, entity_filter: str | None, limit: int) -> list[dict[str, Any]]:
    variables: dict[str, Any] = {"queryString": term, "page": {"index": 0, "size": limit}}
    if entity_filter:
        variables["entityNames"] = [normalize_entity(entity_filter)]
    response = client.execute(SEARCH_QUERY, variables=variables)
    hits = response.get("data", {}).get("search", {}).get("hits", [])
    if not hits:
        return []
    top_score = float(hits[0]["score"]) if hits[0].get("score") else 1.0
    normalized: list[dict[str, Any]] = []
    for hit in hits[:limit]:
        raw_score = float(hit.get("score") or 0.0)
        normalized_score = raw_score / top_score if top_score > 0 else 0.0
        normalized.append(normalize_hit(hit, normalized_score))
    return normalized


def list_categories_payload() -> dict[str, Any]:
    return {"categories": [{"name": spec.name, "summary": spec.summary} for spec in CATEGORY_SPECS.values()]}


def handle_meta(client: OpenTargetsClient, args: argparse.Namespace) -> dict[str, Any]:
    meta = client.fetch_meta()
    api_version_parts = meta["apiVersion"]
    data_version_parts = meta["dataVersion"]
    versions = version_pair(meta)
    data: dict[str, Any] = {
        "name": meta["name"],
        "product": meta["product"],
        "data_prefix": meta["dataPrefix"],
        "enable_data_release_prefix": meta["enableDataReleasePrefix"],
        "api_version": versions["api_version"],
        "api_version_parts": api_version_parts,
        "data_version": versions["data_version"],
        "data_version_parts": data_version_parts,
    }
    if not args.no_downloads:
        data["downloads"] = meta.get("downloads")
    return build_success_envelope(
        client=client,
        command="meta",
        template="meta",
        args={"no_downloads": args.no_downloads},
        data=data,
    )


def handle_tools(client: OpenTargetsClient, args: argparse.Namespace) -> dict[str, Any]:
    return build_local_success_envelope(
        endpoint=client.endpoint,
        command="tools",
        template="tools",
        args={},
        data=tools_payload(),
    )


def read_skill_version(skill_dir: Path) -> str | None:
    skill_file = skill_dir / "SKILL.md"
    try:
        lines = skill_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return None
        if stripped.startswith("version:"):
            return stripped.split(":", 1)[1].strip().strip("'\"") or None
    return None


def normalized_path(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def skill_check(path: Path) -> dict[str, Any]:
    installed = (path / "SKILL.md").is_file()
    version = read_skill_version(path) if installed else None
    return {
        "path": str(path),
        "installed": installed,
        "version": version,
        "version_matches": (version == __version__) if installed else None,
    }


def skill_source_dir() -> Path:
    data_root = Path(sysconfig.get_path("data"))
    installed = data_root / "share" / "opentargets-cli" / "skills" / "opentargets-cli"
    if (installed / "SKILL.md").is_file():
        return installed

    repo_root = Path(__file__).resolve().parents[2]
    editable = repo_root / "skills" / "opentargets-cli"
    if (editable / "SKILL.md").is_file():
        return editable

    raise CLIError(
        "internal",
        "Bundled Open Targets skill asset was not found.",
        details={"checked": [str(installed), str(editable)]},
        exit_code=1,
    )


def skill_destinations() -> dict[str, Path]:
    home = Path.home()
    codex_home = Path(os.getenv("CODEX_HOME", str(home / ".codex"))).expanduser()
    return {
        "claude": home / ".claude" / "skills" / "opentargets-cli",
        "codex": codex_home / "skills" / "opentargets-cli",
    }


def ensure_safe_skill_destination(agent: str, dest: Path) -> None:
    destinations = skill_destinations()
    expected = destinations[agent]
    normalized_dest = normalized_path(dest)
    normalized_expected = normalized_path(expected)
    if normalized_dest != normalized_expected:
        raise CLIError(
            "usage",
            "Refusing unsafe skill destination.",
            details={"agent": agent, "destination": str(dest), "expected": str(expected)},
            exit_code=2,
        )
    if agent == "codex":
        codex_home = normalized_path(Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex"))).expanduser())
        home = normalized_path(Path.home())
        if codex_home in {Path("/"), home}:
            raise CLIError(
                "usage",
                "Refusing unsafe CODEX_HOME for skill installation.",
                details={"CODEX_HOME": str(codex_home)},
                exit_code=2,
            )


def next_backup_path(dest: Path) -> Path:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = dest.with_name(f"{dest.name}.backup-{stamp}")
    if not backup.exists() and not backup.is_symlink():
        return backup
    suffix = 1
    while True:
        candidate = dest.with_name(f"{dest.name}.backup-{stamp}.{suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        suffix += 1


def copy_skill_tree(source: Path, dest: Path) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if dest.exists() or dest.is_symlink():
        backup = next_backup_path(dest)
        shutil.move(str(dest), str(backup))
    shutil.copytree(source, dest)
    return backup


def selected_skill_agents(agent: str) -> tuple[list[str], dict[str, bool], list[str]]:
    detected = {
        "claude": bool(shutil.which("claude")),
        "codex": bool(shutil.which("codex")),
    }
    warnings: list[str] = []
    if agent == "all":
        return ["claude", "codex"], detected, warnings
    if agent in {"claude", "codex"}:
        return [agent], detected, warnings

    selected = [name for name, is_detected in detected.items() if is_detected]
    if selected:
        return selected, detected, warnings
    warnings.append("No Claude Code or Codex command detected; installed both skill targets for future use.")
    return ["claude", "codex"], detected, warnings


def handle_install_skills(client: OpenTargetsClient, args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    source = skill_source_dir()
    agents, detected, warnings = selected_skill_agents(args.agent)
    destinations = skill_destinations()
    installed = []

    for agent in agents:
        dest = destinations[agent]
        ensure_safe_skill_destination(agent, dest)
        backup = copy_skill_tree(source, dest)
        installed.append(
            {
                "agent": agent,
                "path": str(dest),
                "backup_path": str(backup) if backup else None,
                "version": read_skill_version(dest),
            }
        )

    envelope = build_local_success_envelope(
        endpoint=client.endpoint,
        command="install-skills",
        template="install-skills",
        args={"agent": args.agent},
        resolved={
            "detected_agents": detected,
            "selected_agents": agents,
            "skill_source": str(source),
        },
        warnings=warnings,
        data={"installed": installed},
    )
    return envelope, 0


def repo_local_check(cwd: Path) -> dict[str, Any]:
    agents_md = (cwd / "AGENTS.md").is_file()
    claude_md = (cwd / "CLAUDE.md").is_file()
    return {
        "cwd": str(cwd),
        "agents_md": agents_md,
        "claude_md": claude_md,
        "available": agents_md or claude_md,
    }


def doctor_meta(endpoint: str, meta: dict[str, Any] | None) -> dict[str, Any]:
    base = static_meta_block(endpoint, "doctor")
    if meta is not None:
        base.update(version_pair(meta))
        base["product"] = meta["product"]
    return base


def api_reachability(client: OpenTargetsClient) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        api_meta = client.fetch_meta()
    except CLIError as error:
        return (
            {
                "reachable": False,
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                },
            },
            None,
        )
    versions = version_pair(api_meta)
    return {"reachable": True, **versions}, api_meta


def doctor_warnings_and_failures(
    *,
    ot_path: str | None,
    api: dict[str, Any],
    repo_local: dict[str, Any],
    detected_agents: dict[str, bool],
    claude_skill: dict[str, Any],
    codex_skill: dict[str, Any],
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    failures: list[str] = []

    if not ot_path:
        if repo_local["available"]:
            warnings.append("ot is not on PATH; repo-local agents must use .venv/bin/ot or run scripts/install.sh")
        else:
            failures.append("ot is not on PATH")
    if not api["reachable"]:
        failures.append("Open Targets API is not reachable")

    installed_skills = [check for check in (claude_skill, codex_skill) if check["installed"]]
    if not installed_skills and not repo_local["available"]:
        failures.append("no global skill is installed; run ot install-skills or start the agent from this repo")
    else:
        if detected_agents["claude"] and not claude_skill["installed"]:
            warnings.append("claude_skill not installed; run ot install-skills to enable chat-anywhere in Claude Code")
        if detected_agents["codex"] and not codex_skill["installed"]:
            warnings.append("codex_skill not installed; run ot install-skills to enable chat-anywhere in Codex")

    for name, check in (("claude_skill", claude_skill), ("codex_skill", codex_skill)):
        if check["installed"] and check["version_matches"] is not True:
            failures.append(f"{name} version does not match CLI version")

    return warnings, failures


def handle_doctor(client: OpenTargetsClient, args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    cwd = Path.cwd()
    codex_home = Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    claude_skill = skill_check(Path.home() / ".claude" / "skills" / "opentargets-cli")
    codex_skill = skill_check(codex_home / "skills" / "opentargets-cli")
    repo_local = repo_local_check(cwd)
    ot_path = shutil.which("ot")
    claude_command = shutil.which("claude")
    codex_command = shutil.which("codex")
    detected_agents = {
        "claude": bool(claude_command),
        "codex": bool(codex_command),
    }

    api, api_meta = api_reachability(client)
    warnings, failures = doctor_warnings_and_failures(
        ot_path=ot_path,
        api=api,
        repo_local=repo_local,
        detected_agents=detected_agents,
        claude_skill=claude_skill,
        codex_skill=codex_skill,
    )

    status = "error" if failures else "ok"
    data = {
        "cli": {
            "version": __version__,
            "on_path": bool(ot_path),
            "path": ot_path,
            "python": sys.executable,
        },
        "agents": {
            "claude": {
                "detected": bool(claude_command),
                "command": claude_command,
            },
            "codex": {
                "detected": bool(codex_command),
                "command": codex_command,
            },
        },
        "api": api,
        "repo_local": repo_local,
        "claude_skill": claude_skill,
        "codex_skill": codex_skill,
    }
    envelope: dict[str, Any] = {
        "status": status,
        "meta": doctor_meta(client.endpoint, api_meta),
        "request": {
            "command": "doctor",
            "args": {},
            "resolved": {},
        },
        "warnings": warnings,
        "data": data,
    }
    if failures:
        envelope["error"] = {
            "code": "doctor_failed",
            "message": "One or more doctor checks failed.",
            "details": {"failures": failures},
        }
    return envelope, 1 if failures else 0


def handle_describe(client: OpenTargetsClient, args: argparse.Namespace) -> dict[str, Any]:
    payload = describe_payload(args.command_name)
    status = "ok" if payload else "not_found"
    return build_local_success_envelope(
        endpoint=client.endpoint,
        command="describe",
        template="describe",
        args={"command": args.command_name},
        resolved={"described_command": args.command_name},
        status=status,
        data=payload or {"command": args.command_name},
    )


def handle_resolve(client: OpenTargetsClient, args: argparse.Namespace) -> dict[str, Any]:
    if args.limit <= 0:
        raise CLIError("usage", "--limit must be a positive integer.", exit_code=2)

    direct_entity = infer_direct_entity(args.term, args.entity)
    candidates: list[dict[str, Any]] = []
    resolution_method = "search"

    if direct_entity and direct_entity in DIRECT_ID_QUERIES:
        candidates = resolve_direct_id(client, direct_entity, args.term)
        resolution_method = "direct-id"
        if args.entity and direct_entity != args.entity:
            candidates = []

    if not candidates:
        candidates = resolve_map_ids(client, args.term, args.entity)
        resolution_method = "mapIds"

    if not candidates and args.search_fallback:
        candidates = resolve_search(client, args.term, args.entity, args.limit)
        resolution_method = "search"

    candidates = candidates[: args.limit]
    status = choose_resolution_status(candidates, args.entity)
    return build_success_envelope(
        client=client,
        command="resolve",
        template="resolve",
        args={
            "term": args.term,
            "entity": args.entity,
            "limit": args.limit,
            "search_fallback": args.search_fallback,
        },
        resolved={"entity_filter": args.entity},
        status=status,
        data={
            "term": args.term,
            "entity_filter": args.entity,
            "resolution_method": resolution_method,
            "candidates": candidates,
        },
    )


def handle_schema(client: OpenTargetsClient, args: argparse.Namespace) -> dict[str, Any]:
    if args.full and args.category:
        raise CLIError("usage", "Choose either --full or --category, not both.", exit_code=2)
    invalid = [name for name in args.category if name not in CATEGORY_SPECS]
    if invalid:
        raise CLIError(
            "usage",
            f"Unknown schema categories: {', '.join(invalid)}",
            details={"available_categories": sorted(CATEGORY_SPECS)},
            exit_code=2,
        )

    args_payload = {
        "list_categories": args.list_categories,
        "category": args.category,
        "full": args.full,
        "schema_format": args.schema_format,
    }
    if args.list_categories or not args.category and not args.full:
        data = list_categories_payload()
        return build_local_success_envelope(
            endpoint=client.endpoint,
            command="schema",
            template="schema",
            args=args_payload,
            data=data,
        )

    schema = client.fetch_schema()
    if args.full:
        data = build_full_schema(schema, args.schema_format)
    else:
        data = build_category_slice(schema, args.category, args.schema_format)
    return build_success_envelope(
        client=client,
        command="schema",
        template="schema",
        args=args_payload,
        data=data,
    )


def handle_type(client: OpenTargetsClient, args: argparse.Namespace) -> dict[str, Any]:
    schema = client.fetch_schema()
    args_payload = {
        "graphql_type": args.graphql_type,
        "with_dependencies": args.with_dependencies,
        "schema_format": args.schema_format,
    }
    if schema.get_type(args.graphql_type) is None:
        suggestions = suggest_types(schema, args.graphql_type)
        return build_success_envelope(
            client=client,
            command="type",
            template="type",
            args=args_payload,
            status="not_found",
            warnings=[{"suggestions": suggestions}] if suggestions else [],
            data={"requested_type": args.graphql_type},
        )
    return build_success_envelope(
        client=client,
        command="type",
        template="type",
        args=args_payload,
        data=build_type_view(schema, args.graphql_type, args.with_dependencies, args.schema_format),
    )


def classify_gql_response(response: dict[str, Any]) -> tuple[str, list[Any], dict[str, Any] | None, CLIError | None]:
    data = response.get("data")
    errors = response.get("errors")
    if errors and data is not None:
        warnings = errors if isinstance(errors, list) else [errors]
        return "partial", warnings, data, None
    if errors and data is None:
        return (
            "error",
            [],
            None,
            CLIError(
                "graphql",
                "GraphQL query failed without usable data.",
                details={"errors": errors},
                exit_code=5,
            ),
        )
    if data is None:
        return (
            "error",
            [],
            None,
            CLIError(
                "malformed_response",
                "GraphQL response did not contain a data object.",
                details={"response": response},
                exit_code=5,
            ),
        )
    return "ok", [], data, None


def row_error(index: int, variables: dict[str, Any], code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "index": index,
        "key": None,
        "variables": variables,
        "status": "error",
        "warnings": [],
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def execute_gql_batch_row(
    client: OpenTargetsClient,
    args: argparse.Namespace,
    query_text: str,
    index: int,
    variables: dict[str, Any],
) -> dict[str, Any]:
    if args.key_field not in variables:
        return row_error(
            index,
            variables,
            "usage",
            f"Key field '{args.key_field}' not found in variables.",
            {"key_field": args.key_field},
        )

    key = str(variables[args.key_field])
    try:
        response = client.execute(query_text, variables=variables, operation_name=args.operation_name)
        status, warnings, data, error = classify_gql_response(response)
        if error:
            if error.code in TRANSPORT_ERROR_CODES:
                raise error
            result = row_error(index, variables, error.code, error.message, error.details)
            result["key"] = key
            return result
        return {
            "index": index,
            "key": key,
            "variables": variables,
            "status": status,
            "graphql_data": data,
            "warnings": warnings,
        }
    except CLIError as error:
        if error.code in TRANSPORT_ERROR_CODES:
            raise
        result = row_error(index, variables, error.code, error.message, error.details)
        result["key"] = key
        return result


def handle_gql_batch(
    client: OpenTargetsClient,
    args: argparse.Namespace,
    query_text: str,
    emit_query: bool,
) -> tuple[dict[str, Any], int]:
    if args.variables or args.variables_file:
        raise CLIError("usage", "Use --variables-list instead of --variables or --variables-file for batch mode.", exit_code=2)
    if not args.key_field:
        raise CLIError("usage", "--key-field is required when using --variables-list.", exit_code=2)

    variables_list = read_variables_list(args.variables_list, args.max_items)
    results: list[dict[str, Any]] = []
    counts = {"ok": 0, "partial": 0, "error": 0}

    for index, variables in enumerate(variables_list):
        result = execute_gql_batch_row(client, args, query_text, index, variables)
        results.append(result)
        counts[result["status"]] += 1

    if counts["ok"] == len(results):
        status = "ok"
    elif counts["ok"] or counts["partial"]:
        status = "partial"
    else:
        status = "error"

    resolved: dict[str, Any] = {
        "operation_name": args.operation_name,
        "batch": True,
        "key_field": args.key_field,
    }
    if emit_query:
        resolved["rendered_query"] = query_text

    envelope = build_success_envelope(
        client=client,
        command="gql",
        template="gql.batch",
        args=compact_dict(
            {
                "query_source": gql_query_source(args, stdin_label="stdin"),
                "variables_source": "list",
                "variables_list": args.variables_list,
                "key_field": args.key_field,
                "max_items": args.max_items,
                "operation_name": args.operation_name,
            }
        ),
        resolved=resolved,
        status=status,
        data={
            "operation_name": args.operation_name,
            "summary": {
                "total": len(results),
                "successful": counts["ok"],
                "partial": counts["partial"],
                "failed": counts["error"],
            },
            "results": results,
        },
    )
    if status == "error":
        envelope["error"] = {
            "code": "batch_failed",
            "message": "All batch rows failed.",
            "details": {"summary": envelope["data"]["summary"]},
        }
    return envelope, 0 if status != "error" else 5


def handle_gql(client: OpenTargetsClient, args: argparse.Namespace, emit_query: bool) -> tuple[dict[str, Any], int]:
    query_text = read_query_text(args.query, args.query_file)
    validate_query_is_read_only(query_text)
    if args.variables_list:
        return handle_gql_batch(client, args, query_text, emit_query)

    variables = read_json_arg(args.variables, args.variables_file)
    response = client.execute(query_text, variables=variables, operation_name=args.operation_name)
    status, warnings, data, error = classify_gql_response(response)
    if error:
        raise error
    resolved = {
        "operation_name": args.operation_name,
    }
    if emit_query:
        resolved["rendered_query"] = query_text
        resolved["rendered_variables"] = variables or {}

    payload = {
        "operation_name": args.operation_name,
        "variables": variables or {},
        "graphql_data": data,
    }

    envelope = build_success_envelope(
        client=client,
        command="gql",
        template="gql",
        args=compact_dict(
            {
                "query_source": gql_query_source(args, stdin_label="stdin"),
                "variables_source": "inline" if args.variables else "file" if args.variables_file else None,
                "operation_name": args.operation_name,
            }
        ),
        resolved=resolved,
        status=status,
        warnings=warnings,
        data=payload,
    )
    return envelope, 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ot", description="Open Targets CLI")
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--format", choices=("json", "table", "text"), default="json")
    parser.add_argument("--endpoint", default=default_endpoint())
    parser.add_argument("--timeout", type=int, default=default_timeout())
    parser.add_argument("--emit-query", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    meta_parser = subparsers.add_parser("meta")
    meta_parser.add_argument(
        "--no-downloads",
        dest="no_downloads",
        action="store_true",
        help="Omit the downloads field from the response data.",
    )
    subparsers.add_parser("tools")
    subparsers.add_parser("doctor")

    install_skills_parser = subparsers.add_parser("install-skills")
    install_skills_parser.add_argument("--agent", choices=("auto", "claude", "codex", "all"), default="auto")

    describe_parser = subparsers.add_parser("describe")
    describe_parser.add_argument("command_name")

    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("term")
    resolve_parser.add_argument("--entity", choices=ENTITY_TYPES)
    resolve_parser.add_argument("--limit", type=int, default=5)
    resolve_parser.add_argument("--search-fallback", dest="search_fallback", action="store_true", default=True)
    resolve_parser.add_argument("--no-search-fallback", dest="search_fallback", action="store_false", help=argparse.SUPPRESS)

    schema_parser = subparsers.add_parser("schema")
    schema_parser.add_argument("--list-categories", action="store_true")
    schema_parser.add_argument("--category", action="append", default=[])
    schema_parser.add_argument("--full", action="store_true")
    schema_parser.add_argument("--schema-format", choices=("sdl", "json"), default="sdl")

    type_parser = subparsers.add_parser("type")
    type_parser.add_argument("graphql_type")
    type_parser.add_argument("--with-dependencies", action="store_true")
    type_parser.add_argument("--schema-format", choices=("sdl", "json"), default="sdl")

    gql_parser = subparsers.add_parser("gql")
    gql_parser.add_argument("--query")
    gql_parser.add_argument("--query-file")
    gql_parser.add_argument("--variables")
    gql_parser.add_argument("--variables-file")
    gql_parser.add_argument("--variables-list", help="Path to NDJSON variables for batch mode; one JSON object per line.")
    gql_parser.add_argument("--key-field", help="Variable field used as the stable key for each batch row.")
    gql_parser.add_argument(
        "--max-items",
        type=int,
        default=100,
        help="Maximum batch rows to execute. Batch continues on per-row errors by default.",
    )
    gql_parser.add_argument("--emit-query", action="store_true", default=argparse.SUPPRESS)
    gql_parser.add_argument("--operation-name")

    return parser


def dispatch(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.timeout <= 0:
        raise CLIError("usage", "--timeout must be a positive integer.", exit_code=2)
    client = OpenTargetsClient(endpoint=args.endpoint, timeout=args.timeout, user_agent=default_user_agent())

    if args.command == "meta":
        return handle_meta(client, args), 0
    if args.command == "tools":
        return handle_tools(client, args), 0
    if args.command == "doctor":
        return handle_doctor(client, args)
    if args.command == "install-skills":
        return handle_install_skills(client, args)
    if args.command == "describe":
        return handle_describe(client, args), 0
    if args.command == "resolve":
        return handle_resolve(client, args), 0
    if args.command == "schema":
        return handle_schema(client, args), 0
    if args.command == "type":
        return handle_type(client, args), 0
    if args.command == "gql":
        return handle_gql(client, args, args.emit_query)
    raise CLIError("usage", f"Unknown command: {args.command}", exit_code=2)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        envelope, exit_code = dispatch(args)
        return emit_output(envelope, args.format, exit_code)
    except CLIError as error:
        command = getattr(args, "command", "unknown")
        template = template_from_namespace(args)
        envelope = build_error_envelope(
            endpoint=getattr(args, "endpoint", default_endpoint()),
            command=command,
            template=template,
            args=error_args_from_namespace(args),
            resolved={},
            error=error,
        )
        return emit_output(envelope, getattr(args, "format", "json"), error.exit_code)
    except Exception as error:  # pragma: no cover - last-resort guardrail
        cli_error = CLIError("internal", str(error), exit_code=1)
        envelope = build_error_envelope(
            endpoint=getattr(args, "endpoint", default_endpoint()),
            command=getattr(args, "command", "unknown"),
            template=template_from_namespace(args),
            args={},
            resolved={},
            error=cli_error,
        )
        return emit_output(envelope, getattr(args, "format", "json"), cli_error.exit_code)
