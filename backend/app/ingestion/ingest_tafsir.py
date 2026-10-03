"""Ingest tafsir text for a surah from every tafsir book Quranpedia lists for it.

This is the stand-in tafsir pipeline for Phase 1 while the Dorar.net access
mechanism is still being confirmed (see docs/SOURCE_FINDINGS.md). Each tafsir
book becomes its own Source row (author + title preserved), so disagreement
between books is preserved rather than merged (spec: "Disagreement" section).

Usage:
    python -m app.ingestion.ingest_tafsir --surah 1
"""
from __future__ import annotations

import argparse
import datetime as dt

from sqlalchemy.orm import Session

from ..config import QURANPEDIA_API_BASE
from ..db import SessionLocal, init_db
from ..models import Source, TafsirEntry, Verse
from ..trust import TrustCategory, require_provenance
from .quranpedia_client import QuranpediaClient


def get_or_create_book_source(db: Session, book: dict) -> Source:
    url = f"{QURANPEDIA_API_BASE}/book/{book['id']}"
    existing = db.query(Source).filter_by(url=url, source_type="tafsir_book").first()
    if existing:
        return existing
    source = Source(
        title=book.get("name", f"Book {book['id']}"),
        publisher="Quranpedia.net",
        author=book.get("author"),
        source_type="tafsir_book",
        url=url,
        version=dt.datetime.now(dt.timezone.utc).date().isoformat(),
        retrieval_date=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),  # naive UTC, matches column
        trust_category=TrustCategory.TAFSIR_VERIFIED,
        citation_identifier=f"quranpedia:book:{book['id']}",
    )
    db.add(source)
    db.flush()
    return source


def ingest_surah_tafsir(db: Session, client: QuranpediaClient, surah_id: int) -> int:
    books = client.list_surah_tafsir_books(surah_id)
    verses = {v.ayah_number: v for v in db.query(Verse).filter_by(surah_number=surah_id, reading="hafs")}
    inserted = 0
    for book in books:
        source = get_or_create_book_source(db, book)
        require_provenance(source.id, "TafsirEntry")
        for ayah_number, verse in verses.items():
            content = client.get_tafsir_for_ayah(surah_id, ayah_number, book["id"])
            parts = content.get("content") or []
            if not parts:
                continue  # no tafsir text for this ayah in this book — do not invent one
            exists = (
                db.query(TafsirEntry)
                .filter_by(verse_id=verse.id, source_id=source.id)
                .first()
            )
            if exists:
                continue
            text = "\n".join(p.get("text", "") for p in parts)
            db.add(
                TafsirEntry(
                    verse_id=verse.id,
                    source_id=source.id,
                    scholar=book.get("author"),
                    category="verse_tafsir",
                    original_text=text,  # verbatim from the book, never invented
                    normalized_summary=None,
                    source_location=parts[0].get("page") if parts else None,
                    disagreement_group=f"surah{surah_id}:ayah{ayah_number}",
                )
            )
            inserted += 1
    db.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest tafsir text from Quranpedia tafsir books.")
    parser.add_argument("--surah", type=int, required=True)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    client = QuranpediaClient()
    try:
        n = ingest_surah_tafsir(db, client, args.surah)
        print(f"Inserted {n} new tafsir entries for surah {args.surah}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
