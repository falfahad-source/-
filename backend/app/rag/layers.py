"""The knowledge layers around a verse, in the order of the AFAQ journey:
linguistic analysis -> tafsir across eras -> concepts and topics -> scientific
knowledge, plus the concept map that links them. Everything here is read from
stored records; nothing is generated.
"""
from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import CONTEMPORARY_TAFSIR_BOOKS
from ..models import (
    ArticleVerse,
    Concept,
    CuratedTopic,
    Relationship,
    ScientificEvidence,
    TafsirEntry,
    Verse,
    VersePhrase,
    VerseTopic,
    WordAnalysis,
    WordMeaning,
)
from ..reviews import effective as effective_review
from ..search import normalize_arabic
from ..trust import TrustCategory

QAC_ATTRIBUTION = "التحليل الصرفي: Quranic Arabic Corpus — د. كايس دوكس رحمه الله (corpus.quran.com)، برخصة GNU GPL."

_ORDINALS = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن",
             "التاسع", "العاشر", "الحادي عشر", "الثاني عشر", "الثالث عشر", "الرابع عشر", "الخامس عشر"]


def era_of(year: int | None, book_id: int | None) -> dict:
    """Century and era group for an author's death year (AH)."""
    if year:
        century = (year - 1) // 100 + 1
        if year <= 500:
            group = "المتقدمون"
        elif year <= 900:
            group = "المتوسطون"
        elif year <= 1300:
            group = "المتأخرون"
        else:
            group = "المعاصرون"
        label = f"القرن {_ORDINALS[century - 1]} الهجري" if century <= len(_ORDINALS) else f"القرن {century} الهجري"
        return {"year": year, "century": century, "century_label": label, "era": group}
    if book_id in CONTEMPORARY_TAFSIR_BOOKS:
        return {"year": None, "century": None, "century_label": "معاصر", "era": "المعاصرون"}
    return {"year": None, "century": None, "century_label": "غير محدد", "era": "غير محدد"}


def _book_id(src) -> int | None:
    cid = src.citation_identifier or ""
    return int(cid.rsplit(":", 1)[1]) if cid.startswith("quranpedia:book:") else None


def tafsir_timeline(entries: list[TafsirEntry]) -> list[dict]:
    """Verified tafsir ordered by the author's death year; undated contemporary
    works last. I'rab entries are not tafsir and are excluded here."""
    rows = []
    for t in entries:
        if t.category == "e3rab":
            continue
        era = era_of(t.source.author_year, _book_id(t.source))
        rows.append({
            "scholar": t.scholar, "category": t.category, "text": t.original_text,
            "source": t.source.title, "disagreement_group": t.disagreement_group,
            "page": t.source_location, "trust_category": TrustCategory.TAFSIR_VERIFIED.value, **era,
        })
    rows.sort(key=lambda r: (r["year"] is None, r["year"] or 0, r["source"]))
    return rows


def linguistic_layer(db: Session, verse: Verse, entries: list[TafsirEntry]) -> dict:
    words = db.query(WordAnalysis).filter_by(verse_id=verse.id).order_by(WordAnalysis.word_number).all()
    meanings = db.query(WordMeaning).filter_by(verse_id=verse.id).order_by(WordMeaning.id).all()
    e3rab = sorted((t for t in entries if t.category == "e3rab"),
                   key=lambda t: (t.source.author_year is None, t.source.author_year or 0))
    return {
        "words": [{"number": w.word_number, "text": w.text, "root": w.root, "lemma": w.lemma, "pos": w.pos,
                   "description": w.description, "translation_en": w.translation_en} for w in words],
        "meanings": [{"word": m.word_text, "meaning": m.meaning, "book": m.source.title, "author": m.source.author}
                     for m in meanings],
        "e3rab": [{"book": t.source.title, "author": t.scholar, **era_of(t.source.author_year, _book_id(t.source)),
                   "text": t.original_text, "is_excerpt": t.is_excerpt, "page": t.source_location}
                  for t in e3rab],
        "attribution": QAC_ATTRIBUTION if words else None,
        "trust_category": TrustCategory.TAFSIR_VERIFIED.value,
    }


def _tokens(text: str) -> set[str]:
    return {t for t in normalize_arabic(text).split() if len(t) >= 3}


def _headword_forms(word_text: str) -> set[str]:
    """The word a غريب entry explains is its first word; also try it without a
    leading و / ال / وال so «واللجي» still names «لجي»."""
    words = normalize_arabic(word_text).split()
    if not words:
        return set()
    w = words[0]
    return {w, w.removeprefix("و"), w.removeprefix("ال"), w.removeprefix("وال")}


def topics_layer(db: Session, verse: Verse, related_limit: int = 12) -> list[dict]:
    out = []
    for vt in db.query(VerseTopic).filter_by(verse_id=verse.id).all():
        others = (
            db.query(Verse.surah_number, Verse.ayah_number, Verse.surah_name)
            .join(VerseTopic, VerseTopic.verse_id == Verse.id)
            .filter(VerseTopic.topic_id == vt.topic_id, Verse.id != verse.id)
            .order_by(Verse.surah_number, Verse.ayah_number)
        )
        total = others.count()
        out.append({
            "id": vt.topic.id, "name": vt.topic.name, "parent": vt.topic.parent_name,
            "related_total": total,
            "related": [{"surah_number": s, "ayah_number": a, "surah_name": n} for s, a, n in others.limit(related_limit)],
            "source": "الموضوعات القرآنية — Quranpedia.net",
            "trust_category": TrustCategory.TAFSIR_VERIFIED.value,
        })
    return out


def _claim(e: ScientificEvidence) -> dict:
    return {
        "claim": e.claim, "trust_category": e.trust_category.value, "source": e.source.title,
        "url": e.url, "quote": e.quote, "domain": e.scientific_domain,
        "verified_at": e.verified_at.date().isoformat() if e.verified_at else None,
        "provenance_note": e.provenance_note,
    }


def concepts_layer(db: Session, verse: Verse, meanings: list[dict], words: list[dict],
                   register_source) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (phrases, scientific_knowledge, connections) for curated verses."""
    phrases = db.query(VersePhrase).filter_by(verse_id=verse.id).order_by(VersePhrase.word_from).all()
    by_number = {w["number"]: w for w in words}
    out_phrases, connections, concept_keys = [], [], []
    for p in phrases:
        phrase_words = [by_number[n]["text"] for n in range(p.word_from, p.word_to + 1) if n in by_number]
        toks = _tokens(" ".join(phrase_words) or p.label)
        rels = (db.query(Relationship)
                .filter_by(source_entity=f"phrase:{verse.surah_number}:{verse.ayah_number}:{p.key}").all())
        links = []
        for r in rels:
            if r.trust_category != TrustCategory.POSSIBLE_CONNECTION:
                continue  # never present anything else as a comparison
            review = effective_review(db, r)
            if review.status == "rejected":
                continue  # a researcher rejected this comparison
            key = r.target_entity.removeprefix("concept:")
            concept = db.query(Concept).filter_by(key=key).first()
            register_source(r.evidence_source)
            link = {
                "label": "مقارنة / ارتباط محتمل — ليست تفسيرًا.",
                "phrase": p.key, "phrase_label": p.label, "concept": key,
                "concept_name_ar": concept.name_ar if concept else key,
                "concept_name_en": concept.name_en if concept else None,
                "explanation": review.explanation, "review_status": review.status,
                "reviewed_by": review.reviewer, "reviewed_at": review.reviewed_at,
                "source": r.evidence_source.title, "trust_category": r.trust_category.value,
                "target": r.target_entity, "relationship_type": r.relationship_type, "confidence": r.confidence,
            }
            links.append(link)
            connections.append(link)
            if key not in concept_keys:
                concept_keys.append(key)
        out_phrases.append({
            "key": p.key, "label": p.label, "words": [p.word_from, p.word_to], "text": " ".join(phrase_words),
            "meanings": [m for m in meanings if _headword_forms(m["word"]) & toks],
            "connections": links,
        })
    science = []
    for key in concept_keys:
        concept = db.query(Concept).filter_by(key=key).first()
        if concept is None:
            continue
        claims = db.query(ScientificEvidence).filter_by(concept_id=concept.id).all()
        for e in claims:
            register_source(e.source)
        science.append({"concept": key, "name_ar": concept.name_ar, "name_en": concept.name_en,
                        "claims": [_claim(e) for e in claims]})
    return out_phrases, science, connections


def concept_graph(verse: Verse, phrases: list[dict], science: list[dict], topics: list[dict]) -> dict:
    """Nodes and edges for the concept map: verse at the centre, its key phrases
    and Quranic topics around it, scientific concepts beyond the phrases."""
    vid = f"verse:{verse.surah_number}:{verse.ayah_number}"
    nodes = [{"id": vid, "type": "verse", "label": f"{verse.surah_name} {verse.ayah_number}",
              "trust_category": TrustCategory.QURANIC_TEXT.value}]
    edges = []
    for p in phrases:
        pid = f"phrase:{p['key']}"
        nodes.append({"id": pid, "type": "phrase", "label": p["label"], "trust_category": TrustCategory.QURANIC_TEXT.value})
        edges.append({"from": vid, "to": pid, "type": "contains"})
    claims_by_concept = {s["concept"]: s for s in science}
    seen = set()
    for p in phrases:
        for c in p["connections"]:
            cid = f"concept:{c['concept']}"
            if cid not in seen:
                verified = any(x["trust_category"] == TrustCategory.SCIENTIFIC_FACT.value
                               for x in claims_by_concept.get(c["concept"], {}).get("claims", []))
                nodes.append({"id": cid, "type": "concept", "label": c["concept_name_ar"],
                              "label_en": c["concept_name_en"],
                              "trust_category": (TrustCategory.SCIENTIFIC_FACT if verified
                                                 else TrustCategory.UNVERIFIED_CLAIM).value,
                              "has_claims": bool(claims_by_concept.get(c["concept"], {}).get("claims"))})
                seen.add(cid)
            edges.append({"from": f"phrase:{p['key']}", "to": cid, "type": "possible_connection",
                          "trust_category": TrustCategory.POSSIBLE_CONNECTION.value})
    for t in topics:
        tid = f"topic:{t['id']}"
        nodes.append({"id": tid, "type": "topic", "label": t["name"], "related_total": t["related_total"],
                      "trust_category": TrustCategory.TAFSIR_VERIFIED.value})
        edges.append({"from": vid, "to": tid, "type": "topic"})
    return {"nodes": nodes, "edges": edges}


TRUST_LEGEND = [
    {"category": TrustCategory.QURANIC_TEXT.value, "label": "نص قرآني", "description": "الآية الكريمة بلفظها الأصلي — قطعي الثبوت."},
    {"category": TrustCategory.TAFSIR_VERIFIED.value, "label": "تفسير موثق", "description": "أقوال المفسرين وأهل اللغة بمصادرها وسياقها الأصلي."},
    {"category": TrustCategory.SCIENTIFIC_FACT.value, "label": "حقيقة علمية مثبتة", "description": "معطيات علمية طوبقت مع مصدرها الأصلي المحكَّم."},
    {"category": TrustCategory.POSSIBLE_CONNECTION.value, "label": "مقارنة / ارتباط محتمل", "description": "مقارنة يرسمها الباحث — ليست تفسيرًا شرعيًا."},
    {"category": TrustCategory.UNVERIFIED_CLAIM.value, "label": "ادعاء غير موثق", "description": "لم يُتحقق من مصدره بعد — يُتعامل معه بحذر."},
]


IJAZ_LABEL = ("قراءة إعجازية من مصدر ثانوي — ليست تفسيرًا، ولم يتحقق آفاق من معلوماتها العلمية. "
              "اقرأ المقال في موقعه وقارنه بالتفسير الموثق.")


def ijaz_articles(db: Session, verse: Verse, limit: int = 8) -> dict:
    """Secondary i'jaz articles that discuss this verse, most focused first: an
    article whose title quotes the verse, then articles about few verses."""
    links = db.query(ArticleVerse).filter_by(verse_id=verse.id).all()
    if not links:
        return {"total": 0, "articles": [], "label": IJAZ_LABEL}
    ids = [link.article_id for link in links]
    sizes = dict(db.query(ArticleVerse.article_id, func.count()).filter(ArticleVerse.article_id.in_(ids))
                 .group_by(ArticleVerse.article_id).all())
    vtext = normalize_arabic(verse.text_imlaei or verse.arabic_text)
    rows = []
    for link in links:
        a = link.article
        title_n = normalize_arabic(a.title)
        in_title = any(len(chunk) >= 8 and chunk in vtext for chunk in
                       (normalize_arabic(q) for q in _title_quotes(a.title)))
        rows.append({
            "title": a.title, "url": a.url, "published": a.published, "categories": a.categories,
            "excerpt": a.excerpt, "match_method": link.match_method, "matched_text": link.matched_text,
            "verses_in_article": sizes.get(a.id, 1), "focused": in_title or sizes.get(a.id, 1) <= 5,
            "source": a.source.title, "trust_category": TrustCategory.POSSIBLE_CONNECTION.value,
            "_rank": (not in_title, sizes.get(a.id, 1), title_n),
        })
    rows.sort(key=lambda r: r["_rank"])
    for r in rows:
        del r["_rank"]
    return {"total": len(rows), "articles": rows[:limit], "label": IJAZ_LABEL}


def _title_quotes(text: str) -> list[str]:
    return re.findall(r"[﴿“\"]([^﴾”\"]{4,200})[﴾”\"]", text)


def related_comparisons(db: Session, verse: Verse, topic_ids: list[int], limit: int = 6) -> list[dict]:
    """Curated verses whose declared comparison topics (CuratedTopic) include one of
    this verse's Quranic topics, with their concepts — a way to reach comparisons
    when this verse has none of its own. Only topics a curator declared count, so a
    broad shared topic (e.g. «الدِّين») never links unrelated comparisons."""
    if not topic_ids:
        return []
    rows = (
        db.query(CuratedTopic).filter(CuratedTopic.topic_id.in_(topic_ids), CuratedTopic.verse_id != verse.id)
        .order_by(CuratedTopic.verse_id).all()
    )
    by_verse: dict[int, list[str]] = {}
    for r in rows:
        by_verse.setdefault(r.verse_id, []).append(r.topic.name)
    out = []
    for vid, shared in list(by_verse.items())[:limit]:
        v = db.get(Verse, vid)
        keys = {r.target_entity.removeprefix("concept:") for r in db.query(Relationship)
                .filter(Relationship.source_entity.like(f"phrase:{v.surah_number}:{v.ayah_number}:%"))}
        out.append({"surah_number": v.surah_number, "ayah_number": v.ayah_number, "surah_name": v.surah_name,
                    "shared_topics": shared,
                    "concepts": [c.name_ar for c in db.query(Concept).filter(Concept.key.in_(keys))]})
    out.sort(key=lambda r: (r["surah_number"], r["ayah_number"]))
    return out
