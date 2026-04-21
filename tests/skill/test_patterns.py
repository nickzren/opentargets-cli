from __future__ import annotations

import pytest

pytestmark = [pytest.mark.live, pytest.mark.skill]


def test_association_pattern_uses_order_by_score_field_name(cli):
    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            (
                'query Q($efoId: String!) { '
                'disease(efoId: $efoId) { '
                'associatedTargets(page: {index: 0, size: 10}, orderByScore: "score") { '
                "count rows { target { approvedSymbol id } score } "
                "} } }"
            ),
            "--variables",
            '{"efoId":"MONDO_0016248"}',
        ]
    )
    assert exit_code == 0
    assert envelope["status"] == "ok"
    rows = envelope["data"]["graphql_data"]["disease"]["associatedTargets"]["rows"]
    assert len(rows) >= 3
    scores = [row["score"] for row in rows]
    assert scores == sorted(scores, reverse=True)


def test_skill_pattern_keeps_lung_adenocarcinoma_ambiguous(cli):
    exit_code, envelope = cli(["resolve", "lung adenocarcinoma", "--entity", "disease", "--limit", "5"])
    assert exit_code == 0
    assert envelope["status"] == "ambiguous"
    candidates = envelope["data"]["candidates"]
    ids = {candidate["id"] for candidate in candidates}
    assert "EFO_0000571" in ids
    assert "EFO_0005288" in ids
    for candidate in candidates:
        assert candidate["description"], f"missing description for ambiguous candidate: {candidate}"


def test_evidence_pattern_can_filter_out_literature_dominance(cli):
    exit_code, envelope = cli(
        [
            "gql",
            "--query",
            (
                "query Q($ensemblId: String!, $efoId: String!, $datasourceIds: [String!]) { "
                "target(ensemblId: $ensemblId) { "
                "evidences(efoIds: [$efoId], datasourceIds: $datasourceIds, size: 20) { "
                "count rows { datasourceId datatypeId score literature } "
                "} } }"
            ),
            "--variables",
            (
                '{"ensemblId":"ENSG00000146648","efoId":"EFO_0000571",'
                '"datasourceIds":["intogen","cancer_gene_census","cancer_biomarkers"]}'
            ),
        ]
    )
    assert exit_code == 0
    assert envelope["status"] == "ok"
    evidence = envelope["data"]["graphql_data"]["target"]["evidences"]
    assert evidence["count"] > 0
    rows = evidence["rows"]
    assert rows
    datasource_ids = {row["datasourceId"] for row in rows}
    assert "europepmc" not in datasource_ids
    assert datasource_ids <= {"intogen", "cancer_gene_census", "cancer_biomarkers"}
