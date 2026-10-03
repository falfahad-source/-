import copy
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import main, review_api
from app.curation import load_document
from app.models import Relationship
from app.rag.answer_builder import build_answer
from app.reviews import (
    effective,
    export_to_curation,
    reviewer_for,
    reviewers_from_env,
    submit,
)
from tests.test_layers_answer import DOC, db  # noqa: F401 - db is a fixture

KEY = "24:40:zulumat->ocean_zones"
# naive UTC, as stored
T1 = dt.datetime(2026, 10, 3, 9, 0, tzinfo=dt.timezone.utc).replace(tzinfo=None)
T2 = dt.datetime(2026, 10, 3, 10, 0, tzinfo=dt.timezone.utc).replace(tzinfo=None)


def rel(db):  # noqa: F811
    return db.query(Relationship).filter_by(source_entity="phrase:24:40:zulumat",
                                            target_entity="concept:ocean_zones").one()


def link(db):  # noqa: F811
    a = build_answer(db, 24, 40)
    return next((c for c in a.possible_connections if c.get("concept") == "ocean_zones"), None)


@pytest.fixture()
def loaded(db):  # noqa: F811
    load_document(db, copy.deepcopy(DOC))
    return db


def test_reviewers_parsed_from_env_and_short_tokens_ignored():
    r = reviewers_from_env("د. أحمد:aaaaaaaaaaaaaaaa1234; short:abc ; bad")
    assert r == {"aaaaaaaaaaaaaaaa1234": "د. أحمد"}
    assert reviewer_for("aaaaaaaaaaaaaaaa1234", r) == "د. أحمد"
    assert reviewer_for("wrong-token-wrong-token", r) is None and reviewer_for(None, r) is None


def test_new_comparison_is_draft(loaded):
    assert effective(loaded, rel(loaded)).status == "draft"
    assert link(loaded)["review_status"] == "draft"


def test_approve_shows_reviewer_and_date(loaded):
    submit(loaded, rel(loaded), "د. أحمد", "approved", None, None, now=T1)
    c = link(loaded)
    assert (c["review_status"], c["reviewed_by"], c["reviewed_at"]) == ("approved", "د. أحمد", "2026-10-03")


def test_approve_with_edit_replaces_text_publicly(loaded):
    submit(loaded, rel(loaded), "د. أحمد", "approved", None, "نص معدّل من الباحث.", now=T1)
    assert link(loaded)["explanation"] == "نص معدّل من الباحث."


def test_reject_hides_comparison_and_requires_comment(loaded):
    with pytest.raises(ValueError, match="ملاحظة"):
        submit(loaded, rel(loaded), "د. أحمد", "rejected", "  ", None)
    submit(loaded, rel(loaded), "د. أحمد", "rejected", "ربط متكلف.", None, now=T1)
    assert link(loaded) is None


def test_changes_requested_stays_visible_as_not_approved(loaded):
    submit(loaded, rel(loaded), "د. أحمد", "changes_requested", "اذكر قول الطبري.", None, now=T1)
    assert link(loaded)["review_status"] == "changes_requested"


def test_latest_review_wins(loaded):
    submit(loaded, rel(loaded), "د. أحمد", "rejected", "لا", None, now=T1)
    submit(loaded, rel(loaded), "د. سارة", "approved", None, None, now=T2)
    assert link(loaded)["reviewed_by"] == "د. سارة"


def test_editing_the_curation_file_sends_it_back_to_draft(loaded):
    submit(loaded, rel(loaded), "د. أحمد", "approved", None, None, now=T1)
    doc = copy.deepcopy(DOC)
    next(c for c in doc["connections"] if c["concept"] == "ocean_zones")["explanation"] = "نص جديد لم يُراجع."
    load_document(loaded, doc)
    assert effective(loaded, rel(loaded)).status == "draft"


def test_review_survives_reloading_the_same_file(loaded):
    submit(loaded, rel(loaded), "د. أحمد", "approved", None, None, now=T1)
    load_document(loaded, copy.deepcopy(DOC))  # recreates Relationship rows
    assert effective(loaded, rel(loaded)).status == "approved"


def test_export_writes_decision_and_edit_into_curation_file(loaded, tmp_path):
    (tmp_path / "24-40.json").write_text(json.dumps(DOC, ensure_ascii=False), encoding="utf-8")
    submit(loaded, rel(loaded), "د. أحمد", "approved", None, "نص معتمد.", now=T1)
    assert export_to_curation(loaded, tmp_path) == 1
    out = json.loads((tmp_path / "24-40.json").read_text(encoding="utf-8"))
    c = next(c for c in out["connections"] if c["concept"] == "ocean_zones")
    assert (c["explanation"], c["review_status"], c["reviewed_by"], c["reviewed_at"]) == (
        "نص معتمد.", "approved", "د. أحمد", "2026-10-03")
    # reloading the exported file keeps it approved even without the DB review
    load_document(loaded, out)
    assert effective(loaded, rel(loaded)).status == "approved"
    assert export_to_curation(loaded, tmp_path) == 0  # nothing left to write


def test_api_requires_a_reviewer_token(loaded, monkeypatch):
    monkeypatch.setenv("AFAQ_REVIEWERS", "")
    c = TestClient(main.app)
    assert c.get("/review/me").status_code == 503
    monkeypatch.setenv("AFAQ_REVIEWERS", "د. أحمد:tok-ahmad-0123456789")
    assert c.get("/review/me").status_code == 401
    assert c.get("/review/me", headers={"Authorization": "Bearer nope-nope-nope-nope"}).status_code == 401
    assert c.get("/review/me", headers={"Authorization": "Bearer tok-ahmad-0123456789"}).json() == {"reviewer": "د. أحمد"}


def test_api_queue_and_decision(loaded, monkeypatch):
    monkeypatch.setenv("AFAQ_REVIEWERS", "د. أحمد:tok-ahmad-0123456789")
    factory = sessionmaker(bind=loaded.get_bind())
    monkeypatch.setattr(review_api, "SessionLocal", factory)
    c = TestClient(main.app)
    h = {"Authorization": "Bearer tok-ahmad-0123456789"}
    q = c.get("/review/queue", headers=h).json()
    item = next(i for i in q["items"] if i["key"] == KEY)
    assert item["status"] == "draft" and item["phrase"]["text"] == "ظُلُمَاتٌ بَعْضُهَا فَوْقَ بَعْضٍ"
    assert item["concept"]["claims"] and q["counts"]["draft"] == len(DOC["connections"])
    bad = c.post(f"/review/{KEY}", json={"decision": "rejected"}, headers=h)
    assert bad.status_code == 422
    ok = c.post(f"/review/{KEY}", json={"decision": "approved", "explanation": "نص معتمد."}, headers=h).json()
    assert ok["status"] == "approved" and ok["explanation"] == "نص معتمد." and ok["history"][0]["reviewer"] == "د. أحمد"
    assert c.get("/review/queue?status=approved", headers=h).json()["counts"]["approved"] == 1
    assert c.post("/review/1:1:x->y", json={"decision": "approved"}, headers=h).status_code == 404


def test_export_leaves_unreviewed_files_untouched(loaded, tmp_path):
    (tmp_path / "24-40.json").write_text(json.dumps(DOC, ensure_ascii=False), encoding="utf-8")
    before = (tmp_path / "24-40.json").read_text(encoding="utf-8")
    assert export_to_curation(loaded, tmp_path) == 0
    assert (tmp_path / "24-40.json").read_text(encoding="utf-8") == before
