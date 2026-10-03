import pytest

from app.trust import TrustCategory, TrustViolation, assert_valid_recategorization, require_provenance


def test_unverified_cannot_become_scientific_fact():
    with pytest.raises(TrustViolation):
        assert_valid_recategorization(TrustCategory.UNVERIFIED_CLAIM, TrustCategory.SCIENTIFIC_FACT)


def test_possible_connection_cannot_become_tafsir_verified():
    with pytest.raises(TrustViolation):
        assert_valid_recategorization(TrustCategory.POSSIBLE_CONNECTION, TrustCategory.TAFSIR_VERIFIED)


def test_allowed_recategorization_does_not_raise():
    # e.g. an explicit editorial correction from one verified category metadata
    # fix is not in the forbidden set.
    assert_valid_recategorization(TrustCategory.QURANIC_TEXT, TrustCategory.QURANIC_TEXT)


def test_claim_without_source_is_rejected():
    with pytest.raises(TrustViolation):
        require_provenance(None, "Claim")


def test_claim_with_source_is_accepted():
    require_provenance(42, "Claim")  # should not raise
