import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import main, topic_search
from app.curation import load_document
from app.models import ArticleVerse, ExternalArticle, Source, TafsirEntry, Topic, Verse, VerseTopic
from app.topic_search import core_stem, query_stems, search_topics, stem
from app.trust import TrustCategory
from tests.test_layers_answer import DOC, db  # noqa: F401 - db is a fixture


def test_stemming_matches_forms_of_a_word():
    assert stem("الرضاعه") == stem("رضاعه") == "رضاع"
    assert stem("مدتها") == stem("مده") == "مده"           # pronoun + taa marbuta written ت
    assert query_stems("مدة الرضاعة الطبيعية") == ["مده", "رضاع", "طبيع"]
    assert query_stems("ما هي آيات الجنين في القرآن") == ["جنين"]  # question words dropped
    assert core_stem("مدة الرضاعة الطبيعية") == "رضاع"      # the phrase's subject, not its head or adjective
    assert core_stem("زكاة") is None


@pytest.fixture()
def seeded(db, monkeypatch):  # noqa: F811
    load_document(db, copy.deepcopy(DOC))  # curated comparison on 24:40 (ocean zones, darkness)
    other = db.query(Verse).filter_by(surah_number=25, ayah_number=53).one()
    src = Source(title="Quranpedia topics", publisher="Quranpedia", source_type="topic_index", url="u",
                 trust_category=TrustCategory.TAFSIR_VERIFIED)
    db.add(src)
    db.flush()
    db.add_all([Topic(id=1, name="الرَّضاعة", parent_name=None, source_id=src.id),
                Topic(id=2, name="فضل الإطعام ابتغاء مرضاة اللَّه", parent_name="الاكل", source_id=src.id),
                Topic(id=3, name="البحار", parent_name=None, source_id=src.id)])
    db.flush()
    db.add_all([VerseTopic(verse_id=other.id, topic_id=1), VerseTopic(verse_id=other.id, topic_id=2),
                VerseTopic(verse_id=other.id, topic_id=3)])
    art = ExternalArticle(source_id=src.id, external_id=1, title="ظلمات البحار العميقة", url="https://x/1")
    db.add(art)
    db.flush()
    v2440 = db.query(Verse).filter_by(surah_number=24, ayah_number=40).one()
    db.add(ArticleVerse(article_id=art.id, verse_id=v2440.id, match_method="citation"))
    book = db.query(Source).filter_by(citation_identifier=topic_search.TAFSIR_BOOK).one()  # from the fixture
    db.add(TafsirEntry(verse_id=other.id, source_id=book.id, category="verse_tafsir",
                       original_text="وهو الذي خلط البحرين العذب والمالح وجعل بينهما حاجزًا"))
    db.commit()
    monkeypatch.setattr(topic_search, "_cache", None)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=db.get_bind()))
    return db


def test_topic_finds_verses_with_their_reasons(seeded):
    r = search_topics(seeded, "الرضاعة")
    assert [(x["surah_number"], x["ayah_number"]) for x in r["results"]] == [(25, 53)]
    assert r["results"][0]["reasons"][0] == {"kind": "topic", "label": "الرَّضاعة", "url": None, "coverage": 1.0}


def test_words_not_substrings(seeded):
    # «رضا» must not pick up «مرضاة»: the topic «فضل الإطعام ابتغاء مرضاة الله» is not a match
    labels = [rs["label"] for x in search_topics(seeded, "رضا")["results"] for rs in x["reasons"]]
    assert "الاكل › فضل الإطعام ابتغاء مرضاة اللَّه" not in labels


def test_sources_add_up_and_rank(seeded):
    r = search_topics(seeded, "البحار")
    kinds = {(x["surah_number"], x["ayah_number"]): {rs["kind"] for rs in x["reasons"]} for x in r["results"]}
    assert kinds[(25, 53)] == {"topic"}
    assert kinds[(24, 40)] == {"topic", "article"}  # the fixture's topic plus the article: reasons add up
    assert r["results"][0]["surah_number"] == 24 and r["results"][0]["score"] > r["results"][1]["score"]
    # the curated comparison's concept, and the tafsir mentioning every word typed
    assert any(rs["kind"] == "concept" for x in search_topics(seeded, "طبقات المحيط")["results"] for rs in x["reasons"])
    assert {rs["kind"] for x in search_topics(seeded, "العذب والمالح")["results"] for rs in x["reasons"]} == {"tafsir"}


def test_endpoint(seeded):
    c = TestClient(main.app)
    assert c.get("/search/topics", params={"q": "الرضاعة"}).json()["total"] == 1
    assert c.get("/search/topics", params={"q": "في من"}).status_code == 422
