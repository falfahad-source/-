"""HTTP endpoints of the «الذكاء الاصطناعي في الإعجاز العلمي» section."""
from __future__ import annotations

import datetime as dt
import os
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import SessionLocal
from ..models import Verse
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


@router.post("")
def research(req: ResearchRequest, request: Request):
    db = SessionLocal()
    try:
        v = (db.query(Verse)
             .filter_by(surah_number=req.surah_number, ayah_number=req.ayah_number, reading="hafs")
             .one_or_none())
        if v is None:
            raise HTTPException(404, "لم يتم العثور على هذه الآية في المصادر المعتمدة المستوعبة حتى الآن.")
        verse = {"surah_number": v.surah_number, "ayah_number": v.ayah_number,
                 "surah_name": v.surah_name, "text": v.arabic_text}
    finally:
        db.close()

    provider = _provider()
    info = provider.info()
    if info.mode == "live":
        _check_rate(request.client.host if request.client else "unknown")
    try:
        report = provider.generate(RESEARCH_PROMPT, verse_message(verse["surah_name"], verse["surah_number"],
                                                                  verse["ayah_number"], verse["text"]), verse=verse)
    except ProviderError as e:
        raise HTTPException(502, str(e)) from e
    return {
        "verse": verse,
        "mode": info.mode,
        "provider": info.name,
        "model": info.model,
        "prompt_version": PROMPT_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "trust_category": TrustCategory.UNVERIFIED_CLAIM.value,
        "disclaimer": DISCLAIMER,
        "report_markdown": report,
    }
