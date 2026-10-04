"""HTTP endpoints of the «الذكاء الاصطناعي في الإعجاز العلمي» section."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
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
def research(req: ResearchRequest):
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
