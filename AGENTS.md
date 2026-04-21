# Open Targets CLI Agent Instructions

Use this repo to answer read-only Open Targets Platform questions through the local `ot` CLI.

## Setup

- Prefer `ot` from `PATH` if available.
- If `ot` is missing and this repo has `.venv/bin/ot`, use `.venv/bin/ot`.
- If `ot` is missing and `.venv/bin/ot` is also missing, set up a repo-local environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Then use `.venv/bin/ot`.

For chat-anywhere setup from an installed package, run:

```bash
ot install-skills
```

## Workflow

1. Discover the CLI once:

```bash
ot doctor
ot tools
ot describe install-skills
ot describe resolve
ot describe gql
```

2. Get provenance once:

```bash
ot meta --no-downloads
```

3. Resolve user-provided names before querying:

```bash
ot resolve "BRCA1" --entity target --limit 5
ot resolve "type 2 diabetes" --entity disease --limit 5
ot resolve "trastuzumab" --entity drug --limit 5
```

4. Inspect focused schema only when needed:

```bash
ot schema --category targets --category associations
ot type AssociatedDisease
```

5. Execute read-only GraphQL with `ot gql`.

Never run mutations or subscriptions. The CLI rejects them, but do not attempt them.

For repeated execution of the same query with different variables, prefer batch mode:

```bash
ot gql --query-file query.graphql --variables-list vars.ndjson --key-field ensemblId
```

## Query Rules

- For association sorting, use `orderByScore: "score"`.
- `orderByScore` takes a field name, not a direction. Do not use `orderByScore: "desc"`.
- When `ot resolve` returns `ambiguous`, show candidates with `id`, `name`, and `description`, then ask the user to choose.
- For evidence questions about genetics, causality, or human evidence, prefer focused `datasourceIds` and exclude `europepmc` unless the user asks for literature.
- Keep result limits small and state any limit, filter, or sort used.
- In batch mode, each `vars.ndjson` line is one variables object; inspect per-row `status` before summarizing.

## Answer Format

Give the plain-English answer first. Include resolved IDs, query assumptions, and the Open Targets data/API version when relevant.
