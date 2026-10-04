"""Browsing the mushaf: the surah index and the verses of one surah, each verse marked
when AFAQ has something on it beyond tafsir (a curated scientific comparison, or
secondary i'jaz articles), so the reader can see where to look before opening it."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func

from .db import SessionLocal
from .models import ArticleVerse, Verse, VersePhrase

router = APIRouter(tags=["quran"])


def _flags(db, verse_ids: list[int]) -> tuple[set[int], dict[int, int]]:
    curated = {vid for (vid,) in db.query(VersePhrase.verse_id).filter(VersePhrase.verse_id.in_(verse_ids)).distinct()}
    ijaz = dict(db.query(ArticleVerse.verse_id, func.count()).filter(ArticleVerse.verse_id.in_(verse_ids))
                .group_by(ArticleVerse.verse_id).all())
    return curated, ijaz


@router.get("/surahs")
def surahs():
    db = SessionLocal()
    try:
        rows = (db.query(Verse.surah_number, func.min(Verse.surah_name), func.count(Verse.id))
                .filter(Verse.reading == "hafs").group_by(Verse.surah_number).order_by(Verse.surah_number).all())
        curated = dict(db.query(Verse.surah_number, func.count(func.distinct(VersePhrase.verse_id)))
                       .join(VersePhrase, VersePhrase.verse_id == Verse.id).group_by(Verse.surah_number).all())
        ijaz = dict(db.query(Verse.surah_number, func.count(func.distinct(ArticleVerse.verse_id)))
                    .join(ArticleVerse, ArticleVerse.verse_id == Verse.id).group_by(Verse.surah_number).all())
        return {"surahs": [{"number": n, "name": name, "ayah_count": count,
                            "curated_ayahs": curated.get(n, 0), "ijaz_ayahs": ijaz.get(n, 0)}
                           for n, name, count in rows]}
    finally:
        db.close()


@router.get("/surah/{surah_number}")
def surah(surah_number: int):
    db = SessionLocal()
    try:
        verses = (db.query(Verse).filter_by(surah_number=surah_number, reading="hafs")
                  .order_by(Verse.ayah_number).all())
        if not verses:
            raise HTTPException(404, "لم يتم العثور على هذه السورة في المصادر المعتمدة المستوعبة حتى الآن.")
        curated, ijaz = _flags(db, [v.id for v in verses])
        return {"number": surah_number, "name": verses[0].surah_name, "verses": [
            {"ayah_number": v.ayah_number, "text": v.arabic_text, "page_number": v.page_number,
             "juz_number": v.juz_number, "curated": v.id in curated, "ijaz_articles": ijaz.get(v.id, 0)}
            for v in verses]}
    finally:
        db.close()
