from __future__ import annotations

import os
import re
from dataclasses import dataclass

from opentargets_cli import __version__

DEFAULT_ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = f"ot/{__version__} (+https://github.com/nickzren/opentargets-cli)"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
AMBIGUITY_THRESHOLD = 0.95
AMBIGUITY_MARGIN = 0.2
CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class CategorySpec:
    name: str
    summary: str
    root_fields: tuple[str, ...]
    seed_types: tuple[str, ...]


CATEGORY_SPECS: dict[str, CategorySpec] = {
    "targets": CategorySpec(
        name="targets",
        summary="Target entry points and target-related types",
        root_fields=("target", "targets"),
        seed_types=("Target",),
    ),
    "diseases": CategorySpec(
        name="diseases",
        summary="Disease entry points and disease-related types",
        root_fields=("disease", "diseases"),
        seed_types=("Disease",),
    ),
    "drugs": CategorySpec(
        name="drugs",
        summary="Drug entry points and drug-related types",
        root_fields=("drug", "drugs"),
        seed_types=("Drug", "KnownDrug", "KnownDrugs", "MechanismsOfAction", "Indications"),
    ),
    "variants": CategorySpec(
        name="variants",
        summary="Variant entry points and variant-related types",
        root_fields=("variant",),
        seed_types=("Variant", "VariantAnnotation", "TranscriptConsequence"),
    ),
    "studies": CategorySpec(
        name="studies",
        summary="Study entry points and study-related types",
        root_fields=("study", "studies"),
        seed_types=("Study", "Studies", "StudyTypeEnum"),
    ),
    "credible_sets": CategorySpec(
        name="credible_sets",
        summary="Credible set entry points and credible-set-related types",
        root_fields=("credibleSet", "credibleSets"),
        seed_types=("CredibleSet", "CredibleSets", "Locus", "Loci", "StudyTypeEnum"),
    ),
    "associations": CategorySpec(
        name="associations",
        summary="Association result types and association entry points",
        root_fields=("target", "disease"),
        seed_types=("Target", "Disease", "AssociatedDisease", "AssociatedDiseases"),
    ),
    "evidence": CategorySpec(
        name="evidence",
        summary="Evidence entry points and evidence-related types",
        root_fields=("target", "disease"),
        seed_types=("Target", "Disease", "Evidence", "Evidences"),
    ),
    "meta": CategorySpec(
        name="meta",
        summary="Metadata and release provenance types",
        root_fields=("meta",),
        seed_types=("Meta", "APIVersion", "DataVersion"),
    ),
}

ENTITY_TYPES = ("target", "disease", "drug", "variant", "study", "credible_set")

TARGET_ID_PATTERN = re.compile(r"^ENSG\d{11}$")
DRUG_ID_PATTERN = re.compile(r"^CHEMBL\d+$", re.IGNORECASE)
DISEASE_ID_PATTERN = re.compile(r"^(?:EFO|MONDO|Orphanet|OTAR|HP)_[A-Za-z0-9:.+-]+$", re.IGNORECASE)
VARIANT_ID_PATTERN = re.compile(
    r"^(?:chr)?(?:[1-9]|1\d|2[0-2]|X|Y|MT|M)_\d+_[ACGT]+_[ACGT]+$",
    re.IGNORECASE,
)
STUDY_ID_PATTERN = re.compile(r"^GCST\d+$", re.IGNORECASE)

CANONICAL_ID_RULES = {
    "target": TARGET_ID_PATTERN.pattern,
    "drug": DRUG_ID_PATTERN.pattern,
    "disease": DISEASE_ID_PATTERN.pattern,
    "variant": VARIANT_ID_PATTERN.pattern,
    "study": STUDY_ID_PATTERN.pattern,
    "credible_set": None,
}


def default_endpoint() -> str:
    return os.getenv("OT_API_URL", DEFAULT_ENDPOINT)


def default_timeout() -> int:
    raw = os.getenv("OT_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


def default_user_agent() -> str:
    return os.getenv("OT_USER_AGENT", DEFAULT_USER_AGENT)
