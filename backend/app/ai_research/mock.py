"""Test-mode report. It has the exact structure of a real one (schema.py), so the page can be
checked end to end, but every finding is a placeholder: test mode must never put a
scientific claim, a tafsir attribution or a citation in front of a user."""

PLACEHOLDER = "_[يملؤه الباحث الآلي عند ربط المنصة]_"


def mock_data(verse: dict) -> dict:
    p = PLACEHOLDER
    return {
        "verse_reference": f"سورة {verse['surah_name']}، الآية {verse['ayah_number']}",
        "scientific_topic": p, "potential_claim": p, "related_text": p, "link_kind": None,
        "quranic_context": p, "key_words": [{"word": "[كلمة]", "meaning": p, "source_ids": ["Q1"]}],
        "interpretive_boundaries": p, "alternative_readings": [p],
        "scientific_background": p, "scientific_consensus": None, "consensus_note": "",
        "historical_background": p, "known_before_revelation": None, "comparison": p,
        "supporting_evidence": [{"point": p, "source_ids": ["S1"]}],
        "counter_evidence": [{"point": p, "source_ids": ["S2"]}],
        "alternative_explanations": [p], "critical_analysis": [{"issue": "other", "note": p}],
        "scientific_claim_assessment": {"verdict": None, "reason": p},
        "correspondence_assessment": {"verdict": None, "reason": p},
        "confidence_level": None, "final_assessment": p, "hypotheses": [], "research_gaps": [],
        "quranic_sources": [], "scientific_sources": [], "checks": None,
    }
