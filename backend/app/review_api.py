"""HTTP endpoints for researcher review (see app.reviews)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import cache
from .db import SessionLocal
from .models import (
    Concept,
    Relationship,
    ScientificEvidence,
    Verse,
    VersePhrase,
    WordAnalysis,
    WordMeaning,
)
from .rag.layers import _claim, _headword_forms, _tokens
from .reviews import (
    DECISIONS,
    connection_key,
    effective,
    history,
    reviewer_for,
    reviewers_from_env,
    submit,
)
from .trust import TrustCategory

router = APIRouter(prefix="/review", tags=["review"])


def current_reviewer(authorization: str | None = Header(default=None)) -> str:
    reviewers = reviewers_from_env()
    if not reviewers:
        raise HTTPException(503, "لم يُعدّ أي مراجع على هذا الخادم (AFAQ_REVIEWERS).")
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    name = reviewer_for(token, reviewers)
    if name is None:
        raise HTTPException(401, "رمز المراجع غير صحيح.")
    return name


class Decision(BaseModel):
    decision: str
    comment: str | None = Field(default=None, max_length=4000)
    explanation: str | None = Field(default=None, max_length=4000)


def _comparisons(db):
    return (db.query(Relationship)
            .filter(Relationship.source_entity.like("phrase:%"),
                    Relationship.trust_category == TrustCategory.POSSIBLE_CONNECTION)
            .all())


def _item(db, rel: Relationship) -> dict:
    _, s, a, pkey = rel.source_entity.split(":", 3)
    s, a = int(s), int(a)
    verse = db.query(Verse).filter_by(surah_number=s, ayah_number=a, reading="hafs").one()
    phrase = db.query(VersePhrase).filter_by(verse_id=verse.id, key=pkey).one()
    words = {w.word_number: w.text for w in db.query(WordAnalysis).filter_by(verse_id=verse.id)}
    ptext = " ".join(words[n] for n in range(phrase.word_from, phrase.word_to + 1) if n in words)
    toks = _tokens(ptext or phrase.label)
    meanings = [{"word": m.word_text, "meaning": m.meaning, "book": m.source.title}
                for m in db.query(WordMeaning).filter_by(verse_id=verse.id) if _headword_forms(m.word_text) & toks]
    ckey = rel.target_entity.removeprefix("concept:")
    concept = db.query(Concept).filter_by(key=ckey).first()
    claims = [_claim(e) for e in db.query(ScientificEvidence).filter_by(concept_id=concept.id)] if concept else []
    eff = effective(db, rel)
    key = connection_key(rel.source_entity, rel.target_entity)
    return {
        "key": key, "status": eff.status, "explanation": eff.explanation, "curated_explanation": rel.explanation,
        "reviewed_by": eff.reviewer, "reviewed_at": eff.reviewed_at, "comment": eff.comment,
        "verse": {"surah_number": s, "ayah_number": a, "surah_name": verse.surah_name, "text": verse.arabic_text},
        "phrase": {"key": pkey, "label": phrase.label, "text": ptext, "meanings": meanings},
        "concept": {"key": ckey, "name_ar": concept.name_ar if concept else ckey,
                    "name_en": concept.name_en if concept else None, "claims": claims},
        "source": rel.evidence_source.title, "history": history(db, key),
    }


@router.get("/me")
def me(reviewer: str = Depends(current_reviewer)):
    return {"reviewer": reviewer}


@router.get("/queue")
def queue(status: str | None = Query(default=None), reviewer: str = Depends(current_reviewer)):
    if status and status not in (*DECISIONS, "draft"):
        raise HTTPException(422, "حالة غير معروفة.")
    db = SessionLocal()
    try:
        items = [_item(db, r) for r in _comparisons(db)]
        counts = {k: sum(1 for i in items if i["status"] == k) for k in ("draft", *DECISIONS)}
        if status:
            items = [i for i in items if i["status"] == status]
        items.sort(key=lambda i: (i["status"] != "draft", i["verse"]["surah_number"], i["verse"]["ayah_number"], i["key"]))
        return {"reviewer": reviewer, "counts": counts, "items": items}
    finally:
        db.close()


@router.post("/{key:path}")
def decide(key: str, body: Decision, reviewer: str = Depends(current_reviewer)):
    db = SessionLocal()
    try:
        rel = next((r for r in _comparisons(db) if connection_key(r.source_entity, r.target_entity) == key), None)
        if rel is None:
            raise HTTPException(404, "لا توجد مقارنة بهذا المفتاح.")
        try:
            submit(db, rel, reviewer, body.decision, body.comment, body.explanation)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        cache.clear()  # the verse pages show the review state
        return _item(db, rel)
    finally:
        db.close()
