"""
Trust categories and the non-negotiable epistemic rules from AFAQ_MASTER_SPEC.md.

These are intentionally implemented as *enforced* code, not comments, so a future
change to the pipeline cannot silently violate the project's core guarantees:
- UNVERIFIED_CLAIM never silently becomes SCIENTIFIC_FACT.
- POSSIBLE_CONNECTION never silently becomes TAFSIR_VERIFIED.
- Every factual claim must have a source_id (provenance).
"""
from __future__ import annotations

from enum import Enum


class TrustCategory(str, Enum):
    QURANIC_TEXT = "QURANIC_TEXT"
    TAFSIR_VERIFIED = "TAFSIR_VERIFIED"
    SCIENTIFIC_FACT = "SCIENTIFIC_FACT"
    POSSIBLE_CONNECTION = "POSSIBLE_CONNECTION"
    UNVERIFIED_CLAIM = "UNVERIFIED_CLAIM"


# Category upgrades that are NEVER allowed to happen automatically (spec rules).
FORBIDDEN_SILENT_UPGRADES = {
    (TrustCategory.UNVERIFIED_CLAIM, TrustCategory.SCIENTIFIC_FACT),
    (TrustCategory.POSSIBLE_CONNECTION, TrustCategory.TAFSIR_VERIFIED),
    (TrustCategory.UNVERIFIED_CLAIM, TrustCategory.TAFSIR_VERIFIED),
    (TrustCategory.POSSIBLE_CONNECTION, TrustCategory.SCIENTIFIC_FACT),
}


class TrustViolation(Exception):
    """Raised whenever code attempts to violate a non-negotiable epistemic rule."""


def assert_valid_recategorization(old: TrustCategory, new: TrustCategory) -> None:
    """Call this any time a record's trust_category is changed.

    Explicit human/editorial recategorization is allowed in principle, but it must
    never happen as a side effect of retrieval, ranking, or LLM synthesis. Callers
    performing an automated pipeline step should never call this with a forbidden
    pair; if they do, that is a bug, not a policy decision, hence the raise.
    """
    if (old, new) in FORBIDDEN_SILENT_UPGRADES:
        raise TrustViolation(
            f"Refusing to silently recategorize {old.value} -> {new.value}. "
            "This upgrade is only permitted via explicit, logged editorial review, "
            "never automatically."
        )


def require_provenance(source_id: int | None, claim_type: str) -> None:
    """Every factual claim must have provenance (spec rule #8)."""
    if source_id is None:
        raise TrustViolation(
            f"Refusing to store a {claim_type} with no source_id. "
            "If no verified source exists, the system must say so explicitly "
            "instead of inventing provenance."
        )


NO_VERIFIED_SOURCE_MESSAGE_AR = "لم أتمكن من التحقق من هذا الادعاء ضمن المصادر المعتمدة."
NO_VERIFIED_SOURCE_MESSAGE_EN = "I could not verify this claim in the approved sources."
