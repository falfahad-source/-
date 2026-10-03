import gzip
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ingestion.ingest_tafsir_dump import (
    download,
    fundamental_book_ids,
    import_book,
    load_gz_json,
)
from app.models import Base, Source, TafsirEntry, Verse
from app.trust import TrustCategory


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_verses(db, n=3):
    src = Source(title="KFGQPC", publisher="KFGQPC", source_type="quran_dataset",
                 url="https://qurancomplex.gov.sa/quran-hafs/", trust_category=TrustCategory.QURANIC_TEXT)
    db.add(src)
    db.flush()
    for a in range(1, n + 1):
        db.add(Verse(surah_number=1, surah_name="الفاتحة", ayah_number=a, arabic_text=f"آية {a}",
                     reading="hafs", source_id=src.id))
    db.commit()


def _dump():
    """Same shape as a real tafsir-book-{id}.json.gz (author is an object there)."""
    return {
        "license": {"version": "2026-08-10"},
        "book": {"id": 3, "name": "تيسير الكريم الرحمن",
                 "author": {"id": 3444, "ar_name": "السعدي", "full_name": "عبد الرحمن بن ناصر السعدي"}},
        "ayahs": [
            {"surah": 1, "ayah": 1, "content": [{"text": "<span>نص</span> أول", "page": 39},
                                                {"text": "تتمة", "page": 40}]},
            {"surah": 1, "ayah": 2, "content": []},                  # no text for this ayah
            {"surah": 1, "ayah": 3, "content": [{"text": "نص ثالث", "page": 41}]},
            {"surah": 99, "ayah": 1, "content": [{"text": "x", "page": 1}]},  # verse not in DB
        ],
    }


def test_import_book_stores_verbatim_text_and_provenance(db_session):
    _seed_verses(db_session)
    assert import_book(db_session, _dump()) == 2
    first = db_session.query(TafsirEntry).join(Verse).filter(Verse.ayah_number == 1).one()
    assert first.original_text == "<span>نص</span> أول\nتتمة"
    assert first.scholar == "السعدي"
    assert first.source_location == "39"
    assert first.source.citation_identifier == "quranpedia:book:3"
    assert first.source.version == "dump:2026-08-10"
    assert first.source.trust_category == TrustCategory.TAFSIR_VERIFIED


def test_import_book_is_idempotent(db_session):
    _seed_verses(db_session)
    import_book(db_session, _dump())
    assert import_book(db_session, _dump()) == 0
    assert db_session.query(TafsirEntry).count() == 2


def test_import_book_reuses_source_created_by_api_ingestion(db_session):
    """An entry fetched earlier through the API must not be duplicated."""
    _seed_verses(db_session)
    from app.ingestion.ingest_tafsir import get_or_create_book_source
    src = get_or_create_book_source(db_session, {"id": 3, "name": "تيسير الكريم الرحمن", "author": "السعدي"})
    verse = db_session.query(Verse).filter_by(ayah_number=1).one()
    db_session.add(TafsirEntry(verse_id=verse.id, source_id=src.id, category="verse_tafsir", original_text="api"))
    db_session.commit()

    assert import_book(db_session, _dump()) == 1  # only ayah 3 is new
    assert db_session.query(Source).filter_by(citation_identifier="quranpedia:book:3").count() == 1


def test_import_book_requires_verses(db_session):
    with pytest.raises(ValueError, match="import the Quran text first"):
        import_book(db_session, _dump())


def test_fundamental_book_ids_from_index():
    index = {"data": [
        {"surah": 1, "ayah": 1, "tafsir": [{"id": 3, "fundamental": 1}, {"id": 9, "fundamental": 0}]},
        {"surah": 1, "ayah": 2, "tafsir": [{"id": 4, "fundamental": 1}, {"id": 3, "fundamental": 1}]},
    ]}
    assert fundamental_book_ids(index) == [3, 4]


def test_download_caches_and_round_trips_gzip(tmp_path):
    payload = gzip.compress(json.dumps({"ok": True}).encode())
    session = MagicMock()
    session.get.return_value.content = payload
    path = download("x.json.gz", cache_dir=tmp_path, session=session)
    download("x.json.gz", cache_dir=tmp_path, session=session)
    assert session.get.call_count == 1  # second call served from cache
    assert load_gz_json(path) == {"ok": True}
    assert not list(tmp_path.glob("*.part"))
