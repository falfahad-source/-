"""Builds the structured A-G answer format required by AFAQ_MASTER_SPEC.md
("Answer format" section), strictly from database records.

The LLM (if/when wired in) is only allowed to touch section D's phrasing and a
short natural-language bridge in section E — it never originates sections A, B,
C or G, and section F is generated from what's *absent*, not from a model guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import Relationship, TafsirEntry, Verse
from ..trust import NO_VERIFIED_SOURCE_MESSAGE_AR, TrustCategory


@dataclass
class StructuredAnswer:
    quranic_text: str
    surah_number: int
    ayah_number: int
    surah_name: str
    page_number: int | None = None
    juz_number: int | None = None
    concepts: list[str] = field(default_factory=list)
    verified_tafsir: list[dict] = field(default_factory=list)
    scientific_knowledge: list[dict] = field(default_factory=list)
    possible_connections: list[dict] = field(default_factory=list)
    not_established: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)


def build_answer(db: Session, surah_number: int, ayah_number: int) -> StructuredAnswer | None:
    verse = (
        db.query(Verse)
        .filter_by(surah_number=surah_number, ayah_number=ayah_number, reading="hafs")
        .first()
    )
    if verse is None:
        # Spec rule: if no verified source exists, say so explicitly. We do not
        # fabricate a verse that isn't in the approved corpus.
        return None

    sources_seen: dict[int, dict] = {}

    def register_source(src) -> None:
        sources_seen[src.id] = {
            "title": src.title, "publisher": src.publisher, "url": src.url,
            "trust_category": src.trust_category.value,
        }

    register_source(verse.source)

    tafsir_entries = db.query(TafsirEntry).filter_by(verse_id=verse.id).all()
    verified_tafsir = []
    for t in tafsir_entries:
        register_source(t.source)
        verified_tafsir.append({
            "scholar": t.scholar, "category": t.category,
            "text": t.original_text, "source": t.source.title,
            "disagreement_group": t.disagreement_group,
        })

    # Relationships whose source_entity references this verse.
    entity_key = f"verse:{surah_number}:{ayah_number}"
    relationships = db.query(Relationship).filter_by(source_entity=entity_key).all()
    possible_connections = []
    for r in relationships:
        if r.trust_category != TrustCategory.POSSIBLE_CONNECTION:
            # Refuse to present anything else under this section — the label
            # must never be implied for a non-POSSIBLE_CONNECTION record.
            continue
        register_source(r.evidence_source)
        possible_connections.append({
            "label": "POSSIBLE CONNECTION — not tafsir.",
            "target": r.target_entity,
            "relationship_type": r.relationship_type,
            "confidence": r.confidence,
            "explanation": r.explanation,
            "source": r.evidence_source.title,
        })

    not_established: list[str] = []
    if not verified_tafsir:
        not_established.append(
            "لا يوجد في المصادر المعتمدة حاليًا نص تفسير موثّق لهذه الآية. " + NO_VERIFIED_SOURCE_MESSAGE_AR
        )
    if not possible_connections:
        not_established.append("لا توجد مقارنة علمية موثّقة مرتبطة بهذه الآية في قاعدة البيانات حتى الآن.")

    return StructuredAnswer(
        quranic_text=verse.arabic_text,
        surah_number=verse.surah_number,
        ayah_number=verse.ayah_number,
        surah_name=verse.surah_name,
        page_number=verse.page_number,
        juz_number=verse.juz_number,
        concepts=[],  # populated once Concept linking is implemented (Phase 2)
        verified_tafsir=verified_tafsir,
        scientific_knowledge=[],  # populated once ScientificEvidence linking is implemented (Phase 2)
        possible_connections=possible_connections,
        not_established=not_established,
        sources=list(sources_seen.values()),
    )
