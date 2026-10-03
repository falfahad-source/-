"""Uses a real Dorar API response saved from a browser (query "الصلاة"), so
the parser is tested against the actual markup without network access."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ingestion.dorar_client import DorarClient, parse_results
from app.ingestion.ingest_hadith import ingest_verse_hadith
from app.models import Base, HadithEntry, Source, Verse
from app.rag.answer_builder import build_answer
from app.trust import TrustCategory

FIXTURE = Path(__file__).parent / "fixtures" / "dorar_api_salah.json"


def _result_html() -> str:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["ahadith"]["result"]


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_verse(db):
    src = Source(title="KFGQPC", publisher="KFGQPC", source_type="quran_dataset",
                 url="https://qurancomplex.gov.sa/quran-hafs/", trust_category=TrustCategory.QURANIC_TEXT)
    db.add(src)
    db.flush()
    db.add(Verse(surah_number=2, surah_name="البَقَرَةِ", ayah_number=43, arabic_text="نص", reading="hafs",
                 source_id=src.id))
    db.commit()


def _client():
    client = MagicMock(spec=DorarClient)
    client.search.return_value = parse_results(_result_html())
    return client


def test_parses_every_hadith_with_its_fields():
    hadiths = parse_results(_result_html())
    assert [h.rank for h in hadiths] == list(range(1, 16))
    second = hadiths[1]
    assert second.text.startswith("ستكونُ من بعدِي")
    assert second.text.endswith("وأجعلُ صلاتِي مَعهمْ سُبحةً")
    assert (second.narrator, second.muhaddith, second.book, second.reference) == (
        "شداد بن أوس", "البزار", "البحر الزخار", "8/413")
    assert second.grade == "روي بعضه من غير وجه"


def test_highlighting_and_trailing_dot_are_removed_but_words_kept():
    first = parse_results(_result_html())[0]
    assert "<span" not in first.text and "search-keys" not in first.text
    # Expected wording taken from the fixture bytes themselves (typed Arabic can
    # order stacked diacritics differently): the parser must not alter them.
    raw = _result_html()
    start = raw.index("1 -") + len("1 -")
    expected = raw[start:raw.index("</div>", start)].replace('<span class="search-keys">', "").replace("</span>", "")
    expected = " ".join(expected.split()).removesuffix(" .")
    assert first.text == expected
    assert 'class="search-keys"' in first.raw_html  # original markup kept for audit


def test_missing_narrator_dash_becomes_none():
    assert parse_results(_result_html())[0].narrator is None


def test_weak_and_fabricated_grades_are_kept_verbatim():
    grades = {h.rank: h.grade for h in parse_results(_result_html())}
    assert grades[3] == "منكر"
    assert grades[8] == "موضوع"


def test_header_and_more_link_are_not_parsed_as_hadith():
    assert all("المزيد" not in h.text and "canonical" not in h.text for h in parse_results(_result_html()))


def test_client_sends_query_as_skey():
    session = MagicMock()
    session.get.return_value.json.return_value = {"ahadith": {"result": _result_html()}}
    hadiths = DorarClient(session=session).search("الصلاة")
    assert len(hadiths) == 15
    assert session.get.call_args.kwargs["params"] == {"skey": "الصلاة"}


def test_ingest_stores_rows_as_possible_connection_and_is_idempotent(db_session):
    _seed_verse(db_session)
    client = _client()
    assert ingest_verse_hadith(db_session, client, 2, 43, " الصلاة ") == 15
    assert ingest_verse_hadith(db_session, client, 2, 43, "الصلاة") == 0
    rows = db_session.query(HadithEntry).all()
    assert len(rows) == 15
    assert {r.trust_category for r in rows} == {TrustCategory.POSSIBLE_CONNECTION}
    assert {r.search_query for r in rows} == {"الصلاة"}
    assert rows[0].source.citation_identifier == "dorar:hadith_api"


def test_ingest_requires_the_verse_to_exist(db_session):
    with pytest.raises(ValueError, match="not in the database"):
        ingest_verse_hadith(db_session, _client(), 2, 43, "الصلاة")


def test_answer_lists_hadith_separately_from_tafsir_with_grade(db_session):
    _seed_verse(db_session)
    ingest_verse_hadith(db_session, _client(), 2, 43, "الصلاة")
    answer = build_answer(db_session, 2, 43)
    assert answer.verified_tafsir == []  # hadith never leak into tafsir
    assert len(answer.hadith_matches) == 15
    fabricated = answer.hadith_matches[7]
    assert fabricated["grade"] == "موضوع"
    assert "ليست تفسيرًا" in fabricated["label"]
    assert any(s["title"] == "الموسوعة الحديثية — الدرر السنية" for s in answer.sources)
