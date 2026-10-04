"""HTTP endpoints of the «الذكاء الاصطناعي في الإعجاز العلمي» section."""
from __future__ import annotations

import datetime as dt
import os
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import SessionLocal
from ..models import AiReport, Verse
from ..trust import TrustCategory
from .prompt import PROMPT_VERSION, RESEARCH_PROMPT, verse_message
from .providers import ProviderError, get_provider

router = APIRouter(prefix="/ai-research", tags=["ai-research"])

DISCLAIMER = ("هذا التقرير من إنتاج نموذج ذكاء اصطناعي، وهو ادعاء غير موثق حتى يراجعه باحث: "
              "قد يخطئ في الحقائق العلمية أو ينسب إلى التفاسير ما لم تقله أو يذكر مصادر غير موجودة. "
              "تحقق من كل مصدر بنفسك قبل الاعتماد عليه، ولا تعدّه تفسيرًا للقرآن.")


# A connected platform is paid per report, so each client address gets a few reports per
# hour (AFAQ_AI_HOURLY_LIMIT, default 10; 0 = unlimited). Test mode is free and unlimited.
# Kept in memory: per process, reset on restart; enough to stop a script draining the account.
_recent: dict[str, deque] = defaultdict(deque)


def _check_rate(client: str) -> None:
    limit = int(os.environ.get("AFAQ_AI_HOURLY_LIMIT", "10") or 0)
    if limit <= 0:
        return
    now, q = time.monotonic(), _recent[client]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, f"بلغت حد التقارير لهذه الساعة ({limit}). حاول لاحقًا.")
    q.append(now)


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
    """Which platform the section uses (test mode until one is connected), and the prompt it sends."""
    info = _provider().info()
    return {"mode": info.mode, "provider": info.name, "model": info.model, "configured": info.configured,
            "missing_settings": info.missing, "prompt_version": PROMPT_VERSION, "prompt": RESEARCH_PROMPT}


def _verse(db, surah_number: int, ayah_number: int) -> dict:
    v = db.query(Verse).filter_by(surah_number=surah_number, ayah_number=ayah_number, reading="hafs").one_or_none()
    if v is None:
        raise HTTPException(404, "لم يتم العثور على هذه الآية في المصادر المعتمدة المستوعبة حتى الآن.")
    return {"surah_number": v.surah_number, "ayah_number": v.ayah_number, "surah_name": v.surah_name, "text": v.arabic_text}


def _response(verse: dict, info, report: str | None, generated_at: dt.datetime | None, saved: bool = False) -> dict:
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
        "report_markdown": report,
    }


def _saved(db, verse: dict, model: str | None) -> AiReport | None:
    return db.query(AiReport).filter_by(surah_number=verse["surah_number"], ayah_number=verse["ayah_number"],
                                        prompt_version=PROMPT_VERSION, model=model or "").one_or_none()


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
            report = provider.generate(RESEARCH_PROMPT, verse_message(verse["surah_name"], verse["surah_number"],
                                                                      verse["ayah_number"], verse["text"]), verse=verse)
            return _response(verse, info, report, dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))
        row = _saved(db, verse, info.model)
        return _response(verse, info, row.report_markdown if row else None, row.generated_at if row else None, bool(row))
    finally:
        db.close()


@router.post("")
def research(req: ResearchRequest, request: Request):
    provider = _provider()
    info = provider.info()
    db = SessionLocal()
    try:
        verse = _verse(db, req.surah_number, req.ayah_number)
        if info.mode == "live":
            row = _saved(db, verse, info.model)
            if row:  # already paid for: same verse, prompt and model
                return _response(verse, info, row.report_markdown, row.generated_at, saved=True)
            _check_rate(request.client.host if request.client else "unknown")
        try:
            report = provider.generate(RESEARCH_PROMPT, verse_message(verse["surah_name"], verse["surah_number"],
                                                                      verse["ayah_number"], verse["text"]), verse=verse)
        except ProviderError as e:
            raise HTTPException(502, str(e)) from e
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        if info.mode == "live":
            db.add(AiReport(surah_number=verse["surah_number"], ayah_number=verse["ayah_number"],
                            prompt_version=PROMPT_VERSION, model=info.model or "", report_markdown=report,
                            generated_at=now))
            db.commit()
        return _response(verse, info, report, now)
    finally:
        db.close()
