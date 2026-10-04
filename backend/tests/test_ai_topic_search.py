import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import main, topic_search
from app.ai_research import api, providers, topic
from app.ai_research.providers import ProviderError
from app.ai_research.topic import parse_suggestions, verify
from tests.test_layers_answer import db  # noqa: F401 - db is a fixture
from tests.test_topic_search import seeded  # noqa: F401 - fixture


@pytest.fixture()
def texts(db):  # noqa: F811
    """Give the fixture verses real text to quote from."""
    from app.models import Verse
    v = db.query(Verse).filter_by(surah_number=24, ayah_number=40).one()
    v.arabic_text = "أَوۡ كَظُلُمَٰتٖ فِي بَحۡرٖ لُّجِّيّٖ يَغۡشَىٰهُ مَوۡجٞ"
    v.text_imlaei = "أو كظلمات في بحر لجي يغشاه موج"
    o = db.query(Verse).filter_by(surah_number=25, ayah_number=53).one()
    o.arabic_text, o.text_imlaei = "وَهُوَ ٱلَّذِي مَرَجَ ٱلۡبَحۡرَيۡنِ", "وهو الذي مرج البحرين"
    db.commit()
    return db


def test_parse_tolerates_fences_and_skips_bad_items():
    text = 'Sure:\n```json\n{"verses": [{"surah": 24, "ayah": 40, "quote": "q", "reason": "r"}, {"surah": "x"}]}\n```'
    assert parse_suggestions(text) == [{"surah": 24, "ayah": 40, "quote": "q", "reason": "r"}]
    with pytest.raises(ProviderError):
        parse_suggestions("no json here")


def test_verify_keeps_corrects_and_drops(texts, monkeypatch):
    monkeypatch.setattr(topic, "_index", None)
    out, dropped = verify(texts, [
        {"surah": 24, "ayah": 40, "quote": "أو كظلمات في بحر لجى", "reason": "ظلمات البحر"},     # right (ى/ي)
        {"surah": 24, "ayah": 41, "quote": "مَرَجَ ٱلۡبَحۡرَيۡنِ", "reason": "البحران"},          # wrong number
        {"surah": 2, "ayah": 255, "quote": "كلمات ليست في المصحف أصلا", "reason": "مختلق"},      # made up
        {"surah": 24, "ayah": 40, "quote": "يغشاه موج", "reason": "مكرر"},                     # duplicate
        {"surah": 24, "ayah": 40, "quote": "أو", "reason": "قصير"},                            # too short
    ])
    assert [(x["surah_number"], x["ayah_number"], x["corrected"]) for x in out] == [(24, 40, False), (25, 53, True)]
    assert out[0]["text"] == "أَوۡ كَظُلُمَٰتٖ فِي بَحۡرٖ لُّجِّيّٖ يَغۡشَىٰهُ مَوۡجٞ"  # the stored text, not the model's
    assert out[0]["reasons"][0]["kind"] == "ai" and dropped == 2


def test_mock_mode_answers_from_the_sources(seeded, monkeypatch):  # noqa: F811
    monkeypatch.delenv("AFAQ_AI_PROVIDER", raising=False)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=seeded.get_bind()))
    r = TestClient(main.app).get("/search/ai", params={"q": "الرضاعة"}).json()
    assert r["mode"] == "mock" and r["note"] and r["total"] == 1
    assert r["results"][0]["reasons"][0]["kind"] == "topic"


def test_live_mode_calls_the_platform_checks_and_caches(texts, monkeypatch):
    for k, v in {"AFAQ_AI_PROVIDER": "http", "AFAQ_AI_API_URL": "https://ai.example/v1/chat/completions",
                 "AFAQ_AI_API_KEY": "k" * 20, "AFAQ_AI_MODEL": "m1", "AFAQ_AI_HOURLY_LIMIT": "10"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(api, "_recent", api.defaultdict(api.deque))
    monkeypatch.setattr(topic, "_cache", topic.OrderedDict())
    monkeypatch.setattr(topic, "_index", None)
    monkeypatch.setattr(topic_search, "_cache", None)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=texts.get_bind()))
    calls = []

    class R:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"verses": [
                {"surah": 24, "ayah": 40, "quote": "كظلمات في بحر لجي", "reason": "ظلمات البحر العميق"},
                {"surah": 9, "ayah": 9, "quote": "نص مختلق لا وجود له", "reason": "x"}]}, ensure_ascii=False)}}]}

    def fake_post(url, headers, json, timeout):
        calls.append(json["messages"][1]["content"])
        return R()

    monkeypatch.setattr(providers.requests, "post", fake_post)
    c = TestClient(main.app)
    r = c.get("/search/ai", params={"q": "ظلمات البحار"}).json()
    assert r["mode"] == "live" and r["total"] == 1 and r["dropped"] == 1
    assert r["results"][0]["reasons"][0]["label"] == "ظلمات البحر العميق" and r["trust_category"] == "UNVERIFIED_CLAIM"
    c.get("/search/ai", params={"q": "ظلمات البحار"})
    assert len(calls) == 1  # the second identical query is answered from the cache
    monkeypatch.setattr(providers.requests, "post", lambda *a, **k: type("E", (), {"status_code": 500})())
    assert c.get("/search/ai", params={"q": "موضوع آخر"}).status_code == 502


def test_alif_spelling_and_surah_hint(texts, monkeypatch):
    monkeypatch.setattr(topic, "_index", None)
    from app.models import Verse
    o = texts.query(Verse).filter_by(surah_number=25, ayah_number=53).one()
    o.text_imlaei = "خلق السموات والارض ومرج البحرين"   # the mushaf's imla'i spelling
    texts.commit()
    out, dropped = verify(texts, [{"surah": 25, "ayah": 53, "quote": "خلق السماوات والأرض", "reason": "r"}])
    assert [(x["surah_number"], x["ayah_number"], x["corrected"]) for x in out] == [(25, 53, False)] and dropped == 0
