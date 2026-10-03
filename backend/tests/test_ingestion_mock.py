"""These tests mock QuranpediaClient so they run with no network access,
including inside CI or this sandbox. They verify the contract that matters
most for AFAQ: canonical text is stored byte-for-byte, and every row carries
real provenance.
"""
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Verse
from app.ingestion.ingest_quran import ingest_surah
from app.ingestion.quranpedia_client import QuranpediaAyah


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
