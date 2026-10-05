import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import main
from app.ai_research import api, providers
from app.ai_research.context import source_pack
from app.ai_research.mock import PLACEHOLDER
from app.ai_research.prompt import RESEARCH_PROMPT
from app.ai_research.report import norm_url
from app.models import AiReport
from tests.test_layers_answer import db  # noqa: F401 - db is a fixture

KEY = "sk-test-" + "k" * 24
VERSE = {"surah_number": 24, "ayah_number": 40}


@pytest.fixture()
def client(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(api, "SessionLocal", sessionmaker(bind=db.get_bind()))
    monkeypatch.setattr(api, "_jobs", {})
    monkeypatch.setattr(api, "_recent", api.defaultdict(api.deque))
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    for k in ("AFAQ_AI_PROVIDER", "AFAQ_AI_API_URL", "AFAQ_AI_API_KEY", "AFAQ_AI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
              "OPENAI_VECTOR_STORE_IDS", "OPENAI_WEB_SEARCH", "OPENAI_REASONING_EFFORT", "AFAQ_AI_HOURLY_LIMIT"):
        monkeypatch.delenv(k, raising=False)
    return TestClient(main.app)


def openai_env(monkeypatch, **extra):
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


def wait(client, start):
    """Follow a research job to its end; returns the last job view."""
    assert start.status_code == 202, start.text
    job = start.json()
    deadline = time.monotonic() + 5
    while job["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)
        job = client.get(f"/ai-research/jobs/{job['job_id']}").json()
    return job


# -- a fake OpenAI Responses API -----------------------------------------------------------
GOOD_URL = "https://oceanservice.noaa.gov/facts/internal-waves.html"
FAKE_URL = "https://www.nature.com/articles/invented-study-123"


def report(**over):
    r = {
        "verse_reference": "سورة النور، الآية 40", "scientific_topic": "الأمواج الداخلية في المحيط",
        "potential_claim": "في البحار العميقة أمواج داخلية تحت الأمواج السطحية", "related_text": "يغشاه موج من فوقه موج",
        "link_kind": "needs_interpretation", "quranic_context": "مثل لأعمال الكافرين.\u2028 مم", "key_words": [
            {"word": "لجي", "meaning": "عميق كثير الماء", "source_ids": ["Q1"]}],
        "interpretive_boundaries": "الآية مثل، لا وصف علمي مقصود بالضرورة.", "alternative_readings": ["الموج الثاني موج السطح نفسه"],
        "scientific_background": "توجد أمواج داخلية بين طبقات الماء المختلفة الكثافة.", "scientific_consensus": "established",
        "consensus_note": "", "historical_background": "وُصفت علميًا في القرن التاسع عشر.", "known_before_revelation": "no_evidence_found",
        "comparison": "تطابق عام.", "supporting_evidence": [{"point": "الأمواج الداخلية حقيقة", "source_ids": ["S1"]}],
        "counter_evidence": [{"point": "لا يلزم أن يقصد النص ذلك", "source_ids": ["Q1", "Q99"]}],
        "alternative_explanations": ["وصف بلاغي لظلمة البحر"], "critical_analysis": [{"issue": "anachronism", "note": "إسقاط محتمل"}],
        "scientific_claim_assessment": {"verdict": "supported", "reason": "حقيقة علمية"},
        "correspondence_assessment": {"verdict": "needs_interpretation", "reason": "يحتاج تأويلًا"},
        "confidence_level": "possible", "final_assessment": f"العلاقة ممكنة. انظر {FAKE_URL}", "hypotheses": [], "research_gaps": [],
        "quranic_sources": [{"id": "Q1", "used_for": "المعنى"}, {"id": "Q42", "used_for": "مصدر لم يُرسل"}],
        "scientific_sources": [
            {"id": "S1", "title": "Internal waves", "authors_or_institution": "NOAA", "year": None, "url": GOOD_URL + "?utm_source=openai",
             "source_type": "institution", "used_for": "تعريف"},
            {"id": "S2", "title": "Invented study", "authors_or_institution": "Nobody", "year": "2020", "url": FAKE_URL,
             "source_type": "peer_reviewed", "used_for": "مختلق"}],
    }
    r.update(over)
    return r


def completed(data, searches=(("completed", [GOOD_URL]),), status="completed", extra_output=()):
    output = [{"type": "web_search_call", "status": st, "action": {"type": "search", "query": "q", "sources": [{"type": "url", "url": u} for u in urls]}}
              for st, urls in searches]
    output += list(extra_output)
    output.append({"type": "message", "content": [{"type": "output_text", "annotations": [],
                                                   "text": data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)}]})
    return {"type": f"response.{status}", "response": {"status": status, "output": output}}


class Stream:
    def __init__(self, events, status=200, body=None, headers=None):
        self.status_code, self.events, self._body, self.headers = status, events, body or {}, headers or {}

    def iter_content(self, chunk_size=None):
        # raw UTF-8, cut into 7-byte pieces: events and Arabic letters split across chunks, as on a network
        raw = b"".join(f"event: {e.get('type')}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n".encode() for e in self.events)
        for i in range(0, len(raw), 7):
            yield raw[i:i + 7]

    def json(self):
        return self._body

    def close(self):
        pass


def fake_openai(monkeypatch, *replies):
    """requests.post answering with the given Streams in turn; returns the list of requests sent."""
    sent, queue = [], list(replies)

    def post(url, json, stream, headers, timeout):
        sent.append({"url": url, "json": json, "headers": headers})
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(providers.requests, "post", post)
    return sent


EVENTS = [{"type": "response.created"}, {"type": "response.web_search_call.in_progress"},
          {"type": "response.web_search_call.searching"}, {"type": "response.web_search_call.completed"},
          {"type": "response.output_text.delta", "delta": "{"}]


# -- test mode ------------------------------------------------------------------------------
def test_status_defaults_to_test_mode_and_exposes_the_prompt(client):
    r = client.get("/ai-research/status").json()
    assert r["mode"] == "mock" and r["configured"] and r["tools"] == []
    assert r["prompt"] == RESEARCH_PROMPT
    for rule in ("لا تبدأ أبدًا من فرضية أن الآية تحتوي على إعجاز علمي", "لا تختلق مصدرًا ولا دراسة ولا DOI",
                 "مقاومة الانحياز التأكيدي", "contradicted", "التفسير لا يثبت حقيقة علمية"):
        assert rule in r["prompt"]


def test_mock_report_has_the_report_structure_and_no_findings(client):
    r = client.post("/ai-research", json=VERSE)
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "mock" and body["trust_category"] == "UNVERIFIED_CLAIM"
    assert body["verse"]["text"] == "أَوۡ كَظُلُمَٰتࣲ ..."
    md = body["report_markdown"]
    assert "تقرير تجريبي" in md and PLACEHOLDER in md
    for section in ("الظاهرة العلمية محل الدراسة", "ماذا يقول النص؟", "ماذا يقول العلم الحديث؟", "تاريخ المعرفة العلمية",
                    "المقارنة", "الأدلة المؤيدة", "الأدلة المعارضة والقيود", "التفسيرات البديلة", "النقد", "التقييم",
                    "المصادر القرآنية والتفسيرية", "المصادر العلمية"):
        assert f"## {section}" in md or f"### {section}" in md
    assert "doi" not in md.lower() and "http" not in md  # test mode never shows a citation
    assert body["confidence_level"] is None


def test_unknown_verse_is_404(client):
    assert client.post("/ai-research", json={"surah_number": 2, "ayah_number": 255}).status_code == 404
    assert client.post("/ai-research", json={"surah_number": 115, "ayah_number": 1}).status_code == 422


def test_unknown_provider_is_503(client, monkeypatch):
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "nope")
    assert client.get("/ai-research/status").status_code == 503


# -- the source pack -------------------------------------------------------------------------
def test_source_pack_is_the_verse_stored_sources_with_ids(db):  # noqa: F811
    pack = source_pack(db, 24, 40)
    assert pack and [s["id"] for s in pack] == [f"Q{i}" for i in range(1, len(pack) + 1)]
    assert all("<" not in s["text"] for s in pack)          # markup removed
    assert any(s["kind"] == "tafsir" for s in pack)
    assert source_pack(db, 2, 255) == []


# -- OpenAI ----------------------------------------------------------------------------------
def test_openai_status_needs_the_key_and_never_shows_it(client, monkeypatch):
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "openai")
    r = client.get("/ai-research/status").json()
    assert r["mode"] == "live" and r["missing_settings"] == ["OPENAI_API_KEY"] and r["model"] == "gpt-6.1-sol"
    assert client.post("/ai-research", json=VERSE).status_code == 502
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    r = client.get("/ai-research/status")
    assert r.json()["configured"] and r.json()["tools"] == ["web_search", "structured_outputs"] and KEY not in r.text


def test_openai_research_request_and_checked_report(client, db, monkeypatch):  # noqa: F811
    openai_env(monkeypatch)
    sent = fake_openai(monkeypatch, Stream(EVENTS + [completed(report())]))
    job = wait(client, client.post("/ai-research", json=VERSE))
    assert job["status"] == "done", job
    assert [s["state"] for s in job["stages"]] == ["done"] * 5 and job["searches"] == 1
    assert job["stages"][2]["label"].endswith("(عملية بحث واحدة)")

    req = sent[0]
    assert req["url"] == "https://api.openai.com/v1/responses"
    assert req["headers"]["Authorization"] == f"Bearer {KEY}"
    body = req["json"]
    assert body["model"] == "gpt-6.1-sol" and body["instructions"] == RESEARCH_PROMPT
    assert body["stream"] is True and body["store"] is False and body["reasoning"] == {"effort": "high"}
    assert body["tools"] == [{"type": "web_search"}] and body["include"] == ["web_search_call.action.sources"]
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and "confidence_level" in fmt["schema"]["required"]
    assert "أَوۡ كَظُلُمَٰتࣲ ..." in body["input"] and "[Q1]" in body["input"]   # the verse and its source pack

    r = job["report"]
    rep, md = r["report"], r["report_markdown"]
    sources = {s["id"]: s for s in rep["scientific_sources"]}
    assert sources["S1"]["verified"] and sources["S1"]["url"].startswith(GOOD_URL)
    assert not sources["S2"]["verified"] and sources["S2"]["url"] is None
    assert FAKE_URL not in md and "nature.com" not in md          # not even inside the model's own text
    assert f"]({GOOD_URL})" in md and "utm_source" not in md and "غير متحقق منه" in md
    assert [q["id"] for q in rep["quranic_sources"]] == ["Q1"]     # Q42 was never sent
    assert rep["counter_evidence"][0]["unknown_ids"] == ["Q99"]
    assert r["confidence_level"] == "possible" and r["confidence_label"] == "ممكن (Possible)"
    assert r["checks"]["verified_sources"] == 1 and r["checks"]["unverified_sources"] == 1
    assert rep["quranic_context"] == "مثل لأعمال الكافرين.\u2028 مم"   # Arabic and a line separator survive the stream

    row = db.query(AiReport).one()
    assert row.model == "gpt-6.1-sol" and json.loads(row.report_json)["confidence_level"] == "possible"
    # paid once: the stored report, no second request
    again = client.post("/ai-research", json=VERSE)
    assert again.status_code == 200 and again.json()["saved"] and len(sent) == 1
    page = client.get("/ai-research/report", params=VERSE).json()
    assert page["saved"] and page["report_markdown"] == md


def test_strong_verdict_without_a_verified_source_is_lowered(client, monkeypatch):
    openai_env(monkeypatch)
    fake_openai(monkeypatch, Stream(EVENTS + [completed(report(confidence_level="very_strong"), searches=(("completed", []),))]))
    r = wait(client, client.post("/ai-research", json=VERSE))["report"]
    assert r["confidence_level"] == "possible" and r["checks"]["downgraded_from"] == "very_strong"
    assert "خُفّض التقييم النهائي" in r["report_markdown"]


def test_failed_web_searches_are_reported_not_filled_in(client, monkeypatch):
    openai_env(monkeypatch)
    fake_openai(monkeypatch, Stream(EVENTS + [completed(report(), searches=(("failed", []), ("failed", [])))]))
    r = wait(client, client.post("/ai-research", json=VERSE))["report"]
    assert "لم يكتمل البحث الخارجي" in r["report_markdown"]
    assert r["checks"]["verified_sources"] == 0 and GOOD_URL not in r["report_markdown"]


@pytest.mark.parametrize("reply, message", [
    (Stream([], status=401, body={"error": {"message": "Incorrect API key provided: sk-test-kkkk"}}), "مفتاح OpenAI غير صالح"),
    (Stream([], status=404), "غير متاح لهذا الحساب"),
    (Stream([], status=429), "Rate limit"),
    (Stream([], status=400, body={"error": {"message": "Unsupported parameter: x"}}), "Unsupported parameter: x"),
    (Stream([{"type": "error", "message": "boom"}]), "boom"),
    (Stream([{"type": "response.incomplete", "response": {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}}]),
     "OPENAI_MAX_OUTPUT_TOKENS"),
    (Stream([{"type": "response.failed", "response": {"status": "failed", "error": {"message": "server_error"}}}]), "server_error"),
    (Stream([completed("لا أستطيع")]), "JSON"),
    (Stream([{"type": "response.completed", "response": {"status": "completed", "output": [
        {"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]}}]), "امتنع النموذج"),
    (Stream([completed(report(confidence_level="certain"))]), "تقييم نهائي صالح"),
    (Stream([{"type": "response.created"}]), "قبل اكتمال التقرير"),
])
def test_openai_failures_end_the_job_with_a_clear_message(client, db, monkeypatch, reply, message):  # noqa: F811
    openai_env(monkeypatch)
    sent = fake_openai(monkeypatch, reply)
    job = wait(client, client.post("/ai-research", json=VERSE))
    assert job["status"] == "failed" and message in job["error"], job
    assert KEY not in json.dumps(job) and "kkkk" not in json.dumps(job)   # the key never leaks
    assert db.query(AiReport).count() == 0
    if reply.status_code == 429:
        assert len(sent) == 3          # retried twice before giving up


def test_rate_limit_retry_then_success(client, monkeypatch):
    openai_env(monkeypatch)
    sent = fake_openai(monkeypatch, Stream([], status=429, headers={"retry-after": "1"}), Stream(EVENTS + [completed(report())]))
    assert wait(client, client.post("/ai-research", json=VERSE))["status"] == "done" and len(sent) == 2


def test_file_search_when_vector_stores_are_set(client, monkeypatch):
    openai_env(monkeypatch, OPENAI_VECTOR_STORE_IDS="vs_1, vs_2", OPENAI_WEB_SEARCH="0")
    files = {"type": "file_search_call", "status": "completed", "results": [{"file_id": "file_9", "filename": "lisan.pdf"}]}
    data = report(quranic_sources=[{"id": "lisan.pdf", "used_for": "اللغة"}])
    sent = fake_openai(monkeypatch, Stream([completed(data, searches=(), extra_output=[files])]))
    r = wait(client, client.post("/ai-research", json=VERSE))["report"]
    body = sent[0]["json"]
    assert body["tools"] == [{"type": "file_search", "vector_store_ids": ["vs_1", "vs_2"], "max_num_results": 8}]
    assert body["include"] == ["file_search_call.results"]
    assert [q["title"] for q in r["report"]["quranic_sources"]] == ["lisan.pdf"]
    assert "لم يُستعمل البحث على الإنترنت" in r["report_markdown"] and r["checks"]["verified_sources"] == 0


def test_same_research_is_not_started_twice_and_is_rate_limited(client, db, monkeypatch):  # noqa: F811
    openai_env(monkeypatch, AFAQ_AI_HOURLY_LIMIT="1")
    gate = __import__("threading").Event()

    class Slow(Stream):
        def iter_content(self, chunk_size=None):
            gate.wait(5)
            yield from super().iter_content(chunk_size)

    fake_openai(monkeypatch, Slow(EVENTS + [completed(report())]))
    first = client.post("/ai-research", json=VERSE)
    second = client.post("/ai-research", json=VERSE)
    assert second.status_code == 202 and second.json()["job_id"] == first.json()["job_id"]
    assert client.post("/ai-research", json={"surah_number": 25, "ayah_number": 53}).status_code == 429
    gate.set()
    assert wait(client, first)["status"] == "done"
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "mock")  # test mode is never limited
    assert client.post("/ai-research", json={"surah_number": 25, "ayah_number": 53}).status_code == 200


def test_unknown_job_is_404(client):
    assert client.get("/ai-research/jobs/nope").status_code == 404


def test_report_for_the_verse_page_never_generates(client, db, monkeypatch):  # noqa: F811
    openai_env(monkeypatch)
    monkeypatch.setattr(providers.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    assert client.get("/ai-research/report", params=VERSE).json()["report_markdown"] is None
    db.add(AiReport(surah_number=24, ayah_number=40, prompt_version=api.PROMPT_VERSION, model="gpt-6.1-sol",
                    report_markdown="# محفوظ", generated_at=api.dt.datetime(2026, 10, 5)))
    db.commit()
    r = client.get("/ai-research/report", params=VERSE).json()
    assert r["report_markdown"] == "# محفوظ" and r["saved"] and r["report"] is None
    assert client.get("/ai-research/report", params={"surah_number": 2, "ayah_number": 255}).status_code == 404


# -- other platforms --------------------------------------------------------------------------
class Plain:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_http_platform_has_no_web_search_so_no_link_survives(client, monkeypatch):
    monkeypatch.setenv("AFAQ_AI_PROVIDER", "http")
    monkeypatch.setenv("AFAQ_AI_API_URL", "https://ai.example/v1/chat/completions")
    monkeypatch.setenv("AFAQ_AI_API_KEY", KEY)
    monkeypatch.setenv("AFAQ_AI_MODEL", "m1")
    sent = {}

    def post(url, headers, json, timeout):
        sent.update(json=json)
        return Plain(200, {"choices": [{"message": {"content": "```json\n" + __import__("json").dumps(report(confidence_level="strong")) + "\n```"}}]})

    monkeypatch.setattr(providers.requests, "post", post)
    r = wait(client, client.post("/ai-research", json=VERSE))["report"]
    msgs = sent["json"]["messages"]
    assert msgs[0]["role"] == "system" and msgs[0]["content"].startswith(RESEARCH_PROMPT) and "confidence_level" in msgs[0]["content"]
    assert GOOD_URL not in r["report_markdown"] and r["confidence_level"] == "possible"
    assert "لم يُستعمل البحث على الإنترنت" in r["report_markdown"]


def test_url_normalisation():
    assert norm_url("https://www.NOAA.gov/a/?utm_source=openai#x") == norm_url("http://noaa.gov/a")
    assert norm_url("https://noaa.gov/a?id=2") != norm_url("https://noaa.gov/a?id=3")


def test_openai_plain_text_for_topic_search(monkeypatch):
    sent = []

    def post(url, json, stream, headers, timeout):
        sent.append(json)
        return Plain(200, {"output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": '{"verses": []}'}]}]})

    monkeypatch.setattr(providers.requests, "post", post)
    p = providers.OpenAIProvider({"OPENAI_API_KEY": KEY})
    assert p.generate("sys", "الموضوع: البحار", verse=None) == '{"verses": []}'
    assert sent[0]["instructions"] == "sys" and "tools" not in sent[0] and sent[0]["store"] is False


def test_daily_limit_covers_the_whole_site(client, monkeypatch):
    openai_env(monkeypatch, AFAQ_AI_HOURLY_LIMIT="0", AFAQ_AI_DAILY_LIMIT="1")
    fake_openai(monkeypatch, Stream(EVENTS + [completed(report())]))
    assert wait(client, client.post("/ai-research", json=VERSE))["status"] == "done"
    r = client.post("/ai-research", json={"surah_number": 25, "ayah_number": 53})
    assert r.status_code == 429 and "حده اليومي" in r.json()["detail"]
