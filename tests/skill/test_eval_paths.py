from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.live, pytest.mark.skill]


def run_ok(cli: Any, argv: list[str]) -> dict[str, Any]:
    exit_code, envelope = cli(argv)
    assert exit_code == 0, envelope
    assert envelope["status"] == "ok", envelope
    assert envelope["request"]["command"] == argv[0]
    return envelope


def first_candidate_id(envelope: dict[str, Any]) -> str:
    candidates = envelope["data"]["candidates"]
    assert candidates
    return candidates[0]["id"]


def test_eval_find_brca1_resolve_only(cli):
    envelope = run_ok(cli, ["resolve", "BRCA1", "--entity", "target", "--limit", "5"])
    assert first_candidate_id(envelope) == "ENSG00000012048"


def test_eval_brca1_associated_diseases_uses_resolve_schema_gql(cli):
    resolve = run_ok(cli, ["resolve", "BRCA1", "--entity", "target", "--limit", "5"])
    ensembl_id = first_candidate_id(resolve)

    schema = run_ok(cli, ["schema", "--category", "targets", "--category", "associations"])
    assert "type Target" in schema["data"]["schema_text"]
    assert "associatedDiseases" in schema["data"]["schema_text"]

    gql = run_ok(
        cli,
        [
            "gql",
            "--query",
            (
                'query Q($ensemblId: String!) { '
                'target(ensemblId: $ensemblId) { '
                'associatedDiseases(page: {index: 0, size: 5}, orderByScore: "score") { '
                "count rows { disease { id name } score } "
                "} } }"
            ),
            "--variables",
            f'{{"ensemblId":"{ensembl_id}"}}',
        ],
    )
    rows = gql["data"]["graphql_data"]["target"]["associatedDiseases"]["rows"]
    assert rows
    assert rows[0]["score"] >= rows[-1]["score"]


def test_eval_rheumatoid_arthritis_drugs_uses_resolve_schema_gql(cli):
    resolve = run_ok(cli, ["resolve", "rheumatoid arthritis", "--entity", "disease", "--limit", "5"])
    disease_id = first_candidate_id(resolve)
    assert disease_id == "EFO_0000685"

    schema = run_ok(cli, ["schema", "--category", "diseases", "--category", "drugs"])
    assert "drugAndClinicalCandidates" in schema["data"]["schema_text"]
    assert "ClinicalIndicationFromDisease" in schema["data"]["schema_text"]

    gql = run_ok(
        cli,
        [
            "gql",
            "--query",
            (
                "query Q($efoId: String!) { "
                "disease(efoId: $efoId) { "
                "id name drugAndClinicalCandidates { count } "
                "} }"
            ),
            "--variables",
            f'{{"efoId":"{disease_id}"}}',
        ],
    )
    candidates = gql["data"]["graphql_data"]["disease"]["drugAndClinicalCandidates"]
    assert candidates["count"] > 0


def test_eval_egfr_lung_adenocarcinoma_resolves_both_and_halts_on_ambiguity(cli):
    target = run_ok(cli, ["resolve", "EGFR", "--entity", "target", "--limit", "5"])
    assert first_candidate_id(target) == "ENSG00000146648"

    exit_code, disease = cli(["resolve", "lung adenocarcinoma", "--entity", "disease", "--limit", "5"])
    assert exit_code == 0
    assert disease["status"] == "ambiguous"
    assert disease["request"]["command"] == "resolve"
    candidates = disease["data"]["candidates"]
    ids = {candidate["id"] for candidate in candidates}
    assert {"EFO_0000571", "EFO_0005288"} <= ids
    assert all(candidate["description"] for candidate in candidates)


def test_eval_associated_disease_type_uses_type(cli):
    envelope = run_ok(cli, ["type", "AssociatedDisease"])
    assert envelope["data"]["requested_type"] == "AssociatedDisease"
    assert "type AssociatedDisease" in envelope["data"]["schema_text"]


def test_eval_schema_categories_uses_schema_list_categories(cli):
    envelope = run_ok(cli, ["schema", "--list-categories"])
    categories = {row["name"] for row in envelope["data"]["categories"]}
    assert {"targets", "diseases", "drugs", "associations", "evidence"} <= categories


def test_eval_describe_gql_uses_describe(cli):
    envelope = run_ok(cli, ["describe", "gql"])
    assert envelope["data"]["command"] == "gql"
    argument_names = {argument["name"] for argument in envelope["data"]["arguments"]}
    assert {"--query", "--query-file", "--variables", "--variables-file"} <= argument_names


def test_eval_direct_graphql_query_uses_gql_without_resolution(cli):
    envelope = run_ok(cli, ["gql", "--query", "query { meta { name } }"])
    assert "Open Targets" in envelope["data"]["graphql_data"]["meta"]["name"]
