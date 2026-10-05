"""Browsing the mushaf: the surah index, the verses of one surah, and the mushaf page by page
(KFGQPC's page numbers, the Madinah mushaf's 604 pages). Each verse is marked
when AFAQ has something on it beyond tafsir (a curated scientific comparison, or
secondary i'jaz articles), so the reader can see where to look before opening it."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from sqlalchemy import func

from .cache import cached_json
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
    return cached_json("surahs", _surahs, max_age=3600)


def _surahs():
    db = SessionLocal()
    try:
        rows = (db.query(Verse.surah_number, func.min(Verse.surah_name), func.count(Verse.id), func.min(Verse.page_number))
                .filter(Verse.reading == "hafs").group_by(Verse.surah_number).order_by(Verse.surah_number).all())
        curated = dict(db.query(Verse.surah_number, func.count(func.distinct(VersePhrase.verse_id)))
                       .join(VersePhrase, VersePhrase.verse_id == Verse.id).group_by(Verse.surah_number).all())
        ijaz = dict(db.query(Verse.surah_number, func.count(func.distinct(ArticleVerse.verse_id)))
                    .join(ArticleVerse, ArticleVerse.verse_id == Verse.id).group_by(Verse.surah_number).all())
        juz = dict(db.query(Verse.juz_number, func.min(Verse.page_number)).filter(Verse.reading == "hafs",
                   Verse.juz_number.isnot(None)).group_by(Verse.juz_number).all())
        return {"juz_pages": {str(j): p for j, p in sorted(juz.items())},
                "surahs": [{"number": n, "name": name, "ayah_count": count, "start_page": page,
                            "curated_ayahs": curated.get(n, 0), "ijaz_ayahs": ijaz.get(n, 0)}
                           for n, name, count, page in rows]}
    finally:
        db.close()


@router.get("/surah/{surah_number}")
def surah(surah_number: int):
    return cached_json(f"surah:{surah_number}", lambda: _surah(surah_number), max_age=3600)


def _surah(surah_number: int):
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


_AYAH_END = re.compile(r"\s*\u06dd[\d\u0660-\u0669]*\s*$")


@router.get("/page/{page_number}")
def page(page_number: int):
    """One mushaf page: its verses in order, with the juz, and the basmala that heads each
    surah starting on it (the stored text of al-Fatiha 1:1 without its ayah-end sign; it is
    not a verse of the other surahs, so it is shown as their heading, and not over at-Tawbah)."""
    return cached_json(f"page:{page_number}", lambda: _page(page_number), max_age=3600)


def _page(page_number: int):
    db = SessionLocal()
    try:
        pages = db.query(func.max(Verse.page_number)).filter(Verse.reading == "hafs").scalar() or 0
        verses = (db.query(Verse).filter_by(page_number=page_number, reading="hafs")
                  .order_by(Verse.surah_number, Verse.ayah_number).all())
        if not verses:
            raise HTTPException(404, f"لا توجد الصفحة {page_number} في المصحف (من 1 إلى {pages}).")
        first = db.query(Verse).filter_by(surah_number=1, ayah_number=1, reading="hafs").one_or_none()
        curated, ijaz = _flags(db, [v.id for v in verses])
        return {"page": page_number, "pages": pages,
                "juz": sorted({v.juz_number for v in verses if v.juz_number}),
                "basmala": _AYAH_END.sub("", first.arabic_text) if first else None,
                "verses": [{"surah_number": v.surah_number, "surah_name": v.surah_name, "ayah_number": v.ayah_number,
                            "text": v.arabic_text, "juz_number": v.juz_number, "curated": v.id in curated,
                            "ijaz_articles": ijaz.get(v.id, 0)} for v in verses]}
    finally:
        db.close()
