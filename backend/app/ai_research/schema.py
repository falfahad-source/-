"""The JSON every research report must have (OpenAI Structured Outputs, strict mode: every
property required, nulls allowed where a value may be unknown, no extra keys).

The model fills it; report.py then checks it (source ids, links actually visited) and
renders it as the Arabic report the reader sees.
"""

CONFIDENCE = ["very_strong", "strong", "possible", "weak", "unsupported", "contradicted", "no_claim"]
CONSENSUS = ["established", "broad_consensus", "debated", "emerging", "not_supported", "not_applicable"]
KNOWN_BEFORE = ["yes", "partially", "no_evidence_found", "unclear", "not_applicable"]
LINK_KIND = ["direct", "needs_interpretation", "far_fetched", "not_applicable"]
CLAIM_VERDICT = ["supported", "partially_supported", "unsupported", "contradicted", "not_applicable"]
MATCH_VERDICT = ["precise", "general", "needs_interpretation", "far_fetched", "not_applicable"]
SOURCE_TYPE = ["peer_reviewed", "systematic_review", "institution", "academic_book", "database",
               "specialist_article", "science_journalism", "general_website", "ijaz_website"]
CRITIQUE = ["overinterpretation", "anachronism", "confirmation_bias", "selective_evidence",
            "alternative_interpretation", "alternative_scientific_explanation", "weak_scientific_evidence",
            "weak_historical_argument", "linguistic_problem", "translation_problem", "unestablished_claim", "other"]


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_str = {"type": "string"}
_nstr = {"type": ["string", "null"]}
_ids = {"type": "array", "items": _str, "description": "معرّفات المصادر: S1… أو Q1…"}
_evidence = {"type": "array", "items": _obj({"point": _str, "source_ids": _ids})}
_verdict = lambda values: _obj({"verdict": {"type": "string", "enum": values}, "reason": _str})  # noqa: E731

REPORT_SCHEMA = _obj({
    "verse_reference": _str,
    "scientific_topic": {**_nstr, "description": "الظاهرة العلمية محل الدراسة، أو null إن لم توجد"},
    "potential_claim": {**_nstr, "description": "الادعاء العلمي مصوغًا بطريقة قابلة للاختبار، أو null"},
    "related_text": {**_nstr, "description": "الجزء من الآية المرتبط بالظاهرة"},
    "link_kind": {"type": "string", "enum": LINK_KIND},
    "quranic_context": {**_str, "description": "معنى النص باختصار شديد من حزمة المصادر"},
    "key_words": {"type": "array", "items": _obj({"word": _str, "meaning": _str, "source_ids": _ids})},
    "interpretive_boundaries": {**_str, "description": "حدود ما يحتمله النص"},
    "alternative_readings": {"type": "array", "items": _str},
    "scientific_background": _str,
    "scientific_consensus": {"type": "string", "enum": CONSENSUS},
    "consensus_note": _str,
    "historical_background": _str,
    "known_before_revelation": {"type": "string", "enum": KNOWN_BEFORE},
    "comparison": _str,
    "supporting_evidence": _evidence,
    "counter_evidence": _evidence,
    "alternative_explanations": {"type": "array", "items": _str},
    "critical_analysis": {"type": "array", "items": _obj({"issue": {"type": "string", "enum": CRITIQUE}, "note": _str})},
    "scientific_claim_assessment": _verdict(CLAIM_VERDICT),
    "correspondence_assessment": _verdict(MATCH_VERDICT),
    "confidence_level": {"type": "string", "enum": CONFIDENCE},
    "final_assessment": _str,
    "hypotheses": {"type": "array", "items": _str},
    "research_gaps": {"type": "array", "items": _str},
    "quranic_sources": {"type": "array", "items": _obj({"id": _str, "used_for": _str})},
    "scientific_sources": {"type": "array", "items": _obj({
        "id": _str, "title": _str, "authors_or_institution": _nstr, "year": _nstr, "url": _str,
        "source_type": {"type": "string", "enum": SOURCE_TYPE}, "used_for": _str})},
})
