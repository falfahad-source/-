"""Ingest tafsir text for a surah from the tafsir books Quranpedia lists per ayah.

Book availability is listed per ayah (/ayah/{s}/{a}/tafsir); by default only the
books Quranpedia flags as `fundamental` are ingested (see select_books).

This is the stand-in tafsir pipeline for Phase 1 while the Dorar.net access
mechanism is still being confirmed (see docs/SOURCE_FINDINGS.md). Each tafsir
book becomes its own Source row (author + title preserved), so disagreement
between books is preserved rather than merged (spec: "Disagreement" section).

Usage:
    python -m app.ingestion.ingest_tafsir --surah 1
    python -m app.ingestion.ingest_tafsir --surah 1 --books 3,2012
"""
from __future__ import annotations

import argparse
import datetime as dt

from sqlalchemy.orm import Session

from ..config import EXCLUDED_DEFAULT_TAFSIR_BOOKS, QURANPEDIA_API_BASE
from ..db import SessionLocal, init_db
from ..models import Source, TafsirEntry, Verse
from ..trust import TrustCategory, require_provenance
from .quranpedia_client import QuranpediaClient


def get_or_create_book_source(db: Session, book: dict) -> Source:
    url = f"{QURANPEDIA_API_BASE}/book/{book['id']}"
    # Keyed on the book id alone: a book's source_type may be refined later
    # (e.g. "e3rab_book"), and it must still resolve to the same row.
    existing = db.query(Source).filter_by(citation_identifier=f"quranpedia:book:{book['id']}").first()
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


def select_books(listing: list[dict], book_ids: set[int] | None) -> list[dict]:
    """Explicit book ids win; otherwise only the `fundamental` books. Fetching all
    ~120 books per ayah would exhaust the API's 10,000/day quota on one long surah."""
    if book_ids:
        return [b for b in listing if b["id"] in book_ids]
    return [b for b in listing if b.get("fundamental") and b["id"] not in EXCLUDED_DEFAULT_TAFSIR_BOOKS]


def ingest_surah_tafsir(
    db: Session, client: QuranpediaClient, surah_id: int, book_ids: set[int] | None = None
) -> int:
    verses = db.query(Verse).filter_by(surah_number=surah_id, reading="hafs").order_by(Verse.ayah_number)
    inserted = 0
    for verse in verses:
        ayah_number = verse.ayah_number
        for book in select_books(client.list_ayah_tafsir_books(surah_id, ayah_number), book_ids):
            source = get_or_create_book_source(db, book)
            require_provenance(source.id, "TafsirEntry")
            exists = (
                db.query(TafsirEntry)
                .filter_by(verse_id=verse.id, source_id=source.id)
                .first()
            )
            if exists:
                continue
            content = client.get_tafsir_for_ayah(surah_id, ayah_number, book["id"])
            parts = content.get("content") or []
            if not parts:
                continue  # no tafsir text for this ayah in this book — do not invent one
            text = "\n".join(p.get("text", "") for p in parts)
            page = parts[0].get("page")
            db.add(
                TafsirEntry(
                    verse_id=verse.id,
                    source_id=source.id,
                    scholar=book.get("author"),
                    category="verse_tafsir",
                    original_text=text,  # verbatim from the book, never invented
                    normalized_summary=None,
                    source_location=str(page) if page is not None else None,
                    disagreement_group=f"surah{surah_id}:ayah{ayah_number}",
                )
            )
            inserted += 1
    db.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest tafsir text from Quranpedia tafsir books.")
    parser.add_argument("--surah", type=int, required=True)
    parser.add_argument(
        "--books", type=str, default=None,
        help="Comma-separated Quranpedia book ids (e.g. 3,2012). Default: fundamental tafsirs only.",
    )
    args = parser.parse_args()
    book_ids = {int(b) for b in args.books.split(",")} if args.books else None

    init_db()
    db = SessionLocal()
    client = QuranpediaClient()
    try:
        n = ingest_surah_tafsir(db, client, args.surah, book_ids)
        print(f"Inserted {n} new tafsir entries for surah {args.surah}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
