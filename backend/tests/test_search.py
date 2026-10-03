import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.ingestion.ingest_kfgqpc import DEFAULT_FILE, import_records, load_records
from app.models import Base, Source, Verse
from app.search import normalize_arabic, search_verses
from app.trust import TrustCategory

# Real KFGQPC strings (Uthmani + imla'i), copied from kfgqpc_hafs_v30.json.
VERSES = [
    (1, "الفَاتِحَةِ", 1, "بِسۡمِ ٱللَّهِ ٱلرَّحۡمَٰنِ ٱلرَّحِيمِ ۝١", "بسم الله الرحمن الرحيم"),
    (2, "البَقَرَةِ", 43, "وَأَقِيمُواْ ٱلصَّلَوٰةَ وَءَاتُواْ ٱلزَّكَوٰةَ وَٱرۡكَعُواْ مَعَ ٱلرَّٰكِعِينَ ۝٤٣",
     "وأقيموا الصلاة وآتوا الزكاة واركعوا مع الراكعين"),
    (27, "النَّمۡلِ", 30, "إِنَّهُۥ مِن سُلَيۡمَٰنَ وَإِنَّهُۥ بِسۡمِ ٱللَّهِ ٱلرَّحۡمَٰنِ ٱلرَّحِيمِ ۝٣٠",
     "إنه من سليمان وإنه بسم الله الرحمن الرحيم"),
]


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    src = Source(title="KFGQPC", publisher="KFGQPC", source_type="quran_dataset",
                 url="https://qurancomplex.gov.sa/quran-hafs/", trust_category=TrustCategory.QURANIC_TEXT)
    db.add(src)
    db.flush()
    for s, name, a, text, imlaei in VERSES:
        db.add(Verse(surah_number=s, surah_name=name, ayah_number=a, arabic_text=text, text_imlaei=imlaei,
                     page_number=1, reading="hafs", source_id=src.id))
    db.commit()
    db.session_factory = session_factory
    yield db
    db.close()


def _hits(db, q):
    return [(r["surah_number"], r["ayah_number"]) for r in search_verses(db, q)["results"]]


def test_normalize_strips_tashkeel_marks_and_folds_letters():
    assert normalize_arabic("بِسۡمِ ٱللَّهِ ٱلرَّحۡمَٰنِ ٱلرَّحِيمِ ۝١") == "بسم الله الرحمن الرحيم"
    assert normalize_arabic("أإآٱ ى ة ؤ ئ") == "اااا ي ه و ي"
    assert normalize_arabic("  الـــصلاة  ") == "الصلاه"


def test_plain_spelling_finds_every_occurrence_in_mushaf_order(db_session):
    assert _hits(db_session, "بسم الله الرحمن الرحيم") == [(1, 1), (27, 30)]


def test_imlaei_spelling_matches_uthmani_text(db_session):
    assert _hits(db_session, "اقيموا الصلاة") == [(2, 43)]   # no hamza, imla'i الصلاة


def test_uthmani_input_with_diacritics_also_matches(db_session):
    assert _hits(db_session, "ٱلصَّلَوٰةَ") == [(2, 43)]
    assert _hits(db_session, "الصلوة") == [(2, 43)]          # Uthmani spelling without marks


def test_results_carry_name_number_and_verbatim_text(db_session):
    r = search_verses(db_session, "سليمان")["results"][0]
    assert (r["surah_name"], r["surah_number"], r["ayah_number"]) == ("النَّمۡلِ", 27, 30)
    assert r["text"] == VERSES[2][3]  # stored text, not the normalized form


def test_no_match_returns_empty(db_session):
    res = search_verses(db_session, "كلمة غير موجودة")
    assert res["total"] == 0 and res["results"] == []


def test_limit_caps_results_but_total_counts_all(db_session):
    res = search_verses(db_session, "الرحمن", limit=1)
    assert res["total"] == 2 and len(res["results"]) == 1


@pytest.mark.parametrize("q", ["", " ", "ا", "xyz", "١٢٣"])
def test_too_short_or_non_arabic_query_is_rejected(db_session, q):
    with pytest.raises(ValueError):
        search_verses(db_session, q)


def test_index_refreshes_after_verses_change(db_session):
    assert _hits(db_session, "الراكعين") == [(2, 43)]
    db_session.query(Verse).filter_by(surah_number=2).delete()
    db_session.commit()
    assert _hits(db_session, "الراكعين") == []


def test_search_endpoint(db_session, monkeypatch):
    monkeypatch.setattr(main, "SessionLocal", db_session.session_factory)
    client = TestClient(main.app)
    ok = client.get("/search", params={"q": "بسم الله"})
    assert ok.status_code == 200 and ok.json()["total"] == 2
    assert client.get("/search", params={"q": "x"}).status_code == 422


@pytest.mark.skipif(not DEFAULT_FILE.exists(), reason="KFGQPC data file not present (not in git)")
def test_real_mushaf_known_counts():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    records, sha = load_records(DEFAULT_FILE)
    import_records(db, records, sha)
    assert search_verses(db, "فبأي آلاء ربكما تكذبان")["total"] == 31  # all in surah al-Rahman
    assert _hits(db, "الله لا إله إلا هو الحي القيوم") == [(2, 255), (3, 2)]
    assert _hits(db, "قل هو الله احد") == [(112, 1)]
