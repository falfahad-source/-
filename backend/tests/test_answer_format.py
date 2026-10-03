import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Relationship, Source, Verse
from app.rag.answer_builder import build_answer
from app.trust import TrustCategory


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed_verse(db):
    src = Source(
        title="Quranpedia Mushaf #1", publisher="Quranpedia.net", source_type="quran_api",
        url="https://api.quranpedia.net/v1/mushafs/1", trust_category=TrustCategory.QURANIC_TEXT,
    )
    db.add(src)
    db.flush()
    verse = Verse(surah_number=24, surah_name="النور", ayah_number=40,
                   arabic_text="أَوْ كَظُلُمَاتٍ فِي بَحْرٍ لُجِّيٍّ...", reading="hafs", source_id=src.id)
    db.add(verse)
    db.commit()
    return verse


def test_missing_verse_returns_none(db_session):
    assert build_answer(db_session, 2, 9999) is None


def test_answer_without_tafsir_or_science_flags_not_established(db_session):
    _seed_verse(db_session)
    answer = build_answer(db_session, 24, 40)
    assert answer is not None
    assert answer.quranic_text.startswith("أَوْ كَظُلُمَاتٍ")
    assert answer.verified_tafsir == []
    assert answer.possible_connections == []
    assert any("تفسير" in msg for msg in answer.not_established)


def test_possible_connection_is_always_labeled(db_session):
    verse = _seed_verse(db_session)
    sci_src = Source(
        title="Example Oceanography Paper", publisher="Example University",
        source_type="scientific_paper", url="https://example.edu/paper",
        trust_category=TrustCategory.SCIENTIFIC_FACT,
    )
    db_session.add(sci_src)
    db_session.flush()
    db_session.add(Relationship(
        source_entity=f"verse:{verse.surah_number}:{verse.ayah_number}",
        target_entity="concept:light_attenuation_in_deep_water",
        relationship_type="thematic_similarity",
        evidence_source_id=sci_src.id,
        trust_category=TrustCategory.POSSIBLE_CONNECTION,
        confidence=0.4,
        explanation="Tafsir describes layered darkness; oceanography describes light attenuation with depth.",
    ))
    db_session.commit()

    answer = build_answer(db_session, verse.surah_number, verse.ayah_number)
    assert len(answer.possible_connections) == 1
    assert answer.possible_connections[0]["label"] == "POSSIBLE CONNECTION — not tafsir."


def test_non_possible_connection_relationship_is_excluded_from_section_e(db_session):
    """A Relationship mistakenly marked with a different trust_category must
    never leak into the 'possible connections' section under its label."""
    verse = _seed_verse(db_session)
    src = Source(title="x", publisher="x", source_type="x", url="https://x",
                 trust_category=TrustCategory.TAFSIR_VERIFIED)
    db_session.add(src)
    db_session.flush()
    db_session.add(Relationship(
        source_entity=f"verse:{verse.surah_number}:{verse.ayah_number}",
        target_entity="concept:y", relationship_type="z",
        evidence_source_id=src.id, trust_category=TrustCategory.TAFSIR_VERIFIED,
        confidence=1.0, explanation="not a possible connection",
    ))
    db_session.commit()

    answer = build_answer(db_session, verse.surah_number, verse.ayah_number)
    assert answer.possible_connections == []
