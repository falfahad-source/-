from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .db import SessionLocal
from .rag.answer_builder import build_answer
from .search import search_verses

app = FastAPI(
    title="آفاق (AFAQ) API",
    description="Source-grounded knowledge exploration around Quranic verses.",
    version="0.1.0-scaffold",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/verse/{surah_number}/{ayah_number}")
def get_verse_answer(surah_number: int, ayah_number: int):
    db = SessionLocal()
    try:
        answer = build_answer(db, surah_number, ayah_number)
        if answer is None:
            raise HTTPException(
                status_code=404,
                detail="لم يتم العثور على هذه الآية في المصادر المعتمدة المستوعبة حتى الآن.",
            )
        return answer
    finally:
        db.close()


@app.get("/search")
def search(
    q: str = Query(..., max_length=500),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Verses containing the typed fragment (diacritics and spelling variants ignored).
    Page with `offset` (e.g. a "show more" button sends offset = results shown so far)."""
    db = SessionLocal()
    try:
        return search_verses(db, q, limit, offset)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    finally:
        db.close()


@app.get("/explore")
def explore():
    """Verses that have a curated concept map, grouped by theme order of the mushaf."""
    from sqlalchemy import func

    from .models import Concept, Relationship, Verse, VersePhrase

    db = SessionLocal()
    try:
        rows = (
            db.query(Verse, func.count(VersePhrase.id))
            .join(VersePhrase, VersePhrase.verse_id == Verse.id)
            .group_by(Verse.id)
            .order_by(Verse.surah_number, Verse.ayah_number)
            .all()
        )
        out = []
        for v, _ in rows:
            prefix = f"phrase:{v.surah_number}:{v.ayah_number}:"
            keys = {r.target_entity.removeprefix("concept:")
                    for r in db.query(Relationship).filter(Relationship.source_entity.like(prefix + "%"))}
            names = [c.name_ar for c in db.query(Concept).filter(Concept.key.in_(keys)).order_by(Concept.name_ar)]
            out.append({"surah_number": v.surah_number, "ayah_number": v.ayah_number,
                        "surah_name": v.surah_name, "concepts": names})
        return {"verses": out}
    finally:
        db.close()
