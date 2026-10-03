import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ingestion.ingest_kfgqpc import (
    DEFAULT_FILE,
    HAFS_AYAH_COUNT,
    KfgqpcDataError,
    import_records,
    load_records,
    validate_records,
)
from app.models import Base, Source, Verse
from app.trust import TrustCategory


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _records():
    """A structurally valid synthetic release: 114 surahs, 6236 ayahs. The text
    is a placeholder, not Quran text — these tests check plumbing, not content."""
    counts = [1] * 114
    counts[1] = HAFS_AYAH_COUNT - 113  # put the remainder in surah 2
    records, rid = [], 0
    for surah, n in enumerate(counts, start=1):
        for ayah in range(1, n + 1):
            rid += 1
            records.append({
                "id": rid, "jozz": 1, "page": 1, "sura_no": surah, "aya_no": ayah,
                "sura_name_ar": f"سورة {surah}", "aya_text_unicode": f"نص {surah}:{ayah} ۝{ayah}",
                "aya_text_emlaey": f"نص {surah}:{ayah}",
            })
    return records


def test_import_stores_text_verbatim_with_layout(db_session):
    counts = import_records(db_session, _records(), sha256="abc")
    assert counts == {"inserted": HAFS_AYAH_COUNT, "replaced": 0, "unchanged": 0, "skipped": 0}
    v = db_session.query(Verse).filter_by(surah_number=2, ayah_number=5).one()
    assert v.arabic_text == "نص 2:5 ۝5"
    assert v.text_imlaei == "نص 2:5"
    assert (v.page_number, v.juz_number, v.surah_name) == (1, 1, "سورة 2")
    assert v.source.citation_identifier == "kfgqpc:kfgqpc_hafs_v30"
    assert v.source.version == "sha256:abc"
    assert v.source.trust_category == TrustCategory.QURANIC_TEXT


def test_import_is_idempotent(db_session):
    import_records(db_session, _records(), sha256="abc")
    counts = import_records(db_session, _records(), sha256="abc")
    assert counts["unchanged"] == HAFS_AYAH_COUNT and counts["inserted"] == 0
    assert db_session.query(Verse).count() == HAFS_AYAH_COUNT


def test_import_refuses_different_file_under_same_release(db_session):
    import_records(db_session, _records(), sha256="abc")
    with pytest.raises(KfgqpcDataError):
        import_records(db_session, _records(), sha256="different")


def _seed_other_source_verse(db):
    src = Source(title="Quranpedia", publisher="Quranpedia.net", source_type="quran_api",
                 url="https://api.quranpedia.net/v1/mushafs/1", trust_category=TrustCategory.QURANIC_TEXT)
    db.add(src)
    db.flush()
    v = Verse(surah_number=1, surah_name="سورة 1", ayah_number=1, arabic_text="نص قديم",
              reading="hafs", source_id=src.id)
    db.add(v)
    db.commit()
    return v


def test_existing_verse_from_other_source_is_skipped_without_replace(db_session):
    old = _seed_other_source_verse(db_session)
    counts = import_records(db_session, _records(), sha256="abc")
    assert counts["skipped"] == 1
    assert db_session.get(Verse, old.id).arabic_text == "نص قديم"


def test_replace_updates_in_place_keeping_row_id(db_session):
    old = _seed_other_source_verse(db_session)
    counts = import_records(db_session, _records(), sha256="abc", replace=True)
    assert counts["replaced"] == 1
    v = db_session.get(Verse, old.id)  # same row, so tafsir links survive
    assert v.arabic_text == "نص 1:1 ۝1"
    assert v.source.citation_identifier == "kfgqpc:kfgqpc_hafs_v30"


@pytest.mark.parametrize("mutate, message", [
    (lambda r: r.pop(), "expected 6236"),
    (lambda r: r[0].update(aya_text_unicode="  "), "empty text"),
    (lambda r: r[5].update(aya_no=999), "not contiguous"),
    (lambda r: r[0].pop("sura_name_ar"), "missing"),
])
def test_malformed_file_is_rejected_before_writing(db_session, mutate, message):
    records = _records()
    mutate(records)
    with pytest.raises(KfgqpcDataError, match=message):
        import_records(db_session, records, sha256="abc")
    assert db_session.query(Verse).count() == 0


@pytest.mark.skipif(not DEFAULT_FILE.exists(), reason="KFGQPC data file not present (not in git)")
def test_real_release_file_is_valid():
    records, sha256 = load_records(DEFAULT_FILE)
    validate_records(records)
    first = next(r for r in records if (r["sura_no"], r["aya_no"]) == (1, 1))
    assert first["aya_text_unicode"].startswith("بِسۡمِ")
    assert len(sha256) == 64
    json.dumps(first)  # plain JSON-serialisable record
