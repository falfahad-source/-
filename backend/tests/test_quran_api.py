import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import main, quran_api
from app.curation import load_document
from app.models import ArticleVerse, ExternalArticle, Source, Verse
from app.trust import TrustCategory
from tests.test_layers_answer import DOC, db  # noqa: F401 - db is a fixture


@pytest.fixture()
def client(db, monkeypatch):  # noqa: F811
    load_document(db, copy.deepcopy(DOC))  # curated comparison on 24:40
    src = Source(title="quran-m", publisher="quran-m", source_type="ijaz_site", url="u",
                 trust_category=TrustCategory.POSSIBLE_CONNECTION)
    db.add(src)
    db.flush()
    other = db.query(Verse).filter_by(surah_number=25, ayah_number=53).one()
    for i in (1, 2):
        art = ExternalArticle(source_id=src.id, external_id=i, title=f"a{i}", url=f"https://x/{i}")
        db.add(art)
        db.flush()
        db.add(ArticleVerse(article_id=art.id, verse_id=other.id, match_method="citation"))
    db.commit()
    monkeypatch.setattr(quran_api, "SessionLocal", sessionmaker(bind=db.get_bind()))
    return TestClient(main.app)


def test_surah_index_counts_marked_ayahs(client):
    s = client.get("/surahs").json()["surahs"]
    assert [x["number"] for x in s] == [24, 25]
    assert s[0] == {"number": 24, "name": "النُّورِ", "ayah_count": 1, "curated_ayahs": 1, "ijaz_ayahs": 0}
    assert s[1]["ijaz_ayahs"] == 1 and s[1]["curated_ayahs"] == 0


def test_surah_verses_carry_their_marks(client):
    v = client.get("/surah/24").json()
    assert v["name"] == "النُّورِ"
    assert v["verses"][0]["ayah_number"] == 40 and v["verses"][0]["curated"] is True
    assert v["verses"][0]["text"] == "أَوۡ كَظُلُمَٰتࣲ ..."
    assert client.get("/surah/25").json()["verses"][0]["ijaz_articles"] == 2
    assert client.get("/surah/99").status_code == 404
