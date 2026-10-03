"""Import the knowledge layers around each verse from Quranpedia's dumps.

    python -m app.ingestion.ingest_layers_dump            # everything below
    python -m app.ingestion.ingest_layers_dump --only morphology,meanings

Layers (all verbatim from their sources, provenance on every row):
- morphology : per-word root/lemma/part of speech — Quranic Arabic Corpus
               (Dr. Kais Dukes), GPL: attribution to corpus.quran.com required.
- meanings   : غريب القرآن word meanings, one Source per book.
- topics     : Quranpedia's Quranic topic index (verse <-> topic links).
- e3rab      : i'rab books (العكبري، ابن النحاس، ...), stored as TafsirEntry with
               category "e3rab". The dumps are page-based, so each ayah's entry
               holds neighbouring ayahs too; extract_ayah_passage() keeps only
               the passage for that ayah (an exact substring of the book text).
- years      : author death year (AH) on every tafsir/i'rab Source, from the
               dump indexes, so tafsir can be ordered by era.

Run ingest_kfgqpc (verses) first; ingest_tafsir_dump may run before or after.
"""
from __future__ import annotations

import argparse
import re

from sqlalchemy.orm import Session

from ..config import QURANPEDIA_API_BASE
from ..db import SessionLocal, init_db
from ..models import (
    Source,
    TafsirEntry,
    Topic,
    Verse,
    VerseTopic,
    WordAnalysis,
    WordMeaning,
)
from ..trust import TrustCategory, require_provenance
from .ingest_tafsir import get_or_create_book_source
from .ingest_tafsir_dump import download, load_gz_json

DEFAULT_E3RAB_BOOKS = [309, 318]  # العكبري (616هـ)، ابن النحاس (338هـ)


def _verse_ids(db: Session) -> dict[tuple[int, int], int]:
    ids = {(v.surah_number, v.ayah_number): v.id for v in db.query(Verse).filter_by(reading="hafs")}
    if not ids:
        raise ValueError("no verses in the database; import the Quran text first (ingest_kfgqpc)")
    return ids


def _source(db: Session, citation: str, **fields) -> Source:
    src = db.query(Source).filter_by(citation_identifier=citation).first()
    if src is None:
        src = Source(citation_identifier=citation, **fields)
        db.add(src)
        db.flush()
    return src


# ---- morphology -------------------------------------------------------------
def import_morphology(db: Session, dump: dict) -> int:
    verses = _verse_ids(db)
    src = _source(
        db, "qac:morphology",
        title="Quranic Arabic Corpus — التحليل الصرفي", publisher="Quranic Arabic Corpus (via Quranpedia.net)",
        author="Dr. Kais Dukes", source_type="linguistic_dataset", url="https://corpus.quran.com",
        version=f"quranpedia-dump:{dump.get('license', {}).get('version')}",
        trust_category=TrustCategory.TAFSIR_VERIFIED,
    )
    require_provenance(src.id, "WordAnalysis")
    done = {vid for (vid,) in db.query(WordAnalysis.verse_id).distinct()}
    n = 0
    for item in dump["data"]:
        vid = verses.get((item["surah"], item["ayah"]))
        if vid is None or vid in done:
            continue
        for w in (item.get("morphology") or {}).get("words", []):
            segs = w.get("segments") or []
            stem = next((s for s in segs if s.get("role") == "stem"), segs[0] if segs else {})
            db.add(WordAnalysis(
                verse_id=vid, source_id=src.id, word_number=w["number"], text=w["text"],
                root=stem.get("root"), lemma=stem.get("lemma"), pos=stem.get("pos"),
                description=" + ".join(s["description"] for s in segs if s.get("description")),
                translation_en=w.get("translation"),
            ))
            n += 1
    db.commit()
    return n


# ---- غريب القرآن -------------------------------------------------------------
def import_meanings(db: Session, dump: dict) -> int:
    verses = _verse_ids(db)
    done = {(vid, sid) for vid, sid in db.query(WordMeaning.verse_id, WordMeaning.source_id).distinct()}
    sources: dict[int, Source] = {}
    n = 0
    for item in dump["data"]:
        vid = verses.get((item["surah"], item["ayah"]))
        if vid is None:
            continue
        for block in item.get("meanings") or []:
            info = block["book_info"]
            src = sources.get(info["id"])
            if src is None:
                src = _source(
                    db, f"quranpedia:book:{info['id']}",
                    title=info["name"], publisher="Quranpedia.net", author=info.get("author"),
                    source_type="gharib_book", url=f"{QURANPEDIA_API_BASE}/book/{info['id']}",
                    version=f"dump:{dump.get('license', {}).get('version')}",
                    trust_category=TrustCategory.TAFSIR_VERIFIED,
                )
                sources[info["id"]] = src
            if (vid, src.id) in done:
                continue
            for w in block.get("words") or []:
                if w.get("text") and w.get("meaning"):
                    db.add(WordMeaning(verse_id=vid, source_id=src.id, word_text=w["text"], meaning=w["meaning"]))
                    n += 1
            done.add((vid, src.id))
    db.commit()
    return n


# ---- topics -----------------------------------------------------------------
def import_topics(db: Session, dump: dict) -> int:
    verses = _verse_ids(db)
    src = _source(
        db, "quranpedia:topics", title="الموضوعات القرآنية", publisher="Quranpedia.net", author=None,
        source_type="topic_index", url=f"{QURANPEDIA_API_BASE}/topics",
        version=f"dump:{dump.get('license', {}).get('version')}", trust_category=TrustCategory.TAFSIR_VERIFIED,
    )
    topics = {t.id for t in db.query(Topic)}
    links = {(vid, tid) for vid, tid in db.query(VerseTopic.verse_id, VerseTopic.topic_id)}
    n = 0
    for item in dump["data"]:
        vid = verses.get((item["surah"], item["ayah"]))
        if vid is None:
            continue
        for t in item.get("topics") or []:
            if t["id"] not in topics:
                db.add(Topic(id=t["id"], name=t["name"], parent_name=(t.get("parent") or {}).get("name"),
                             source_id=src.id))
                topics.add(t["id"])
            if (vid, t["id"]) not in links:
                db.add(VerseTopic(verse_id=vid, topic_id=t["id"]))
                links.add((vid, t["id"]))
                n += 1
    db.commit()
    return n


# ---- إعراب --------------------------------------------------------------------
def _plain(html_text: str) -> str:
    t = re.sub(r"<br\s*/?>|</?p[^>]*>", "\n", html_text)
    t = re.sub(r"<[^>]+>", "", t).replace("\r", "")
    return re.sub(r"[ \t]*\n\s*", "\n", t).strip()


_ENDS_WITH_AYAH_NO = re.compile(r"\(([٠-٩]+)\)[)\].\s]*$")
_TO_LATIN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def extract_ayah_passage(text: str, ayah: int) -> str | None:
    """The lines of a page chunk that discuss `ayah`: from the line quoting it up
    to the line quoting a later ayah. A quoted ayah is a line ending in its
    number, e.g. "... مِنْ نُورٍ (٤٠))." — numbers elsewhere in a line are
    footnote marks, not ayahs. Returns None when the ayah's quote is absent, so
    callers can keep the full chunk."""
    lines = text.split("\n")

    def quoted(line: str) -> int | None:
        m = _ENDS_WITH_AYAH_NO.search(line)
        return int(m.group(1).translate(_TO_LATIN)) if m else None

    start = next((i for i, line in enumerate(lines) if quoted(line) == ayah), None)
    if start is None:
        return None
    end = next(
        (i for i in range(start + 1, len(lines))
         if (quoted(lines[i]) or 0) > ayah or lines[i].startswith("[سورة")),
        len(lines),
    )
    passage = "\n".join(lines[start:end]).strip()
    return passage or None


def import_e3rab_book(db: Session, dump: dict, year: int | None = None) -> int:
    verses = _verse_ids(db)
    book = dump["book"]
    author = book.get("author")
    src = get_or_create_book_source(db, {
        "id": book["id"], "name": book.get("name"),
        "author": author.get("ar_name") if isinstance(author, dict) else author,
    })
    src.source_type = "e3rab_book"
    src.version = f"dump:{dump.get('license', {}).get('version')}"
    if year:
        src.author_year = year
    done = {vid for (vid,) in db.query(TafsirEntry.verse_id).filter_by(source_id=src.id)}
    n = 0
    for item in dump["ayahs"]:
        vid = verses.get((item["surah"], item["ayah"]))
        parts = item.get("content") or []
        if vid is None or not parts or vid in done:
            continue
        chunk = _plain("\n".join(p.get("text", "") for p in parts))
        passage = extract_ayah_passage(chunk, item["ayah"])
        db.add(TafsirEntry(
            verse_id=vid, source_id=src.id, scholar=src.author, category="e3rab",
            original_text=passage or chunk, is_excerpt=passage is not None, source_location=str(parts[0].get("page")) if parts[0].get("page") else None,
            disagreement_group=f"surah{item['surah']}:ayah{item['ayah']}",
        ))
        done.add(vid)
        n += 1
    db.commit()
    return n


# ---- years --------------------------------------------------------------------
def book_years(index: dict, key: str) -> dict[int, int]:
    years: dict[int, int] = {}
    for entry in index["data"]:
        for b in entry.get(key) or []:
            if b.get("year"):
                years.setdefault(b["id"], int(b["year"]))
    return years


def apply_years(db: Session, years: dict[int, int]) -> int:
    n = 0
    for src in db.query(Source).filter(Source.citation_identifier.like("quranpedia:book:%")):
        y = years.get(int(src.citation_identifier.rsplit(":", 1)[1]))
        if y and src.author_year != y:
            src.author_year = y
            n += 1
    db.commit()
    return n


LAYERS = ("years", "morphology", "meanings", "topics", "e3rab")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import verse knowledge layers from Quranpedia dumps.")
    parser.add_argument("--only", type=str, default=None, help=f"comma-separated subset of {','.join(LAYERS)}")
    parser.add_argument("--e3rab-books", type=str, default=",".join(map(str, DEFAULT_E3RAB_BOOKS)))
    args = parser.parse_args()
    layers = args.only.split(",") if args.only else list(LAYERS)

    init_db()
    db = SessionLocal()
    try:
        e3rab_years = book_years(load_gz_json(download("e3rab.json.gz")), "e3rab") if "e3rab" in layers else {}
        if "morphology" in layers:
            print("morphology words:", import_morphology(db, load_gz_json(download("morphology.json.gz"))))
        if "meanings" in layers:
            print("word meanings:", import_meanings(db, load_gz_json(download("meanings.json.gz"))))
        if "topics" in layers:
            print("verse-topic links:", import_topics(db, load_gz_json(download("topics.json.gz"))))
        if "e3rab" in layers:
            for b in (int(x) for x in args.e3rab_books.split(",")):
                d = load_gz_json(download(f"e3rab-book-{b}.json.gz"))
                print(f"e3rab book {b} ({d['book'].get('name')}):", import_e3rab_book(db, d, e3rab_years.get(b)))
        if "years" in layers:
            years = book_years(load_gz_json(download("tafsir.json.gz")), "tafsir")
            years.update(book_years(load_gz_json(download("e3rab.json.gz")), "e3rab"))
            print("sources given a death year:", apply_years(db, years))
    finally:
        db.close()


if __name__ == "__main__":
    main()
