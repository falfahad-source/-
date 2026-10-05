"""HTTP endpoints of the «الذكاء الاصطناعي في الإعجاز العلمي» section.

A real research run (reasoning model + web searches) takes minutes, longer than a browser
request should stay open, so POST /ai-research starts a job and answers 202 with its id;
GET /ai-research/jobs/{id} gives its stages while it runs, then the report. Test mode and
stored reports answer at once (200). Jobs live in this process's memory; a stored report is
in the ai_reports table, paid for once per verse, prompt version and model.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import SessionLocal
from ..models import AiReport, Verse
from ..trust import TrustCategory
from .context import source_pack
from .prompt import PROMPT_VERSION, RESEARCH_PROMPT, verse_message
from .providers import ProviderError, get_provider
from .report import CONFIDENCE_AR, check, render, searches_ar
from .schema import REPORT_SCHEMA

router = APIRouter(prefix="/ai-research", tags=["ai-research"])

DISCLAIMER = ("هذا التقرير من إنتاج نموذج ذكاء اصطناعي، وهو ادعاء غير موثق حتى يراجعه باحث. تحقق آفاق آليًا من أن "
              "المصادر القرآنية من المصادر المرسلة إليه، وأن روابط المصادر العلمية ظهرت فعلًا في نتائج بحثه، لكن "
              "صحة ما نسبه إليها وتقييمه للعلاقة رأي النموذج. تحقق من المصادر بنفسك، ولا تعدّه تفسيرًا للقرآن.")

STAGES = [("context", "مراجعة المصادر القرآنية والتفسيرية"), ("analysis", "تحليل الآية وتحديد الظاهرة العلمية"),
          ("web", "البحث في المصادر العلمية"), ("writing", "مقارنة الأدلة ونقدها وإعداد التقرير"),
          ("verify", "التحقق من المصادر")]


# A connected platform is paid per report, so each client address gets a few reports per
# hour (AFAQ_AI_HOURLY_LIMIT, default 10; 0 = unlimited). Test mode is free and unlimited.
# Kept in memory: per process, reset on restart; enough to stop a script draining the account.
# On a public site the key's owner also needs a ceiling for everyone together:
# AFAQ_AI_DAILY_LIMIT reports per 24 hours for the whole site (default 50; 0 = unlimited).
_recent: dict[str, deque] = defaultdict(deque)
_ALL = "*all*"


def _check_rate(client: str) -> None:
    hourly = int(os.environ.get("AFAQ_AI_HOURLY_LIMIT", "10") or 0)
    daily = int(os.environ.get("AFAQ_AI_DAILY_LIMIT", "50") or 0)
    now, q, everyone = time.monotonic(), _recent[client], _recent[_ALL]
    while q and now - q[0] > 3600:
        q.popleft()
    while everyone and now - everyone[0] > 86400:
        everyone.popleft()
    if hourly > 0 and len(q) >= hourly:
        raise HTTPException(429, f"بلغت حد التقارير لهذه الساعة ({hourly}). حاول لاحقًا.")
    if daily > 0 and len(everyone) >= daily:
        raise HTTPException(429, "بلغ الموقع حده اليومي من تقارير الذكاء الاصطناعي. حاول غدًا.")
    q.append(now)
    everyone.append(now)


class ResearchRequest(BaseModel):
    surah_number: int = Field(ge=1, le=114)
    ayah_number: int = Field(ge=1, le=286)


def _provider():
    try:
        return get_provider()
    except ProviderError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/status")
def status():
    """Which platform the section uses (test mode until one is connected), its tools, and the
    instructions it sends."""
    info = _provider().info()
    return {"mode": info.mode, "provider": info.name, "model": info.model, "configured": info.configured,
            "missing_settings": info.missing, "tools": info.tools, "prompt_version": PROMPT_VERSION,
            "prompt": RESEARCH_PROMPT}


def _verse(db, surah_number: int, ayah_number: int) -> dict:
    v = db.query(Verse).filter_by(surah_number=surah_number, ayah_number=ayah_number, reading="hafs").one_or_none()
    if v is None:
        raise HTTPException(404, "لم يتم العثور على هذه الآية في المصادر المعتمدة المستوعبة حتى الآن.")
    return {"surah_number": v.surah_number, "ayah_number": v.ayah_number, "surah_name": v.surah_name, "text": v.arabic_text}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _response(verse: dict, info, markdown: str | None, report: dict | None, generated_at: dt.datetime | None,
              saved: bool = False) -> dict:
    level = (report or {}).get("confidence_level")
    return {
        "verse": verse,
        "mode": info.mode,
        "provider": info.name,
        "model": info.model,
        "prompt_version": PROMPT_VERSION,
        "generated_at": generated_at.replace(tzinfo=dt.timezone.utc).isoformat(timespec="seconds") if generated_at else None,
        "saved": saved,  # a stored report of a connected platform, not generated just now
        "trust_category": TrustCategory.UNVERIFIED_CLAIM.value,
        "disclaimer": DISCLAIMER,
        "report_markdown": markdown,
        "confidence_level": level,
        "confidence_label": CONFIDENCE_AR.get(level) if level else None,
        "checks": {k: v for k, v in ((report or {}).get("checks") or {}).items() if k != "verified_links"} or None,
        "report": report,
    }


def _saved(db, verse: dict, model: str | None) -> AiReport | None:
    return db.query(AiReport).filter_by(surah_number=verse["surah_number"], ayah_number=verse["ayah_number"],
                                        prompt_version=PROMPT_VERSION, model=model or "").one_or_none()


def _from_row(verse: dict, info, row: AiReport) -> dict:
    report = json.loads(row.report_json) if row.report_json else None
    return _response(verse, info, row.report_markdown, report, row.generated_at, saved=True)


def _mock(provider, info, verse: dict) -> dict:
    data = provider.research(RESEARCH_PROMPT, "", REPORT_SCHEMA, verse=verse).data
    return _response(verse, info, render(data, verse, mock=True), None, _now())


@router.get("/report")
def saved_report(surah_number: int = Query(ge=1, le=114), ayah_number: int = Query(ge=1, le=286)):
    """The verse's report without generating a paid one: in test mode the (free) test report,
    with a connected platform the stored report if there is one, else report_markdown null.
    The verse page shows this with the other layers; POST generates on request."""
    provider = _provider()
    info = provider.info()
    db = SessionLocal()
    try:
        verse = _verse(db, surah_number, ayah_number)
        if info.mode == "mock":
            return _mock(provider, info, verse)
        row = _saved(db, verse, info.model)
        return _from_row(verse, info, row) if row else _response(verse, info, None, None, None)
    finally:
        db.close()


# -- jobs -------------------------------------------------------------------------------
class Job:
    def __init__(self, key: tuple, verse: dict):
        self.id = uuid.uuid4().hex
        self.key, self.verse = key, verse
        self.status = "running"            # running | done | failed
        self.stages = {k: "pending" for k, _ in STAGES}
        self.searches = 0
        self.result: dict | None = None
        self.error: str | None = None
        self.started = time.monotonic()
        self.finished: float | None = None
        self.lock = threading.Lock()

    def stage(self, key: str, state: str = "active") -> None:
        """Mark `key` active (and every earlier stage done), or set it to `state`."""
        with self.lock:
            if state != "active":
                self.stages[key] = state
                return
            for k, _ in STAGES:
                if k == key:
                    break
                if self.stages[k] in ("pending", "active"):
                    self.stages[k] = "skipped" if k == "web" and self.searches == 0 else "done"
            self.stages[key] = "active"

    def on_event(self, kind: str, detail: dict) -> None:
        if kind == "started":
            self.stage("analysis")
        elif kind in ("web_search", "file_search"):
            if kind == "web_search" and detail.get("status") == "completed":
                with self.lock:
                    self.searches += 1
            if self.stages["writing"] == "pending":
                self.stage("web" if kind == "web_search" else "analysis")
        elif kind == "writing" and self.stages["writing"] == "pending":
            self.stage("writing")

    def view(self) -> dict:
        with self.lock:
            out = {"job_id": self.id, "status": self.status, "searches": self.searches,
                   "elapsed": round((self.finished or time.monotonic()) - self.started),
                   "stages": [{"key": k, "label": label + (f" ({searches_ar(self.searches)})" if k == "web" and self.searches else ""),
                               "state": self.stages[k]} for k, label in STAGES]}
        if self.status == "done":
            out["report"] = self.result
        if self.status == "failed":
            out["error"] = self.error
        return out


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()
JOB_TTL = 3600


def _run(job: Job, provider, info) -> None:
    db = SessionLocal()
    try:
        job.stage("context")
        pack = source_pack(db, job.verse["surah_number"], job.verse["ayah_number"])
        result = provider.research(RESEARCH_PROMPT, verse_message(job.verse, pack), REPORT_SCHEMA,
                                   verse=job.verse, on_event=job.on_event)
        job.stage("verify")
        report = check(result.data, result, pack)
        markdown = render(report, job.verse)
        now = _now()
        if not _saved(db, job.verse, info.model):
            db.add(AiReport(surah_number=job.verse["surah_number"], ayah_number=job.verse["ayah_number"],
                            prompt_version=PROMPT_VERSION, model=info.model or "", report_markdown=markdown,
                            report_json=json.dumps(report, ensure_ascii=False), generated_at=now))
            db.commit()
        with job.lock:
            job.stages = {k: "skipped" if k == "web" and job.searches == 0 else "done" for k in job.stages}
            job.result = _response(job.verse, info, markdown, report, now)
            job.status = "done"
    except ProviderError as e:
        with job.lock:
            job.error, job.status = str(e), "failed"
    except Exception:  # noqa: BLE001 - a job must always end, and never with internals in the message
        with job.lock:
            job.error, job.status = "حدث خطأ غير متوقع أثناء إعداد التقرير.", "failed"
    finally:
        job.finished = time.monotonic()
        db.close()


@router.post("")
def research(req: ResearchRequest, request: Request):
    provider = _provider()
    info = provider.info()
    db = SessionLocal()
    try:
        verse = _verse(db, req.surah_number, req.ayah_number)
        if info.mode == "mock":
            return _mock(provider, info, verse)
        if not info.configured:
            raise HTTPException(502, "منصة الذكاء الاصطناعي غير مكتملة الإعداد: " + "، ".join(info.missing))
        row = _saved(db, verse, info.model)
        if row:  # already paid for: same verse, prompt and model
            return _from_row(verse, info, row)
    finally:
        db.close()
    key = (verse["surah_number"], verse["ayah_number"], PROMPT_VERSION, info.model or "")
    with _jobs_lock:
        now = time.monotonic()
        for jid in [j for j, job in _jobs.items() if job.finished and now - job.finished > JOB_TTL]:
            del _jobs[jid]
        running = next((j for j in _jobs.values() if j.key == key and j.status == "running"), None)
        if running:  # the same research is already under way: follow it, don't pay twice
            return _accepted(running)
        _check_rate(request.client.host if request.client else "unknown")
        job = Job(key, verse)
        _jobs[job.id] = job
    threading.Thread(target=_run, args=(job, provider, info), name=f"ai-research-{job.id[:8]}", daemon=True).start()
    return _accepted(job)


def _accepted(job: Job):
    from fastapi.responses import JSONResponse
    return JSONResponse(job.view(), status_code=202)


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "لم يُعثر على هذا البحث؛ ربما أعيد تشغيل الخادم. ابدأ البحث من جديد.")
    return job.view()
