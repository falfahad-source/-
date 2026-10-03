"""Import the full Quran text (Hafs) from the King Fahd Glorious Quran Printing
Complex (KFGQPC) data release, replacing the Quranpedia API as the canonical
Quran text source. Tafsir still comes from Quranpedia (ingest_tafsir.py).

The data file comes from https://qurancomplex.gov.sa/quran-hafs/ (package
kfgqpc_hafs_v30, file kfgqpc_hafs_v30-data/kfgqpc_hafs_v30.json). It is not
committed to the repo; place it at backend/data/kfgqpc_hafs_v30.json or pass
--file.

Usage:
    python -m app.ingestion.ingest_kfgqpc
    python -m app.ingestion.ingest_kfgqpc --file /path/to/kfgqpc_hafs_v30.json
    python -m app.ingestion.ingest_kfgqpc --replace   # overwrite verses from another source

Guarantees:
- aya_text_unicode is stored exactly as in the file (including the trailing
  end-of-ayah sign and number, e.g. "۝١"), never cleaned or regenerated.
- The file is validated as a whole (6236 ayahs, 114 surahs, contiguous ayah
  numbering) before anything is written, so a truncated or wrong file cannot
  half-populate the database.
- The Source row records the file's SHA-256, so every verse is traceable to
  the exact release it came from.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from ..db import SessionLocal, init_db
from ..models import Source, Verse
from ..trust import TrustCategory

KFGQPC_PAGE_URL = "https://qurancomplex.gov.sa/quran-hafs/"
KFGQPC_RELEASE = "kfgqpc_hafs_v30"
DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / f"{KFGQPC_RELEASE}.json"

HAFS_AYAH_COUNT = 6236
HAFS_SURAH_COUNT = 114
REQUIRED_KEYS = {"sura_no", "aya_no", "sura_name_ar", "aya_text_unicode"}


class KfgqpcDataError(ValueError):
    """The data file is not a complete, well-formed KFGQPC Hafs release."""


def load_records(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def validate_records(records: list[dict]) -> None:
    if len(records) != HAFS_AYAH_COUNT:
        raise KfgqpcDataError(f"expected {HAFS_AYAH_COUNT} ayahs, got {len(records)}")
    ayahs_by_surah: dict[int, list[int]] = defaultdict(list)
    for r in records:
        missing = REQUIRED_KEYS - r.keys()
        if missing:
            raise KfgqpcDataError(f"record {r.get('id')} is missing {sorted(missing)}")
        if not r["aya_text_unicode"].strip():
            raise KfgqpcDataError(f"empty text for {r['sura_no']}:{r['aya_no']}")
        ayahs_by_surah[r["sura_no"]].append(r["aya_no"])
    if sorted(ayahs_by_surah) != list(range(1, HAFS_SURAH_COUNT + 1)):
        raise KfgqpcDataError(f"expected surahs 1..{HAFS_SURAH_COUNT}")
    for surah, ayahs in ayahs_by_surah.items():
        if sorted(ayahs) != list(range(1, len(ayahs) + 1)):
            raise KfgqpcDataError(f"surah {surah} ayah numbers are not contiguous from 1")


def get_or_create_source(db: Session, sha256: str) -> Source:
    citation = f"kfgqpc:{KFGQPC_RELEASE}"
    existing = db.query(Source).filter_by(citation_identifier=citation).first()
    if existing:
        if existing.version != f"sha256:{sha256}":
            raise KfgqpcDataError(
                f"a different file was already imported as {citation} "
                f"({existing.version}); refusing to mix two files under one release"
            )
        return existing
    source = Source(
        title="مصحف المدينة النبوية للنشر الحاسوبي — رواية حفص (الإصدار 3.0)",
        publisher="مجمع الملك فهد لطباعة المصحف الشريف",
        author=None,
        source_type="quran_dataset",
        url=KFGQPC_PAGE_URL,
        version=f"sha256:{sha256}",
        retrieval_date=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),  # naive UTC, matches column
        trust_category=TrustCategory.QURANIC_TEXT,
        citation_identifier=citation,
    )
    db.add(source)
    db.flush()
    return source


def import_records(db: Session, records: list[dict], sha256: str, replace: bool = False) -> dict[str, int]:
    """Returns counts: inserted, replaced, unchanged, skipped (owned by another
    source and replace=False)."""
    validate_records(records)
    source = get_or_create_source(db, sha256)
    existing = {
        (v.surah_number, v.ayah_number): v
        for v in db.query(Verse).filter_by(reading="hafs")
    }
    counts = {"inserted": 0, "replaced": 0, "unchanged": 0, "skipped": 0}
    for r in records:
        fields = {
            "surah_name": r["sura_name_ar"],
            "arabic_text": r["aya_text_unicode"],  # verbatim, never altered
            "page_number": r.get("page"),
            "juz_number": r.get("jozz"),
            "text_imlaei": r.get("aya_text_emlaey"),
            "source_id": source.id,
        }
        verse = existing.get((r["sura_no"], r["aya_no"]))
        if verse is None:
            db.add(Verse(surah_number=r["sura_no"], ayah_number=r["aya_no"], reading="hafs", **fields))
            counts["inserted"] += 1
        elif verse.source_id == source.id:
            counts["unchanged"] += 1
        elif replace:
            # Update in place so tafsir entries keep pointing at the same verse row.
            for k, val in fields.items():
                setattr(verse, k, val)
            counts["replaced"] += 1
        else:
            counts["skipped"] += 1
    db.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the KFGQPC Hafs Quran text.")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument(
        "--replace", action="store_true",
        help="Overwrite verses previously imported from another source (e.g. Quranpedia).",
    )
    args = parser.parse_args()
    if not args.file.exists():
        parser.error(f"{args.file} not found; download {KFGQPC_RELEASE} from {KFGQPC_PAGE_URL}")

    records, sha256 = load_records(args.file)
    init_db()
    db = SessionLocal()
    try:
        counts = import_records(db, records, sha256, replace=args.replace)
    finally:
        db.close()
    print(f"KFGQPC {KFGQPC_RELEASE}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    if counts["skipped"]:
        print(f"{counts['skipped']} verses already exist from another source; re-run with --replace to overwrite.")


if __name__ == "__main__":
    main()
