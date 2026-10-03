import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.ingestion.ingest_layers_dump import (
    apply_years,
    book_years,
    extract_ayah_passage,
    import_e3rab_book,
    import_meanings,
    import_morphology,
    import_topics,
)
from app.models import (
    Base,
    Source,
    TafsirEntry,
    Topic,
    Verse,
    VerseTopic,
    WordAnalysis,
    WordMeaning,
)
from app.schema_upgrade import add_missing_columns
from app.trust import TrustCategory


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    src = Source(title="KFGQPC", publisher="KFGQPC", source_type="quran_dataset",
                 url="https://qurancomplex.gov.sa/quran-hafs/", trust_category=TrustCategory.QURANIC_TEXT)
    session.add(src)
    session.flush()
    for a in (39, 40, 41):
        session.add(Verse(surah_number=24, surah_name="النُّورِ", ayah_number=a, arabic_text=f"آية {a}",
                          reading="hafs", source_id=src.id))
    session.commit()
    yield session
    session.close()


def _verse(db, a=40):
    return db.query(Verse).filter_by(surah_number=24, ayah_number=a).one()


MORPH = {"license": {"version": "2026-08-10"}, "data": [{"surah": 24, "ayah": 40, "morphology": {"words": [
    {"number": 4, "text": "بَحْرٍ", "translation": "a sea", "segments": [
        {"role": "stem", "pos": "اسم", "root": "بحر", "lemma": "بَحْر", "description": "اسم مجرور، الجذر (بحر)"}]},
    {"number": 2, "text": "كَظُلُمَاتٍ", "segments": [
        {"role": "prefix", "pos": "حرف جر", "root": None, "lemma": "ك", "description": "حرف جر"},
        {"role": "stem", "pos": "اسم", "root": "ظلم", "lemma": "ظُلُمَة", "description": "اسم مجرور"}]},
]}}]}


def test_morphology_uses_stem_segment_and_credits_the_corpus(db_session):
    assert import_morphology(db_session, MORPH) == 2
    w = db_session.query(WordAnalysis).filter_by(word_number=2).one()
    assert (w.root, w.lemma, w.pos) == ("ظلم", "ظُلُمَة", "اسم")  # stem, not the prefix
    assert w.description == "حرف جر + اسم مجرور"
    assert w.source.url == "https://corpus.quran.com"
    assert import_morphology(db_session, MORPH) == 0  # idempotent


def test_meanings_keep_each_book_as_its_own_source(db_session):
    dump = {"license": {"version": "v"}, "data": [{"surah": 24, "ayah": 40, "meanings": [
        {"book_info": {"id": 491, "name": "السراج في بيان غريب القرآن", "author": "الخضيري"},
         "words": [{"text": "لُّجِّيٍّ", "meaning": "عَمِيقٍ."}]},
        {"book_info": {"id": 1424, "name": "كلمات القرآن", "author": "مخلوف"},
         "words": [{"text": "بحر لجّي", "meaning": "عميق كثير الماء"}, {"text": "x", "meaning": ""}]},
    ]}]}
    assert import_meanings(db_session, dump) == 2  # the empty meaning is skipped
    rows = {m.source.title: m.meaning for m in db_session.query(WordMeaning)}
    assert rows == {"السراج في بيان غريب القرآن": "عَمِيقٍ.", "كلمات القرآن": "عميق كثير الماء"}
    assert import_meanings(db_session, dump) == 0


def test_topics_link_verses_and_keep_parent(db_session):
    dump = {"license": {"version": "v"}, "data": [
        {"surah": 24, "ayah": 40, "topics": [{"id": 897, "name": "البحار"},
                                             {"id": 1414, "name": "ضرب المثل بهما", "parent": {"name": "الظلام"}}]},
        {"surah": 24, "ayah": 41, "topics": [{"id": 897, "name": "البحار"}]},
    ]}
    assert import_topics(db_session, dump) == 3
    assert db_session.get(Topic, 1414).parent_name == "الظلام"
    assert db_session.query(VerseTopic).filter_by(topic_id=897).count() == 2
    assert import_topics(db_session, dump) == 0


CHUNK_LINES = [
    "كلام عن الآية السابقة (٣٩).",
    "قَالَ تَعَالَى: (أَوْ كَظُلُمَاتٍ فِي بَحْرٍ لُجِّيٍّ (٤٠)).",
    "قَوْلُهُ: (أَوْ كَظُلُمَاتٍ) : مَعْطُوفٌ (١) عَلَى «كَسَرَابٍ».",
    "قَالَ تَعَالَى: (أَلَمْ تَرَ أَنَّ اللَّهَ يُسَبِّحُ لَهُ (٤١)).",
    "إعراب الآية التالية",
]
CHUNK = "\n".join(CHUNK_LINES)


def test_extract_passage_runs_from_quote_to_next_ayah():
    assert extract_ayah_passage(CHUNK, 40) == (
        "قَالَ تَعَالَى: (أَوْ كَظُلُمَاتٍ فِي بَحْرٍ لُجِّيٍّ (٤٠)).\n"
        "قَوْلُهُ: (أَوْ كَظُلُمَاتٍ) : مَعْطُوفٌ (١) عَلَى «كَسَرَابٍ».")


def test_footnote_marks_are_not_ayah_quotes():
    assert extract_ayah_passage(CHUNK, 1) is None  # "(١)" mid-line is a footnote


def test_extract_stops_at_surah_header():
    text = "نص الآية (٧)\nإعرابها\n[سورة البقرة (٢) : آية ١]\nالم (١)"
    assert extract_ayah_passage(text, 7) == "نص الآية (٧)\nإعرابها"


def _e3rab_dump(chunk):
    return {"license": {"version": "v"},
            "book": {"id": 309, "name": "التبيان في إعراب القرآن", "author": {"ar_name": "أبو البقاء العكبري"}},
            "ayahs": [{"surah": 24, "ayah": 40, "content": [{"text": chunk.replace("\n", "<br />\r"), "page": 970}]},
                      {"surah": 24, "ayah": 39, "content": [{"text": "لا رقم آية هنا", "page": 969}]}]}


def test_e3rab_import_stores_excerpt_flag_year_and_is_idempotent(db_session):
    assert import_e3rab_book(db_session, _e3rab_dump(CHUNK), year=616) == 2
    e40 = db_session.query(TafsirEntry).filter_by(verse_id=_verse(db_session).id).one()
    assert e40.category == "e3rab" and e40.is_excerpt is True
    assert e40.original_text.startswith("قَالَ تَعَالَى: (أَوْ كَظُلُمَاتٍ")
    assert "يُسَبِّحُ" not in e40.original_text
    e39 = db_session.query(TafsirEntry).filter_by(verse_id=_verse(db_session, 39).id).one()
    assert e39.is_excerpt is False and e39.original_text == "لا رقم آية هنا"  # full chunk kept
    assert e40.source.source_type == "e3rab_book" and e40.source.author_year == 616
    assert import_e3rab_book(db_session, _e3rab_dump(CHUNK), year=616) == 0
    assert db_session.query(Source).filter_by(citation_identifier="quranpedia:book:309").count() == 1


def test_years_from_index_applied_to_book_sources(db_session):
    from app.ingestion.ingest_tafsir import get_or_create_book_source
    get_or_create_book_source(db_session, {"id": 4, "name": "جامع البيان", "author": "الطبري"})
    years = book_years({"data": [{"tafsir": [{"id": 4, "year": 310}, {"id": 9, "year": None}]}]}, "tafsir")
    assert years == {4: 310}
    assert apply_years(db_session, years) == 1
    assert db_session.query(Source).filter_by(citation_identifier="quranpedia:book:4").one().author_year == 310


def test_schema_upgrade_adds_missing_nullable_columns():
    engine = create_engine("sqlite:///:memory:")
    old = MetaData()  # the sources table as an earlier version created it: no author_year
    Table("sources", old, *[Column(c.name, c.type, primary_key=c.primary_key, nullable=c.nullable)
                             for c in Base.metadata.tables["sources"].columns if c.name != "author_year"])
    old.create_all(engine)
    assert add_missing_columns(engine) == ["sources.author_year"]
    assert "author_year" in {c["name"] for c in inspect(engine).get_columns("sources")}


def test_schema_upgrade_refuses_not_null_column():
    engine = create_engine("sqlite:///:memory:")
    old = MetaData()
    Table("sources", old, Column("id", Integer, primary_key=True), Column("title", String))
    old.create_all(engine)
    with pytest.raises(RuntimeError, match="NOT NULL"):
        add_missing_columns(engine)
