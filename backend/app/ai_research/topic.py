"""Search by topic with the AI platform: the reader types a subject («ذكاء الإنسان») and the
model proposes the verses related to it, each with its reason.

A model can cite a verse that does not exist, or the wrong number for a real one, so it
must also quote words from each verse, and nothing it says about the Quran is shown
unchecked:
- the verse must exist, and the quote must be in it (diacritics, spelling variants and
  alif ignored: «السماوات» is the mushaf's «السموات»);
- if the quote is not in the cited verse but is in exactly one other verse (or in exactly
  one verse of the surah the model named), the reference is corrected and marked so;
- otherwise the suggestion is dropped, and the response counts what was dropped.
The verse text shown is always the stored KFGQPC text, never the model's. The reason is
the model's own words, labeled as such (UNVERIFIED_CLAIM).

In test mode (no platform connected yet) the section answers from the source-based topic
search (app.topic_search), and says so.
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Verse
from ..search import normalize_arabic
from ..topic_search import search_topics
from .providers import ProviderError, get_provider

PROMPT_VERSION = "2026-10-04"
MAX_VERSES = 20
MIN_QUOTE_LETTERS = 6

TOPIC_PROMPT = """أنت مساعد بحث في القرآن الكريم. سيكتب لك المستخدم موضوعًا، وعليك أن تذكر الآيات التي تتحدث عن هذا الموضوع أو تتصل به اتصالًا واضحًا، الأقوى صلة أولًا، بحد أقصى 20 آية.

قواعد إلزامية:
- لا تذكر آية إلا وأنت متأكد من رقم سورتها وآيتها.
- لكل آية انقل كلمات من نصها حرفيًا (من 3 إلى 8 كلمات متتالية)، فسيُتحقق منها آليًا، وتُحذف الآية إن لم يوجد الاقتباس فيها.
- اذكر سبب الصلة بالموضوع في جملة واحدة قصيرة، دون مبالغة ودون ادعاء إعجاز.
- إن لم تجد آيات متصلة بالموضوع فأعد قائمة فارغة.

أخرج JSON فقط، بلا أي نص قبله أو بعده، بهذا الشكل:
{"verses": [{"surah": 2, "ayah": 233, "quote": "والوالدات يرضعن أولادهن حولين كاملين", "reason": "تحدد مدة الرضاعة التامة بحولين."}]}"""

DISCLAIMER = ("هذه اقتراحات من نموذج ذكاء اصطناعي. تحقق آفاق من أن كل آية موجودة وأن الاقتباس منها، "
              "لكن صلتها بالموضوع رأي النموذج وليست تفسيرًا. افتح الآية لتقرأ تفسيرها الموثق.")
MOCK_NOTE = ("منصة الذكاء الاصطناعي لم تُربط بعد، فالنتائج مؤقتًا من البحث في مصادر آفاق "
             "(المقارنات العلمية، وموضوعات Quranpedia، ومقالات الإعجاز، والتفسير الميسر).")

# Answers of a connected (paid) platform are kept for repeated queries: same text, same
# prompt version, same result. Per process, cleared on restart.
_cache: OrderedDict[str, dict] = OrderedDict()
CACHE_SIZE = 200


def parse_suggestions(text: str) -> list[dict]:
    """The model's JSON, tolerating text or a code fence around it. Malformed items are skipped."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ProviderError("ردّ منصة الذكاء الاصطناعي ليس بالصيغة المتوقعة (JSON).")
    try:
        items = json.loads(m.group(0)).get("verses", [])
    except (ValueError, AttributeError) as e:
        raise ProviderError("ردّ منصة الذكاء الاصطناعي ليس بالصيغة المتوقعة (JSON).") from e
    out = []
    for it in items if isinstance(items, list) else []:
        try:
            out.append({"surah": int(it["surah"]), "ayah": int(it["ayah"]),
                        "quote": str(it.get("quote") or ""), "reason": str(it.get("reason") or "").strip()})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def skeleton(text: str) -> str:
    """Normalized text without alif, the letter Uthmani, imla'i and modern spelling disagree on
    most («السموات» / «السماوات», «الرحمن» / «الرحمان»); quotes are compared on this."""
    return normalize_arabic(text).replace("ا", "")


_index: list[tuple[int, int, tuple[str, ...]]] | None = None  # (surah, ayah, skeleton keys)
_index_stamp: tuple | None = None


def _verse_keys(db: Session) -> list[tuple[int, int, tuple[str, ...]]]:
    """Every verse's skeleton keys, rebuilt when the verses change (as app.search does)."""
    global _index, _index_stamp
    stamp = db.query(func.count(Verse.id), func.max(Verse.id)).filter(Verse.reading == "hafs").one()
    if _index is None or stamp != _index_stamp:
        _index = [(v.surah_number, v.ayah_number, _keys(v))
                  for v in db.query(Verse).filter_by(reading="hafs").order_by(Verse.surah_number, Verse.ayah_number)]
        _index_stamp = tuple(stamp)
    return _index


def _keys(v: Verse) -> tuple[str, ...]:
    return tuple(k for k in (skeleton(v.text_imlaei or ""), skeleton(v.arabic_text)) if k)


def verify(db: Session, suggestions: list[dict]) -> tuple[list[dict], int]:
    """(checked verses in the model's order, number dropped). See the module docstring."""
    out, seen, dropped = [], set(), 0
    for s in suggestions[:MAX_VERSES]:
        quote = skeleton(s["quote"])
        if len(quote.replace(" ", "")) < MIN_QUOTE_LETTERS:
            dropped += 1
            continue
        v = db.query(Verse).filter_by(surah_number=s["surah"], ayah_number=s["ayah"], reading="hafs").one_or_none()
        corrected = False
        if v is None or not any(quote in k for k in _keys(v)):
            # the quote elsewhere: one verse, or one in the surah the model named
            found = [(su, ay) for su, ay, keys in _verse_keys(db) if any(quote in k for k in keys)]
            if len(found) > 1:
                found = [f for f in found if f[0] == s["surah"]]
            if len(found) != 1:
                dropped += 1
                continue
            v = db.query(Verse).filter_by(surah_number=found[0][0], ayah_number=found[0][1], reading="hafs").one()
            corrected = True
        if (v.surah_number, v.ayah_number) in seen:
            continue
        seen.add((v.surah_number, v.ayah_number))
        out.append({"surah_number": v.surah_number, "ayah_number": v.ayah_number, "surah_name": v.surah_name,
                    "text": v.arabic_text, "page_number": v.page_number,
                    "reasons": [{"kind": "ai", "label": s["reason"] or "اقترحها النموذج دون ذكر سبب.",
                                 "url": None, "coverage": 1.0, "synonyms": []}],
                    "more_reasons": 0, "quote": s["quote"], "corrected": corrected})
    return out, dropped


def ai_topic_search(db: Session, q: str, limit: int = 50, offset: int = 0, rate_check=None) -> dict:
    q = q.strip()
    if len(normalize_arabic(q).replace(" ", "")) < 3:
        raise ValueError("اكتب موضوعًا من ثلاثة أحرف على الأقل، مثل: ذكاء الإنسان، الرضاعة، البحار.")
    provider = get_provider()
    info = provider.info()
    if info.mode == "mock":
        r = search_topics(db, q, limit, offset)
        return {**r, "mode": "mock", "note": MOCK_NOTE, "dropped": 0, "disclaimer": None}

    key = normalize_arabic(q)
    if key not in _cache:
        if rate_check:
            rate_check()
        text = provider.generate(TOPIC_PROMPT, f"الموضوع: {q}", verse=None)
        results, dropped = verify(db, parse_suggestions(text))
        _cache[key] = {"results": results, "dropped": dropped, "model": info.model}
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    else:
        _cache.move_to_end(key)
    hit = _cache[key]
    return {"query": q, "words": [], "total": len(hit["results"]), "offset": offset,
            "results": hit["results"][offset: offset + limit], "mode": "live", "model": hit["model"],
            "prompt_version": PROMPT_VERSION, "dropped": hit["dropped"], "note": None,
            "disclaimer": DISCLAIMER, "trust_category": "UNVERIFIED_CLAIM"}
