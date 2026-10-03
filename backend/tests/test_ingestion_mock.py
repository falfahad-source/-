"""These tests mock QuranpediaClient so they run with no network access,
including inside CI or this sandbox. They verify the contract that matters
most for AFAQ: canonical text is stored byte-for-byte, and every row carries
real provenance.
"""
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ingestion.ingest_quran import ingest_surah
from app.ingestion.ingest_tafsir import ingest_surah_tafsir
from app.ingestion.quranpedia_client import QuranpediaAyah
from app.models import Base, TafsirEntry, Verse


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_ingest_surah_stores_text_verbatim(db_session):
    fake_client = MagicMock()
    fake_client.get_surah_ayahs.return_value = [
        QuranpediaAyah(id=1, number=1, surah=1, page_number=1,
                        text="بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ", options=[]),
        QuranpediaAyah(id=2, number=2, surah=1, page_number=1,
                        text="الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ", options=[]),
    ]

    inserted = ingest_surah(db_session, fake_client, surah_id=1)

    assert inserted == 2
    verses = db_session.query(Verse).filter_by(surah_number=1).all()
    assert len(verses) == 2
    assert verses[0].arabic_text == "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
    assert verses[0].source_id is not None
    assert verses[0].source.url.startswith("https://api.quranpedia.net/v1/mushafs/")


def test_ingest_surah_is_idempotent(db_session):
    fake_client = MagicMock()
    fake_client.get_surah_ayahs.return_value = [
        QuranpediaAyah(id=1, number=1, surah=1, page_number=1, text="نص الآية", options=[]),
    ]
    first = ingest_surah(db_session, fake_client, surah_id=1)
    second = ingest_surah(db_session, fake_client, surah_id=1)
    assert first == 1
    assert second == 0  # re-running must not duplicate rows


def _fake_tafsir_client():
    fake_client = MagicMock()
    fake_client.get_surah_ayahs.return_value = [
        QuranpediaAyah(id=1, number=1, surah=1, page_number=1, text="نص الآية", options=[]),
    ]
    fake_client.list_ayah_tafsir_books.return_value = [
        {"id": 3, "name": "تيسير الكريم الرحمن", "author": "السعدي", "fundamental": 1},
        {"id": 999, "name": "كتاب غير أساسي", "author": "مؤلف", "fundamental": 0},
    ]
    fake_client.get_tafsir_for_ayah.return_value = {
        "content": [{"text": "نص التفسير كما ورد", "page": 40}],
    }
    return fake_client


def test_ingest_tafsir_defaults_to_fundamental_books(db_session):
    client = _fake_tafsir_client()
    ingest_surah(db_session, client, surah_id=1)

    assert ingest_surah_tafsir(db_session, client, surah_id=1) == 1
    entry = db_session.query(TafsirEntry).one()
    assert entry.original_text == "نص التفسير كما ورد"
    assert entry.scholar == "السعدي"
    assert entry.source_location == "40"
    assert entry.source.citation_identifier == "quranpedia:book:3"
    client.get_tafsir_for_ayah.assert_called_once_with(1, 1, 3)

    # idempotent: a re-run neither duplicates rows nor refetches the text
    assert ingest_surah_tafsir(db_session, client, surah_id=1) == 0
    client.get_tafsir_for_ayah.assert_called_once()


def test_ingest_tafsir_explicit_books_override_default(db_session):
    client = _fake_tafsir_client()
    ingest_surah(db_session, client, surah_id=1)

    assert ingest_surah_tafsir(db_session, client, surah_id=1, book_ids={999}) == 1
    client.get_tafsir_for_ayah.assert_called_once_with(1, 1, 999)


def test_ingest_tafsir_skips_empty_content(db_session):
    client = _fake_tafsir_client()
    client.get_tafsir_for_ayah.return_value = {"content": []}
    ingest_surah(db_session, client, surah_id=1)

    assert ingest_surah_tafsir(db_session, client, surah_id=1) == 0
    assert db_session.query(TafsirEntry).count() == 0
