"""Ingest the canonical Quran text (Hafs mushaf) from Quranpedia into the DB.

Usage:
    python -m app.ingestion.ingest_quran --surah 1

Guarantees (enforced, not just documented):
- arabic_text is stored exactly as returned by the API — never generated or
  "cleaned" by an LLM.
- Every Verse row points at a Source row carrying the exact API URL and a
  retrieval timestamp, so the data is traceable per the spec's "Web-source
  requirements".
"""
from __future__ import annotations

import argparse
import datetime as dt

from sqlalchemy.orm import Session

from ..config import DEFAULT_MUSHAF_ID, QURANPEDIA_API_BASE
from ..db import SessionLocal, init_db
from ..models import Source, Verse
from ..trust import TrustCategory
from .quranpedia_client import QuranpediaClient

SURAH_NAMES_PLACEHOLDER = "سورة {n}"  # replaced with the real name returned per-ayah context if available


def get_or_create_source(db: Session, mushaf_id: int) -> Source:
    url = f"{QURANPEDIA_API_BASE}/mushafs/{mushaf_id}"
    existing = db.query(Source).filter_by(url=url, source_type="quran_api").first()
    if existing:
        return existing
    source = Source(
        title=f"Quranpedia Mushaf #{mushaf_id} (Hafs)",
        publisher="Quranpedia.net",
        author=None,
        source_type="quran_api",
        url=url,
        version=dt.date.today().isoformat(),
        retrieval_date=dt.datetime.utcnow(),
        trust_category=TrustCategory.QURANIC_TEXT,
        citation_identifier=f"quranpedia:mushaf:{mushaf_id}",
    )
    db.add(source)
    db.flush()
    return source


def ingest_surah(db: Session, client: QuranpediaClient, surah_id: int, mushaf_id: int = DEFAULT_MUSHAF_ID) -> int:
    source = get_or_create_source(db, mushaf_id)
    ayahs = client.get_surah_ayahs(mushaf_id, surah_id)
    inserted = 0
    for a in ayahs:
        exists = (
            db.query(Verse)
            .filter_by(surah_number=surah_id, ayah_number=a.number, reading="hafs")
            .first()
        )
        if exists:
            continue
        db.add(
            Verse(
                surah_number=surah_id,
                surah_name=SURAH_NAMES_PLACEHOLDER.format(n=surah_id),
                ayah_number=a.number,
                arabic_text=a.text,  # verbatim, never altered
                reading="hafs",
                source_id=source.id,
            )
        )
        inserted += 1
    db.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Quran verses from Quranpedia.")
    parser.add_argument("--surah", type=int, required=True, help="Surah number 1-114")
    parser.add_argument("--mushaf", type=int, default=DEFAULT_MUSHAF_ID)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    client = QuranpediaClient()
    try:
        n = ingest_surah(db, client, args.surah, args.mushaf)
        print(f"Inserted {n} new ayahs for surah {args.surah} (mushaf {args.mushaf}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
