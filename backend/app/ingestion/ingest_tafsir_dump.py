"""Import whole tafsir books from Quranpedia's official data dumps.

Quranpedia's usage policy forbids bulk crawling of the API and points bulk
users to https://api.quranpedia.net/dumps instead. Each tafsir book is one
file, tafsir-book-{id}.json.gz, holding the book's text for all 6236 ayahs in
the same shape as /v1/ayah/{s}/{a}/book/{id}. One download per book replaces
~6,000 API calls (the API allows 10,000/day).

License (dumps/LICENSE.md): free to use inside apps without attribution;
republishing the data as a downloadable dataset requires crediting
Quranpedia.net and the dump version.

Usage:
    python -m app.ingestion.ingest_tafsir_dump                 # the `fundamental` books
    python -m app.ingestion.ingest_tafsir_dump --books 3,2012  # specific book ids
    python -m app.ingestion.ingest_tafsir_dump --remove 331    # delete a book's stored entries

Downloads are cached in backend/data/quranpedia/ (not in git). Verses must be
imported first (ingest_kfgqpc); ayahs are matched by surah/ayah number.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from ..config import EXCLUDED_DEFAULT_TAFSIR_BOOKS
from ..db import SessionLocal, init_db
from ..models import Source, TafsirEntry, Verse
from ..trust import require_provenance
from .ingest_tafsir import get_or_create_book_source

DUMPS_BASE = "https://api.quranpedia.net/dumps"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "quranpedia"


def download(name: str, cache_dir: Path = CACHE_DIR, session: requests.Session | None = None) -> Path:
    """Fetch a dump file once; later runs reuse the cached copy."""
    path = cache_dir / name
    if path.exists():
        return path
    cache_dir.mkdir(parents=True, exist_ok=True)
    resp = (session or requests).get(f"{DUMPS_BASE}/{name}", timeout=300)
    resp.raise_for_status()
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(resp.content)
    tmp.rename(path)  # never leave a truncated file under the real name
    return path


def load_gz_json(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def fundamental_book_ids(index: dict) -> list[int]:
    """Books Quranpedia flags `fundamental` on any ayah, from tafsir.json.gz,
    minus EXCLUDED_DEFAULT_TAFSIR_BOOKS."""
    ids: dict[int, None] = {}
    for entry in index["data"]:
        for book in entry["tafsir"]:
            if book.get("fundamental") and book["id"] not in EXCLUDED_DEFAULT_TAFSIR_BOOKS:
                ids.setdefault(book["id"], None)
    return list(ids)


def import_book(db: Session, dump: dict) -> int:
    """Insert one book dump's tafsir entries; returns how many were new."""
    book = dump["book"]
    author = book.get("author")
    source = get_or_create_book_source(db, {
        "id": book["id"],
        "name": book.get("name"),
        "author": author.get("ar_name") if isinstance(author, dict) else author,
    })
    require_provenance(source.id, "TafsirEntry")
    dump_version = dump.get("license", {}).get("version")
    if dump_version:
        source.version = f"dump:{dump_version}"

    verses = {(v.surah_number, v.ayah_number): v.id for v in db.query(Verse).filter_by(reading="hafs")}
    if not verses:
        raise ValueError("no verses in the database; import the Quran text first (ingest_kfgqpc)")
    already = {vid for (vid,) in db.query(TafsirEntry.verse_id).filter_by(source_id=source.id)}

    inserted = 0
    for item in dump["ayahs"]:
        verse_id = verses.get((item["surah"], item["ayah"]))
        parts = item.get("content") or []
        if verse_id is None or not parts or verse_id in already:
            continue  # unknown ayah, no text in this book (never invent one), or already imported
        page = parts[0].get("page")
        db.add(TafsirEntry(
            verse_id=verse_id,
            source_id=source.id,
            scholar=source.author,
            category="verse_tafsir",
            original_text="\n".join(p.get("text", "") for p in parts),  # verbatim from the book
            normalized_summary=None,
            source_location=str(page) if page is not None else None,
            disagreement_group=f"surah{item['surah']}:ayah{item['ayah']}",
        ))
        already.add(verse_id)
        inserted += 1
    db.commit()
    return inserted


def remove_book(db: Session, book_id: int) -> int:
    """Delete a book's tafsir entries and its Source row; returns entries deleted."""
    source = db.query(Source).filter_by(citation_identifier=f"quranpedia:book:{book_id}").first()
    if source is None:
        return 0
    n = db.query(TafsirEntry).filter_by(source_id=source.id).delete()
    db.delete(source)
    db.commit()
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Import tafsir books from Quranpedia dumps.")
    parser.add_argument("--books", type=str, default=None,
                        help="Comma-separated book ids (e.g. 3,2012). Default: fundamental books.")
    parser.add_argument("--remove", type=str, default=None,
                        help="Comma-separated book ids whose stored tafsir entries should be deleted.")
    args = parser.parse_args()

    if args.remove:
        init_db()
        db = SessionLocal()
        try:
            for book_id in (int(b) for b in args.remove.split(",")):
                print(f"book {book_id}: removed {remove_book(db, book_id)} entries")
        finally:
            db.close()
        return

    if args.books:
        book_ids = [int(b) for b in args.books.split(",")]
    else:
        book_ids = fundamental_book_ids(load_gz_json(download("tafsir.json.gz")))

    init_db()
    db = SessionLocal()
    try:
        for book_id in book_ids:
            dump = load_gz_json(download(f"tafsir-book-{book_id}.json.gz"))
            n = import_book(db, dump)
            print(f"book {book_id} ({dump['book'].get('name')}): {n} new entries, "
                  f"dump version {dump.get('license', {}).get('version')}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
