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
