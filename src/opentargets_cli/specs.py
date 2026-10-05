from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opentargets_cli.config import (
    AMBIGUITY_MARGIN,
    AMBIGUITY_THRESHOLD,
    CATEGORY_SPECS,
    CANONICAL_ID_RULES,
    ENTITY_TYPES,
)


@dataclass(frozen=True)
class ArgumentSpec:
    name: str
    type: str
    description: str
    required: bool
    default: Any = None
    enum: list[str] | None = None
    repeatable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
            "default": self.default,
            "enum": self.enum,
            "repeatable": self.repeatable,
        }


@dataclass(frozen=True)
class CommandSpec:
    name: str
    summary: str
    syntax: str
    status_values: tuple[str, ...]
    arguments: tuple[ArgumentSpec, ...] = ()
    examples: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def tool_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "status_values": list(self.status_values),
            "describe_command": f"ot describe {self.name}",
        }

    def describe_dict(self) -> dict[str, Any]:
        return {
            "command": self.name,
            "summary": self.summary,
            "syntax": self.syntax,
            "arguments": [argument.as_dict() for argument in self.arguments],
            "status_values": list(self.status_values),
            "examples": list(self.examples),
            "notes": list(self.notes),
        }


COMMAND_SPECS: dict[str, CommandSpec] = {
    "meta": CommandSpec(
        name="meta",
        summary="Return API and data release provenance",
        syntax="ot meta [--no-downloads]",
        status_values=("ok", "error"),
        arguments=(
            ArgumentSpec(
                name="--no-downloads",
                type="boolean",
                description="Omit the downloads field from data; recorded as request.args.no_downloads for auditability",
                required=False,
                default=False,
            ),
        ),
        examples=("ot meta", "ot meta --no-downloads"),
        notes=(
            "Returns live Open Targets release metadata.",
            "Default output preserves raw API values; --no-downloads is an explicit opt-out for the downloads blob.",
        ),
    ),
    "tools": CommandSpec(
        name="tools",
        summary="Return the machine-readable command inventory",
        syntax="ot tools",
        status_values=("ok", "error"),
        examples=("ot tools",),
        notes=("Compact inventory for session-start discovery.",),
    ),
    "doctor": CommandSpec(
        name="doctor",
        summary="Diagnose CLI, API, and agent-skill installation health",
        syntax="ot doctor",
        status_values=("ok", "error"),
        examples=("ot doctor",),
        notes=(
            "Reports diagnostics only; it does not install or modify files.",
            "Missing one global skill is reported as a warning when another supported activation path is available.",
        ),
    ),
    "install-skills": CommandSpec(
        name="install-skills",
        summary="Install bundled agent skill files for chat-anywhere use",
        syntax="ot install-skills [--agent auto|claude|codex|all]",
        status_values=("ok", "error"),
        arguments=(
            ArgumentSpec(
                name="--agent",
                type="string",
                description="Which agent skill target to install; auto installs detected agents, or both when none are detected",
                required=False,
                default="auto",
                enum=["auto", "claude", "codex", "all"],
            ),
        ),
        examples=("ot install-skills", "ot install-skills --agent all"),
        notes=(
            "Uses the skill bundled with the installed package, falling back to the repo skill during editable development.",
            "Existing skill directories are moved to timestamped backups in a sibling skill-backups directory before replacement.",
            "This command only modifies Claude/Codex skill and skill-backups directories.",
        ),
    ),
    "describe": CommandSpec(
        name="describe",
        summary="Return the detailed contract for one command",
        syntax="ot describe <command>",
        status_values=("ok", "not_found", "error"),
        arguments=(
            ArgumentSpec(
                name="<command>",
                type="string",
                description="Command name to inspect",
                required=True,
            ),
        ),
        examples=("ot describe resolve", "ot describe gql"),
    ),
    "resolve": CommandSpec(
        name="resolve",
        summary="Resolve names to canonical Open Targets IDs",
        syntax="ot resolve <term> [--entity <type>] [--limit <n>] [--search-fallback]",
        status_values=("ok", "ambiguous", "not_found", "error"),
        arguments=(
            ArgumentSpec(
                name="--entity",
                type="string",
                description="Restrict resolution to one entity type",
                required=False,
                default=None,
                enum=list(ENTITY_TYPES),
            ),
            ArgumentSpec(
                name="--limit",
                type="integer",
                description="Maximum number of candidates to return",
                required=False,
                default=5,
            ),
            ArgumentSpec(
                name="--search-fallback",
                type="boolean",
                description="Fall back to search when mapIds yields no useful hit",
                required=False,
                default=True,
            ),
        ),
        examples=("ot resolve 'BRCA1' --entity target --limit 5",),
        notes=(
            "Direct-ID detection is conservative and entity-aware.",
            "Resolution order is direct-id -> mapIds -> search.",
            f"Deterministic winner rule: top score >= {AMBIGUITY_THRESHOLD} and margin >= {AMBIGUITY_MARGIN}.",
            "Canonical direct-ID patterns: "
            + ", ".join(
                f"{entity}={pattern}"
                for entity, pattern in CANONICAL_ID_RULES.items()
                if pattern is not None
            ),
        ),
    ),
    "schema": CommandSpec(
        name="schema",
        summary="Fetch schema categories or list available categories",
        syntax="ot schema [--list-categories] [--category <name> ...] [--full] [--schema-format sdl|json]",
        status_values=("ok", "error"),
        arguments=(
            ArgumentSpec(
                name="--list-categories",
                type="boolean",
                description="List the pinned schema categories",
                required=False,
                default=False,
            ),
            ArgumentSpec(
                name="--category",
                type="string",
                description="Category name to include in the schema slice",
                required=False,
                default=[],
                enum=sorted(CATEGORY_SPECS.keys()),
                repeatable=True,
            ),
            ArgumentSpec(
                name="--full",
                type="boolean",
                description="Return the full live schema",
                required=False,
                default=False,
            ),
            ArgumentSpec(
                name="--schema-format",
                type="string",
                description="Schema serialization format",
                required=False,
                default="sdl",
                enum=["sdl", "json"],
            ),
        ),
        examples=(
            "ot schema --list-categories",
            "ot schema --category targets --category associations",
        ),
        notes=("Category slices are generated from a pinned root-field and seed-type registry.",),
    ),
    "type": CommandSpec(
        name="type",
        summary="Inspect one GraphQL type, optionally with dependencies",
        syntax="ot type <graphql_type> [--with-dependencies] [--schema-format sdl|json]",
        status_values=("ok", "not_found", "error"),
        arguments=(
            ArgumentSpec(
                name="<graphql_type>",
                type="string",
                description="GraphQL type name to inspect",
                required=True,
            ),
            ArgumentSpec(
                name="--with-dependencies",
                type="boolean",
                description="Include the recursive dependency closure of the requested type",
                required=False,
                default=False,
            ),
            ArgumentSpec(
                name="--schema-format",
                type="string",
                description="Schema serialization format",
                required=False,
                default="sdl",
                enum=["sdl", "json"],
            ),
        ),
        examples=("ot type Target", "ot type AssociatedDisease --with-dependencies"),
    ),
    "gql": CommandSpec(
        name="gql",
        summary="Execute a read-only GraphQL query",
        syntax="ot gql [--query <graphql> | --query-file <path> | stdin] [--variables <json> | --variables-file <path> | --variables-list <ndjson> --key-field <field>] [--operation-name <name>]",
        status_values=("ok", "partial", "error"),
        arguments=(
            ArgumentSpec(
                name="--query",
                type="string",
                description="Inline GraphQL query document",
                required=False,
            ),
            ArgumentSpec(
                name="--query-file",
                type="path",
                description="Path to a GraphQL document file",
                required=False,
            ),
            ArgumentSpec(
                name="--variables",
                type="json",
                description="Inline GraphQL variables object",
                required=False,
            ),
            ArgumentSpec(
                name="--variables-file",
                type="path",
                description="Path to a JSON file containing GraphQL variables",
                required=False,
            ),
            ArgumentSpec(
                name="--variables-list",
                type="path",
                description="Path to an NDJSON file for batch mode; each line must be a variables object",
                required=False,
            ),
            ArgumentSpec(
                name="--key-field",
                type="string",
                description="Variable field used as the stable key for each batch row",
                required=False,
            ),
            ArgumentSpec(
                name="--max-items",
                type="integer",
                description="Maximum batch rows to execute; batch continues on per-row errors by default",
                required=False,
                default=100,
            ),
            ArgumentSpec(
                name="--operation-name",
                type="string",
                description="Optional GraphQL operation name",
                required=False,
            ),
        ),
        examples=(
            "ot gql --query 'query { meta { name } }'",
            "ot gql --query-file query.graphql --variables-list vars.ndjson --key-field ensemblId",
        ),
        notes=(
            "Rejects mutation and subscription operations client-side.",
            "Honors the global --emit-query flag.",
            "Batch mode uses --variables-list with NDJSON variables and --key-field.",
            "Batch execution is serial and continues on per-row errors by default.",
            "GraphQL field selection is the projection mechanism.",
        ),
    ),
}


def tools_payload() -> dict[str, Any]:
    command_order = ("meta", "tools", "doctor", "install-skills", "describe", "resolve", "schema", "type", "gql")
    return {"commands": [COMMAND_SPECS[name].tool_dict() for name in command_order]}


def describe_payload(command_name: str) -> dict[str, Any] | None:
    spec = COMMAND_SPECS.get(command_name)
    if not spec:
        return None
    return spec.describe_dict()
