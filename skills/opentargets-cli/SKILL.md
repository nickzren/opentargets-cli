---
name: opentargets-cli
version: 0.1.0
description: Use for read-only Open Targets Platform questions when the local `ot` CLI is available - ID resolution, schema inspection, and custom GraphQL queries. Not for write operations or non-Open-Targets tasks.
---

# Open Targets CLI skill

This skill assumes a local `ot` command is available on `PATH`.

## Core rule

Use the CLI first. Do not start with raw `curl` or direct HTTP, or switch to a different data-access workflow, unless the user explicitly asks or the CLI is unavailable.

This skill is **read-only**. If `ot` is missing, say: "This workspace does not have the `ot` CLI installed, so I cannot use the Open Targets CLI skill here."

The CLI is a small primitive surface: setup diagnosis, command discovery, ID resolution, schema inspection, GraphQL execution, and release provenance. You do the planning; do not expect high-level domain commands.

## Workflow

### 1. Discover only what you need

Use the commands in this skill directly. Run `ot describe <command>` only when you need a command contract you do not know, `ot tools` only when you need the command list, and `ot doctor` only when a command fails in a way that suggests setup problems. Reuse what you learn within the session.

### 2. Capture provenance when reporting data

Before the first answer that reports Open Targets data, run `ot meta` once per session for the data release and API version, and reuse it.

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

Keep answers proportional to the question. Lead with the plain-English answer, then include only what applies:

- the resolved entity name and canonical ID when resolution was used
- the Open Targets data release when reporting data
- any limit, sort, or filter you introduced
- any ambiguity, partial result, or truncation that affected the answer

State each limit, sort (including API order or association score), and datasource or evidence-type filter you applied. Distinguish **association scores** from **evidence items**. Do not claim “top” or “best” without a stated ranking criterion, and do not claim completeness from a preview query.

## Limits and truncation

Keep default limits small unless the user asks for more.

Recommended defaults:

- `resolve`: 5
- list-style GraphQL previews: 10
- evidence rows: 10

If you truncate results, say so.
