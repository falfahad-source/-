from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import SessionLocal
from .rag.answer_builder import build_answer

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
