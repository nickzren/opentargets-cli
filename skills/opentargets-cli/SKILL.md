---
name: opentargets-cli
version: 0.1.0
description: Use this skill for read-only Open Targets Platform questions when a local `ot` CLI is available. This skill assumes a model-first CLI that exposes self-describing commands: `ot doctor`, `ot install-skills`, `ot tools`, `ot describe`, `ot meta`, `ot resolve`, `ot schema`, `ot type`, and `ot gql`. Use it for command discovery, ID resolution, schema inspection, and executing custom Open Targets GraphQL. Do not use this skill for write operations or non-Open-Targets tasks.
---

# Open Targets CLI skill

This skill assumes a local `ot` command is available on `PATH`.

## Core rule

Use the CLI first. Do not start with raw `curl` or direct HTTP unless the user explicitly asks for a different workflow or the CLI is unavailable.

## Preconditions

- This skill is **read-only**.
- If `ot` is not installed, say the workspace is not configured for this skill.

## What this CLI is for

This CLI is a shell-native primitive surface for strong models.

Use it to:

- diagnose local setup
- install packaged agent skills when the user asks for chat-anywhere setup
- discover the command surface
- resolve names to IDs
- inspect schema categories or one GraphQL type
- write and execute GraphQL
- capture release provenance

Do not expect the CLI to contain a large library of high-level domain commands. The model is expected to do the planning.

## Workflow

### 1. Discover the CLI surface once per session

If you have not already learned the CLI surface in this session, run:

```bash
ot doctor
ot tools
```

If you need the exact contract for one command, run:

```bash
ot describe resolve
ot describe schema
ot describe gql
```

Reuse that knowledge in later steps instead of repeatedly rediscovering the CLI.

### 2. Get provenance once per session

If you have not already captured the current Open Targets API and data release in this session, run:

```bash
ot meta
```

Reuse that metadata in later answers.

### 3. Resolve names to IDs before entity-specific queries

If the user gave a plain-English name or loose label, resolve it first.

Examples:

```bash
ot resolve "BRCA1" --entity target --limit 5
ot resolve "type 2 diabetes" --entity disease --limit 5
ot resolve "trastuzumab" --entity drug --limit 5
ot resolve "GCST004131" --entity study --limit 5
```

Skip `resolve` only when the user already gave a canonical ID that fits the query directly.

### 4. Handle ambiguity explicitly

Read the `status` field from `ot resolve`.

- If `status=ok`, continue.
- If `status=ambiguous`, only continue automatically when the CLI itself already resolved one dominant candidate through its deterministic ambiguity rule.
- If `status=ambiguous` and no deterministic winner was returned, stop and ask the user to choose from the top candidates.
- When presenting ambiguous candidates, show `id`, `name`, and `description` so the user can make a real biological choice.
- If `status=not_found`, say that Open Targets did not return a match and show the exact term you tried.

Never invent IDs. Never silently swap one disease, target, or drug for another.

### 5. Inspect only the schema you need

Prefer focused inspection over full-schema dumping.

Use:

```bash
ot schema --list-categories
ot schema --category targets --category associations
ot type AssociatedDisease
ot type Target --with-dependencies
```

Guidance:

- The pinned schema categories are `targets`, `diseases`, `drugs`, `variants`, `studies`, `credible_sets`, `associations`, `evidence`, and `meta`.
- Start with `ot schema --category ...` when you know the relevant domain.
- Use `ot type <Name>` when one type is the main question.
- Use `--with-dependencies` sparingly.
- Avoid `ot schema --full` unless you are truly blocked without it.

### 6. Write GraphQL and execute it with `ot gql`

The model should write the query.
Use `query` operations only. Do not attempt `mutation` or `subscription`; the CLI is read-only and should reject them.

Common forms:

```bash
ot gql --query 'query { meta { name } }'
ot gql --query 'query GetTarget($ensemblId: String!) { target(ensemblId: $ensemblId) { id approvedSymbol } }' --variables '{"ensemblId":"ENSG00000012048"}'
ot gql --query-file query.graphql --variables-file vars.json
ot gql --query-file query.graphql --variables-list vars.ndjson --key-field ensemblId
```

Use `stdin` when it is cleaner than inline quoting.

Use `--variables-list` for repeated execution of the same query with different variables. Each `vars.ndjson` line must be one variables object. Batch execution is serial and continues on per-row errors by default; inspect each row's `status` before summarizing.

### 7. Retry once if the query shape is wrong

If `ot gql` returns a GraphQL error:

1. inspect a narrower schema slice or one type
2. fix the query
3. retry once

Do not repeatedly brute-force the API.

If `ot gql` returns `status=partial`, use the returned `graphql_data`, inspect the warnings, and mention the partial-result caveat in the answer.

If `ot gql` returns `status=ok`, still inspect `graphql_data` for `null` fields. GraphQL can validly return `null` for nullable fields such as a missing `target`, and that is not a CLI transport or GraphQL execution error.

## Preferred command patterns

### “Find BRCA1”

```bash
ot resolve "BRCA1" --entity target --limit 5
```

### Association questions

Use this pattern for questions like:
- “What diseases is BRCA1 associated with?”
- “What are the top associated targets for familial ovarian cancer?”

Pattern:
- resolve the target or disease first
- query `associatedDiseases(...)` or `associatedTargets(...)`
- always include a `page` argument
- if you want association-score sorting, use `orderByScore: "score"`
- the `orderByScore` value is a field name, not a sort direction; descending is implicit
- do not use `orderByScore: "desc"`

### Disease -> drug questions

Use this pattern for questions like:
- “Show drugs linked to rheumatoid arthritis.”

Pattern:
- resolve the disease first
- query `drugAndClinicalCandidates`
- treat the field as an unpaged full rowset
- keep the user-facing preview small and say you are showing the first `N` rows after retrieval
- do not imply server-side paging or ranking unless you explicitly applied one client-side

### Evidence questions

Use this pattern for questions like:
- “What evidence supports EGFR in lung adenocarcinoma?”
- “What human genetic evidence links this target to this disease?”

Pattern:
- resolve both entities first
- if either entity is ambiguous, stop and show candidate IDs plus descriptions for user selection
- query `evidences(...)` with a small `size`
- if the user asked for genetics, causality, or human evidence, pre-filter with curated `datasourceIds` and exclude `europepmc` by default
- only include `europepmc` when the user explicitly asks for literature
- for cancer examples, `intogen`, `cancer_gene_census`, and `cancer_biomarkers` are a good starting set when they fit the question

These examples define the preferred workflow, not a complete query cookbook.

## Answering rules

When answering the user, always include:

1. a plain-English answer first
2. the exact resolved entity name and canonical ID when ID resolution was used
3. any limit, sort, or filtering assumption you introduced in the query
4. the Open Targets data release and API version
5. any ambiguity or truncation note that affected the answer

### Query-shaping language

- If you chose a limit, say so.
- If you added a sort, say what you sorted by.
- If you used API order, say that.
- If you filtered to one datasource or one evidence type, say that.
- If you used `orderByScore: "score"` on associations, say you sorted by association score.

### Terminology rules

- Distinguish **association scores** from **evidence items**.
- Do not claim “top” or “best” unless you explicitly chose and stated a ranking criterion.
- Do not hide canonical IDs when you used resolution.

## Limits and truncation

Keep default limits small unless the user asks for more.

Recommended defaults:

- `resolve`: 5
- list-style GraphQL previews: 10
- evidence rows: 10

If you truncate results, say so.

## Out-of-scope behavior

Do not use this skill for:

- write operations
- non-Open-Targets tasks

## Failure handling

### If `ot` is missing

Say:

> This workspace does not have the `ot` CLI installed, so I cannot use the Open Targets CLI skill here.

### If the CLI returns `not_found`

Say what term or ID you tried and suggest trying a more specific synonym.

### If the CLI returns `ambiguous`

Show the top candidates with IDs and ask the user to choose unless the CLI already returned a deterministic winner.

### If `ot gql` returns an error

Inspect a narrower schema slice or one type, fix the query, and retry once.

## Minimal response template

Use this shape unless the user asked for raw JSON:

```text
Summary: <plain-English answer>

Resolved:
- <entity name> (<canonical ID>) [only when resolution was used]

Method:
- CLI path: <tools/describe/meta/resolve/schema/type/gql sequence>
- Query assumptions: <limit / sort / filter choices>

Open Targets:
- Data release: <release>
- API version: <version>

Notes:
- <ambiguity / truncation / errors retried if any>
```

## Do not do these things

- do not guess IDs silently
- do not skip `resolve` when the user gave a name and ambiguity matters
- do not call raw HTTP or `curl` first when `ot` is available
- do not switch to a different data-access workflow automatically
- do not dump the full schema when a category or one type is enough
- do not claim completeness from a preview query
