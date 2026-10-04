import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import main
from app.ai_research import api, providers
from app.ai_research.mock import PLACEHOLDER
from app.ai_research.prompt import RESEARCH_PROMPT
from tests.test_layers_answer import db  # noqa: F401 - db is a fixture


@pytest.fixture()
def client(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(api, "SessionLocal", sessionmaker(bind=db.get_bind()))
    for k in ("AFAQ_AI_PROVIDER", "AFAQ_AI_API_URL", "AFAQ_AI_API_KEY", "AFAQ_AI_MODEL"):
        monkeypatch.delenv(k, raising=False)
    return TestClient(main.app)


def test_status_defaults_to_test_mode_and_exposes_the_prompt(client):
    r = client.get("/ai-research/status").json()
    assert r["mode"] == "mock" and r["configured"]
    assert r["prompt"] == RESEARCH_PROMPT
    assert "لا تخترع أي مصدر أو دراسة أو DOI." in r["prompt"]


def test_mock_report_carries_the_verse_verbatim_and_no_findings(client):
    r = client.post("/ai-research", json={"surah_number": 24, "ayah_number": 40})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "mock"
    assert body["trust_category"] == "UNVERIFIED_CLAIM"
    assert body["verse"]["text"] == "أَوۡ كَظُلُمَٰتࣲ ..."
    md = body["report_markdown"]
    assert "تقرير تجريبي" in md and PLACEHOLDER in md
    assert "doi" not in md.lower() and "http" not in md  # test mode never shows a citation


def test_unknown_verse_is_404(client):
    assert client.post("/ai-research", json={"surah_number": 2, "ayah_number": 255}).status_code == 404
    assert client.post("/ai-research", json={"surah_number": 115, "ayah_number": 1}).status_code == 422


def test_http_provider_reports_missing_settings(client, monkeypatch):
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "http")
    assert client.get("/ai-research/status").json()["missing_settings"] == [
        "AFAQ_AI_API_URL", "AFAQ_AI_API_KEY", "AFAQ_AI_MODEL"]
    r = client.post("/ai-research", json={"surah_number": 24, "ayah_number": 40})
    assert r.status_code == 502 and "AFAQ_AI_API_KEY" in r.json()["detail"]


def test_unknown_provider_is_503(client, monkeypatch):
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "nope")
    assert client.get("/ai-research/status").status_code == 503


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_http_provider_sends_prompt_as_system_and_verse_as_user(client, monkeypatch):
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "http")
    monkeypatch.setenv("AFAQ_AI_API_URL", "https://ai.example/v1/chat/completions")
    monkeypatch.setenv("AFAQ_AI_API_KEY", "k" * 20)
    monkeypatch.setenv("AFAQ_AI_MODEL", "m1")
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, headers=headers, json=json)
        return FakeResponse(200, {"choices": [{"message": {"content": "# تقرير"}}]})

    monkeypatch.setattr(providers.requests, "post", fake_post)
    body = client.post("/ai-research", json={"surah_number": 24, "ayah_number": 40}).json()
    assert body["mode"] == "live" and body["model"] == "m1" and body["report_markdown"] == "# تقرير"
    msgs = sent["json"]["messages"]
    assert msgs[0] == {"role": "system", "content": RESEARCH_PROMPT}
    assert msgs[1]["role"] == "user" and "أَوۡ كَظُلُمَٰتࣲ ..." in msgs[1]["content"]
    assert sent["headers"]["Authorization"] == "Bearer " + "k" * 20

    monkeypatch.setattr(providers.requests, "post", lambda *a, **k: FakeResponse(500, {}))
    r = client.post("/ai-research", json={"surah_number": 24, "ayah_number": 40})
    assert r.status_code == 502 and "k" * 20 not in r.text  # the key never leaks


def test_live_reports_are_limited_per_client(client, monkeypatch):
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "http")
    monkeypatch.setenv("AFAQ_AI_API_URL", "https://ai.example/v1/chat/completions")
    monkeypatch.setenv("AFAQ_AI_API_KEY", "k" * 20)
    monkeypatch.setenv("AFAQ_AI_MODEL", "m1")
    monkeypatch.setenv("AFAQ_AI_HOURLY_LIMIT", "2")
    monkeypatch.setattr(api, "_recent", api.defaultdict(api.deque))
    monkeypatch.setattr(providers.requests, "post",
                        lambda *a, **k: FakeResponse(200, {"choices": [{"message": {"content": "# r"}}]}))
    body = {"surah_number": 24, "ayah_number": 40}
    assert [client.post("/ai-research", json=body).status_code for _ in range(3)] == [200, 200, 429]
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "mock")  # test mode is never limited
    assert client.post("/ai-research", json=body).status_code == 200
