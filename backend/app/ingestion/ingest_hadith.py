"""Store Dorar.net hadith search results against a verse.

Usage (from a network Dorar's Cloudflare does not block):
    python -m app.ingestion.ingest_hadith --surah 2 --ayah 43 --query "الصلاة"

The search words are chosen explicitly by the caller: picking them
automatically from the verse would be a guess, and the link would still only
be a keyword match. Every stored row is a POSSIBLE_CONNECTION with the
scholar's grade kept verbatim.
"""
from __future__ import annotations

import argparse
import datetime as dt

from sqlalchemy.orm import Session

from ..db import SessionLocal, init_db
from ..models import HadithEntry, Source, Verse
from ..trust import TrustCategory, require_provenance
from .dorar_client import DORAR_API_URL, DORAR_DOC_URL, DorarClient


def get_or_create_source(db: Session) -> Source:
    existing = db.query(Source).filter_by(citation_identifier="dorar:hadith_api").first()
    if existing:
        return existing
    source = Source(
        title="الموسوعة الحديثية — الدرر السنية",
        publisher="Dorar.net",
        author=None,
        source_type="hadith_api",
        url=DORAR_DOC_URL,
        version=None,
        retrieval_date=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),  # naive UTC, matches column
        # The source itself is a hadith database; how each hadith relates to a
        # verse is carried per row (always POSSIBLE_CONNECTION).
        trust_category=TrustCategory.POSSIBLE_CONNECTION,
        citation_identifier="dorar:hadith_api",
    )
    db.add(source)
    db.flush()
    return source


def ingest_verse_hadith(db: Session, client: DorarClient, surah: int, ayah: int, query: str) -> int:
    verse = db.query(Verse).filter_by(surah_number=surah, ayah_number=ayah, reading="hafs").first()
    if verse is None:
        raise ValueError(f"verse {surah}:{ayah} is not in the database; import the Quran text first")
    query = query.strip()
    source = get_or_create_source(db)
    require_provenance(source.id, "HadithEntry")
    inserted = 0
    for h in client.search(query):
        exists = (
            db.query(HadithEntry)
            .filter_by(verse_id=verse.id, search_query=query, result_rank=h.rank)
            .first()
        )
        if exists:
            continue
        db.add(HadithEntry(
            verse_id=verse.id, source_id=source.id, search_query=query, result_rank=h.rank,
            text=h.text, narrator=h.narrator, muhaddith=h.muhaddith, book=h.book,
            reference=h.reference, grade=h.grade, raw_html=h.raw_html,
            trust_category=TrustCategory.POSSIBLE_CONNECTION,
        ))
        inserted += 1
    db.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Store Dorar.net hadith search results for a verse.")
    parser.add_argument("--surah", type=int, required=True)
    parser.add_argument("--ayah", type=int, required=True)
    parser.add_argument("--query", type=str, required=True, help="Search words sent to Dorar (skey)")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        n = ingest_verse_hadith(db, DorarClient(), args.surah, args.ayah, args.query)
        print(f"Inserted {n} hadith for {args.surah}:{args.ayah} (query: {args.query!r}, {DORAR_API_URL}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
