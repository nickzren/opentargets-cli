from __future__ import annotations

from typing import Any

from graphql import (
    GraphQLEnumType,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLList,
    GraphQLNamedType,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLSchema,
    GraphQLUnionType,
    print_schema,
    print_type,
)

from opentargets_cli.config import CATEGORY_SPECS

BUILTIN_SCALARS = {"String", "Int", "Float", "Boolean", "ID"}


def format_type_ref(graphql_type: Any) -> str:
    if isinstance(graphql_type, GraphQLNonNull):
        return f"{format_type_ref(graphql_type.of_type)}!"
    if isinstance(graphql_type, GraphQLList):
        return f"[{format_type_ref(graphql_type.of_type)}]"
    return getattr(graphql_type, "name", str(graphql_type))


def unwrap_named_type(graphql_type: Any) -> GraphQLNamedType:
    while hasattr(graphql_type, "of_type"):
        graphql_type = graphql_type.of_type
    return graphql_type


def is_renderable_type_name(type_name: str) -> bool:
    return not type_name.startswith("__") and type_name not in BUILTIN_SCALARS


def referenced_type_names(graphql_type: GraphQLNamedType) -> set[str]:
    referenced: set[str] = set()
    if isinstance(graphql_type, GraphQLObjectType | GraphQLInterfaceType):
        for field in graphql_type.fields.values():
            referenced.add(unwrap_named_type(field.type).name)
            for argument in field.args.values():
                referenced.add(unwrap_named_type(argument.type).name)
    elif isinstance(graphql_type, GraphQLInputObjectType):
        for field in graphql_type.fields.values():
            referenced.add(unwrap_named_type(field.type).name)
    elif isinstance(graphql_type, GraphQLUnionType):
        for possible in graphql_type.types:
            referenced.add(possible.name)
    return {name for name in referenced if is_renderable_type_name(name)}


def get_reachable_types(schema: GraphQLSchema, seed_types: set[str]) -> set[str]:
    pending = [name for name in seed_types if is_renderable_type_name(name)]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        graphql_type = schema.get_type(current)
        if graphql_type is None or not is_renderable_type_name(current):
            continue
        seen.add(current)
        pending.extend(sorted(referenced_type_names(graphql_type) - seen))
    return seen


def field_seed_types(schema: GraphQLSchema, field_names: set[str]) -> set[str]:
    query_type = schema.query_type
    if query_type is None:
        return set()
    seeds: set[str] = set()
    for field_name in field_names:
        field = query_type.fields.get(field_name)
        if field is None:
            continue
        seeds.add(unwrap_named_type(field.type).name)
        for argument in field.args.values():
            seeds.add(unwrap_named_type(argument.type).name)
    return {name for name in seeds if is_renderable_type_name(name)}


def build_query_subset_sdl(schema: GraphQLSchema, field_names: set[str]) -> str:
    query_type = schema.query_type
    if query_type is None:
        return ""
    selected_fields = {name: field for name, field in query_type.fields.items() if name in field_names}
    if not selected_fields:
        return ""
    subset = GraphQLObjectType(name="Query", fields=selected_fields, description=query_type.description)
    return print_type(subset)


def render_sdl(schema: GraphQLSchema, type_names: set[str], *, query_fields: set[str] | None = None) -> str:
    parts: list[str] = []
    if query_fields:
        query_sdl = build_query_subset_sdl(schema, query_fields)
        if query_sdl:
            parts.append(query_sdl)
    for type_name in sorted(type_names):
        graphql_type = schema.get_type(type_name)
        if graphql_type is None or not is_renderable_type_name(type_name):
            continue
        parts.append(print_type(graphql_type))
    return "\n\n".join(part for part in parts if part)


def serialize_argument(argument: Any) -> dict[str, Any]:
    return {"name": argument.name, "type": format_type_ref(argument.type)}


def serialize_field(name: str, field: Any) -> dict[str, Any]:
    return {
        "name": name,
        "type": format_type_ref(field.type),
        "arguments": [serialize_argument(argument) for argument in field.args.values()],
    }


def serialize_type(schema: GraphQLSchema, type_name: str) -> dict[str, Any] | None:
    graphql_type = schema.get_type(type_name)
    if graphql_type is None or not is_renderable_type_name(type_name):
        return None
    payload: dict[str, Any] = {"name": graphql_type.name, "kind": type(graphql_type).__name__.removeprefix("GraphQL")}
    if isinstance(graphql_type, GraphQLObjectType | GraphQLInterfaceType):
        payload["fields"] = [serialize_field(name, field) for name, field in graphql_type.fields.items()]
    elif isinstance(graphql_type, GraphQLInputObjectType):
        payload["input_fields"] = [
            {"name": name, "type": format_type_ref(field.type)} for name, field in graphql_type.fields.items()
        ]
    elif isinstance(graphql_type, GraphQLEnumType):
        payload["enum_values"] = list(graphql_type.values)
    elif isinstance(graphql_type, GraphQLUnionType):
        payload["possible_types"] = [possible.name for possible in graphql_type.types]
    elif isinstance(graphql_type, GraphQLScalarType):
        payload["scalar"] = graphql_type.name
    payload["definition"] = print_type(graphql_type)
    return payload


def serialize_types(schema: GraphQLSchema, type_names: set[str] | list[str]) -> list[dict[str, Any]]:
    payloads = [serialize_type(schema, type_name) for type_name in sorted(type_names)]
    return [payload for payload in payloads if payload is not None]


def serialize_query_fields(schema: GraphQLSchema, field_names: set[str]) -> list[dict[str, Any]]:
    query_type = schema.query_type
    if query_type is None:
        return []
    return [serialize_field(name, field) for name, field in query_type.fields.items() if name in field_names]


def build_category_slice(schema: GraphQLSchema, categories: list[str], schema_format: str) -> dict[str, Any]:
    root_fields: set[str] = set()
    seed_types: set[str] = set()
    for category_name in categories:
        spec = CATEGORY_SPECS[category_name]
        root_fields.update(spec.root_fields)
        seed_types.update(spec.seed_types)
    seed_types.update(field_seed_types(schema, root_fields))
    reachable_types = get_reachable_types(schema, seed_types)
    if schema_format == "sdl":
        return {
            "schema_format": "sdl",
            "requested_categories": categories,
            "schema_text": render_sdl(schema, reachable_types, query_fields=root_fields),
            "notes": ["Focused schema subset for the requested categories"],
        }
    return {
        "schema_format": "json",
        "requested_categories": categories,
        "schema_json": {
            "query_fields": serialize_query_fields(schema, root_fields),
            "types": serialize_types(schema, reachable_types),
        },
        "notes": ["Focused schema subset for the requested categories"],
    }


def build_full_schema(schema: GraphQLSchema, schema_format: str) -> dict[str, Any]:
    if schema_format == "sdl":
        return {"schema_format": "sdl", "requested_categories": [], "schema_text": print_schema(schema), "notes": ["Full live schema"]}
    type_names = sorted(
        name for name in schema.type_map if is_renderable_type_name(name) and schema.get_type(name) is not None
    )
    return {
        "schema_format": "json",
        "requested_categories": [],
        "schema_json": {"types": serialize_types(schema, type_names)},
        "notes": ["Full live schema"],
    }


def build_type_view(schema: GraphQLSchema, requested_type: str, with_dependencies: bool, schema_format: str) -> dict[str, Any]:
    selected_types = {requested_type}
    if with_dependencies:
        selected_types = get_reachable_types(schema, {requested_type})
    if schema_format == "sdl":
        return {
            "requested_type": requested_type,
            "with_dependencies": with_dependencies,
            "schema_format": "sdl",
            "schema_text": render_sdl(schema, selected_types),
        }
    return {
        "requested_type": requested_type,
        "with_dependencies": with_dependencies,
        "schema_format": "json",
        "schema_json": {"types": serialize_types(schema, selected_types)},
    }


def suggest_types(schema: GraphQLSchema, requested_type: str) -> list[str]:
    lowered = requested_type.lower()
    candidates = [name for name in schema.type_map if lowered in name.lower() and is_renderable_type_name(name)]
    return sorted(candidates)[:5]
