"""Builds the structured A-G answer format required by AFAQ_MASTER_SPEC.md
("Answer format" section), strictly from database records, together with the
layers of the AFAQ journey (see app.rag.layers): linguistic analysis, tafsir
across eras, concepts/topics, scientific knowledge and the concept map.

The LLM (if/when wired in) is only allowed to touch section D's phrasing and a
short natural-language bridge in section E — it never originates sections A, B,
C or G, and section F is generated from what's *absent*, not from a model guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import HadithEntry, Relationship, TafsirEntry, Verse
from ..trust import NO_VERIFIED_SOURCE_MESSAGE_AR, TrustCategory
from .layers import (
    TRUST_LEGEND,
    concept_graph,
    concepts_layer,
    linguistic_layer,
    tafsir_timeline,
    topics_layer,
)


@dataclass
class StructuredAnswer:
    quranic_text: str
    surah_number: int
    ayah_number: int
    surah_name: str
    page_number: int | None = None
    juz_number: int | None = None
    concepts: list[dict] = field(default_factory=list)          # key phrases with meanings + comparisons
    verified_tafsir: list[dict] = field(default_factory=list)    # ordered by author's era
    linguistic: dict = field(default_factory=dict)
    topics: list[dict] = field(default_factory=list)
    graph: dict = field(default_factory=dict)
    trust_legend: list[dict] = field(default_factory=lambda: TRUST_LEGEND)
    scientific_knowledge: list[dict] = field(default_factory=list)
    possible_connections: list[dict] = field(default_factory=list)
    hadith_matches: list[dict] = field(default_factory=list)
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
    for t in tafsir_entries:
        register_source(t.source)
    verified_tafsir = tafsir_timeline(tafsir_entries)
    linguistic = linguistic_layer(db, verse, tafsir_entries)
    topics = topics_layer(db, verse)
    phrases, scientific_knowledge, phrase_connections = concepts_layer(
        db, verse, linguistic["meanings"], linguistic["words"], register_source)
    graph = concept_graph(verse, phrases, scientific_knowledge, topics)

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

    possible_connections.extend(phrase_connections)

    # Hadith found by a keyword search for this verse: a text match only, so
    # labeled like section E and never merged into tafsir. Grade always shown.
    hadith_matches = []
    hadith_rows = (
        db.query(HadithEntry)
        .filter_by(verse_id=verse.id, trust_category=TrustCategory.POSSIBLE_CONNECTION)
        .order_by(HadithEntry.search_query, HadithEntry.result_rank)
        .all()
    )
    for h in hadith_rows:
        register_source(h.source)
        hadith_matches.append({
            "label": "نتيجة بحث نصي في الموسوعة الحديثية — ليست تفسيرًا للآية.",
            "search_query": h.search_query,
            "text": h.text, "narrator": h.narrator, "muhaddith": h.muhaddith,
            "book": h.book, "reference": h.reference, "grade": h.grade,
            "source": h.source.title,
        })

    not_established: list[str] = []
    if not verified_tafsir:
        not_established.append(
            "لا يوجد في المصادر المعتمدة حاليًا نص تفسير موثّق لهذه الآية. " + NO_VERIFIED_SOURCE_MESSAGE_AR
        )
    if not possible_connections:
        not_established.append("لا توجد مقارنة علمية موثّقة مرتبطة بهذه الآية في قاعدة البيانات حتى الآن.")
    if not phrases:
        not_established.append("لم تُعدّ خريطة مفاهيم ومعرفة علمية لهذه الآية بعد.")
    unverified = [c for s in scientific_knowledge for c in s["claims"]
                  if c["trust_category"] == TrustCategory.UNVERIFIED_CLAIM.value]
    if unverified:
        not_established.append(
            f"{len(unverified)} من المعطيات العلمية المعروضة لم تُطابَق بعد مع مصدرها الأصلي، فهي مصنفة «ادعاء غير موثق».")
    linked = {c["concept"] for c in phrase_connections}
    without = [s["name_ar"] for s in scientific_knowledge if not s["claims"] and s["concept"] in linked]
    if without:
        not_established.append("لا يوجد مصدر علمي مرتبط بعد بهذه المفاهيم: " + "، ".join(without) + ".")

    return StructuredAnswer(
        quranic_text=verse.arabic_text,
        surah_number=verse.surah_number,
        ayah_number=verse.ayah_number,
        surah_name=verse.surah_name,
        page_number=verse.page_number,
        juz_number=verse.juz_number,
        concepts=phrases,
        verified_tafsir=verified_tafsir,
        linguistic=linguistic,
        topics=topics,
        graph=graph,
        scientific_knowledge=scientific_knowledge,
        possible_connections=possible_connections,
        hadith_matches=hadith_matches,
        not_established=not_established,
        sources=list(sources_seen.values()),
    )
