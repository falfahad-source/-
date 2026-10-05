"""Speed measures: indexes on foreign keys, cached read-only pages, compressed responses."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app import cache, main, review_api
from app.models import Base
from app.schema_upgrade import add_missing_indexes
from tests.test_layers_answer import db  # noqa: F401 - db is a fixture
from tests.test_reviews import KEY, loaded  # noqa: F401 - loaded is a fixture


def test_every_foreign_key_gets_an_index_once():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    created = add_missing_indexes(engine)
    assert "ix_tafsir_entries_verse_id" in created and "ix_word_meanings_verse_id" in created
    assert "ix_verse_topics_topic_id" in created
    assert add_missing_indexes(engine) == []          # later starts create nothing
    cols = {ix["column_names"][0] for ix in inspect(engine).get_indexes("tafsir_entries")}
    assert {"verse_id", "source_id"} <= cols


def test_verse_page_is_built_once_compressed_and_refreshed_by_a_review(loaded, monkeypatch):  # noqa: F811
    factory = sessionmaker(bind=loaded.get_bind())
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(review_api, "SessionLocal", factory)
    built = []
    real = main.build_answer
    monkeypatch.setattr(main, "build_answer", lambda *a: (built.append(a), real(*a))[1])
    c = TestClient(main.app)

    first = c.get("/verse/24/40", headers={"Accept-Encoding": "gzip"})
    again = c.get("/verse/24/40")
    assert first.status_code == 200 and again.json() == first.json() and len(built) == 1
    assert first.headers.get("content-encoding") == "gzip" and "max-age" in first.headers["cache-control"]
    status = lambda r: {x["review_status"] for x in r.json()["possible_connections"]}  # noqa: E731
    assert status(first) == {"draft"}

    monkeypatch.setenv("AFAQ_REVIEWERS", "د. أحمد:tok-ahmad-0123456789")
    h = {"Authorization": "Bearer tok-ahmad-0123456789"}
    assert c.post(f"/review/{KEY}", json={"decision": "approved", "explanation": "نص معتمد."}, headers=h).status_code == 200
    after = c.get("/verse/24/40")
    assert len(built) == 2 and "approved" in status(after)   # the review cleared the cache


def test_errors_are_not_cached(loaded, monkeypatch):  # noqa: F811
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=loaded.get_bind()))
    c = TestClient(main.app)
    assert c.get("/verse/2/255").status_code == 404
    assert "verse:2:255" not in cache._store


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(cache, "MAX_BYTES", 100)
    for i in range(10):
        cache.cached_json(f"k{i}", lambda: {"x": "a" * 30})
    assert cache._size <= 100 and "k9" in cache._store and "k0" not in cache._store
