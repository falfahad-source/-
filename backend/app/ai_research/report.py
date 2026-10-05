"""Checks a research report before anyone reads it, then renders it as the Arabic report.

What the model says is never trusted where it can be checked:
- Quranic and tafsir sources: only ids of the pack AFAQ sent (or files File Search
  returned) are kept, and their names come from AFAQ's records, not from the model.
- Scientific sources: a link is shown only if Web Search actually returned or opened that
  page in this research (OpenAI's own list, `web_search_call.action.sources`). Any other
  link, in the source list or inside the text, is removed and the source marked unverified.
- A «very strong» or «strong» verdict with no verified scientific source is lowered to
  «possible»: the evidence shown must be able to carry the verdict.
- Failed or missing web searches are stated in the report, never filled in from memory.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .providers import ProviderError, ResearchResult
from .schema import (CLAIM_VERDICT, CONFIDENCE, CONSENSUS, CRITIQUE, KNOWN_BEFORE, LINK_KIND, MATCH_VERDICT,
                     REPORT_SCHEMA, SOURCE_TYPE)

CONFIDENCE_AR = {
    "very_strong": "قوي جدًا (Very Strong)", "strong": "قوي (Strong)", "possible": "ممكن (Possible)",
    "weak": "ضعيف (Weak)", "unsupported": "غير مدعوم (Unsupported)", "contradicted": "تعارضه الأدلة (Contradicted)",
    "no_claim": "لا يوجد ادعاء علمي قابل للدراسة",
}
CLAIM_AR = {"supported": "مدعوم علميًا", "partially_supported": "مدعوم جزئيًا", "unsupported": "غير مدعوم",
            "contradicted": "تعارضه الأدلة", "not_applicable": "لا ينطبق"}
MATCH_AR = {"precise": "تطابق دقيق", "general": "تطابق عام", "needs_interpretation": "يحتاج إلى تأويل",
            "far_fetched": "تأويل بعيد", "not_applicable": "لا ينطبق"}
LINK_AR = {"direct": "علاقة مباشرة", "needs_interpretation": "تحتاج إلى تأويل", "far_fetched": "تحتاج إلى تأويل بعيد",
           "not_applicable": "لا ينطبق"}
CONSENSUS_AR = {"established": "حقيقة علمية راسخة", "broad_consensus": "إجماع علمي واسع", "debated": "محل نقاش علمي",
                "emerging": "معرفة ناشئة", "not_supported": "غير مدعوم علميًا", "not_applicable": "لا ينطبق"}
KNOWN_AR = {"yes": "نعم، كانت معروفة", "partially": "عُرفت جزئيًا", "no_evidence_found": "لم يُعثر على دليل أنها كانت معروفة",
            "unclear": "غير واضح", "not_applicable": "لا ينطبق"}
TYPE_AR = {"peer_reviewed": "دراسة محكمة", "systematic_review": "مراجعة منهجية", "institution": "مؤسسة علمية",
           "academic_book": "كتاب أكاديمي", "database": "قاعدة بيانات علمية", "specialist_article": "مقال علمي متخصص",
           "science_journalism": "صحافة علمية", "general_website": "موقع عام", "ijaz_website": "موقع إعجاز (ليس مصدرًا لإثبات الحقيقة)"}
CRITIQUE_AR = {"overinterpretation": "تأويل زائد", "anachronism": "إسقاط زمني", "confirmation_bias": "انحياز تأكيدي",
               "selective_evidence": "انتقاء الأدلة", "alternative_interpretation": "تفسير بديل للنص",
               "alternative_scientific_explanation": "تفسير علمي بديل", "weak_scientific_evidence": "ضعف الدليل العلمي",
               "weak_historical_argument": "ضعف الحجة التاريخية", "linguistic_problem": "مشكلة لغوية",
               "translation_problem": "مشكلة ترجمة", "unestablished_claim": "ادعاء غير مثبت علميًا", "other": "ملاحظة"}
STRONG = ("very_strong", "strong")


def ar(n) -> str:
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def searches_ar(n: int) -> str:
    """«عملية بحث» with Arabic number agreement."""
    if n == 1:
        return "عملية بحث واحدة"
    if n == 2:
        return "عمليتا بحث"
    return f"{ar(n)} عمليات بحث" if 3 <= n % 100 <= 10 else f"{ar(n)} عملية بحث"
URL = re.compile(r"https?://[^\s)\]<>\"'،]+")


def norm_url(url: str) -> str:
    """The same page, however it is written: scheme, «www.», case of the host, a trailing
    slash, a fragment and tracking parameters (OpenAI adds utm_source=openai) do not matter."""
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    host = (p.hostname or "").lower().removeprefix("www.")
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")])
    return urlunsplit(("", host, p.path.rstrip("/"), query, "")).lstrip("/")


def display_url(url: str, full: bool = False) -> str:
    """The link without tracking parameters; `full` for the href, else the site name to show."""
    p = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")])
    clean = urlunsplit((p.scheme, p.netloc, p.path, query, p.fragment)).replace(")", "%29").replace(" ", "%20")
    return clean if full else (p.hostname or url).removeprefix("www.")


# -- checks -----------------------------------------------------------------------------
_DEFAULTS = {"string": "", "array": []}
_ENUMS = {"link_kind": LINK_KIND, "scientific_consensus": CONSENSUS, "known_before_revelation": KNOWN_BEFORE}


def _complete(data: dict) -> dict:
    """A platform without Structured Outputs (http) may omit fields: fill them so the report
    renders, and refuse a reply without a valid verdict."""
    out = {}
    for key, spec in REPORT_SCHEMA["properties"].items():
        v = data.get(key)
        t = spec.get("type")
        if key in _ENUMS:
            v = v if v in _ENUMS[key] else "not_applicable"
        elif key in ("scientific_claim_assessment", "correspondence_assessment"):
            allowed = CLAIM_VERDICT if key == "scientific_claim_assessment" else MATCH_VERDICT
            v = v if isinstance(v, dict) else {}
            v = {"verdict": v.get("verdict") if v.get("verdict") in allowed else "not_applicable", "reason": str(v.get("reason") or "")}
        elif t == ["string", "null"]:
            v = v if isinstance(v, str) and v.strip() else None
        elif t == "array":
            v = [x for x in v if isinstance(x, (dict, str))] if isinstance(v, list) else []
        elif t == "string" and key != "confidence_level":
            v = str(v) if v is not None else ""
        out[key] = v
    if out["confidence_level"] not in CONFIDENCE:
        raise ProviderError("ردّ منصة الذكاء الاصطناعي بلا تقييم نهائي صالح.")
    out["critical_analysis"] = [c for c in out["critical_analysis"] if isinstance(c, dict)]
    for c in out["critical_analysis"]:
        c["issue"] = c.get("issue") if c.get("issue") in CRITIQUE else "other"
    for s in out["scientific_sources"]:
        if isinstance(s, dict) and s.get("source_type") not in SOURCE_TYPE:
            s["source_type"] = "general_website"
    return out


def check(data: dict, result: ResearchResult, pack: list[dict]) -> dict:
    """The report with every source checked, plus `checks`: what was verified and what was not."""
    r = _complete(data)
    warnings: list[str] = []
    pack_by_id = {s["id"]: s for s in pack}
    files_by_name = {name: fid for fid, name in result.files.items()}

    quranic = []
    for q in r["quranic_sources"]:
        if not isinstance(q, dict):
            continue
        sid = str(q.get("id") or "").strip()
        if sid in pack_by_id:
            s = pack_by_id[sid]
            quranic.append({"id": sid, "title": s["title"], "kind": s["kind_label"], "author": s.get("author"),
                            "used_for": str(q.get("used_for") or "")})
        elif sid in files_by_name or sid in result.files:
            quranic.append({"id": sid, "title": result.files.get(sid, sid), "kind": "ملف مرجعي (File Search)",
                            "author": None, "used_for": str(q.get("used_for") or "")})
        elif sid:
            warnings.append(f"ذكر النموذج مصدرًا قرآنيًا ({sid}) ليس في المصادر المرسلة إليه، فحُذف.")
    r["quranic_sources"] = quranic

    consulted = {norm_url(u) for u in result.consulted_urls}
    scientific, verified_links = [], set()
    for s in r["scientific_sources"]:
        if not isinstance(s, dict):
            continue
        url = str(s.get("url") or "").strip()
        ok = bool(url) and re.match(r"https?://", url) is not None and norm_url(url) in consulted
        if ok:
            verified_links.add(norm_url(url))
        scientific.append({"id": str(s.get("id") or "").strip(), "title": str(s.get("title") or "").strip() or "(بلا عنوان)",
                           "authors_or_institution": s.get("authors_or_institution") or None, "year": s.get("year") or None,
                           "url": url if ok else None, "verified": ok, "source_type": s["source_type"],
                           "used_for": str(s.get("used_for") or "")})
    r["scientific_sources"] = scientific
    unverified = [s for s in scientific if not s["verified"]]
    if unverified:
        warnings.append(f"{ar(len(unverified))} من المصادر العلمية لم تظهر في نتائج البحث الفعلية لهذا التقرير، "
                        "فحُذفت روابطها وعُلّمت «غير متحقق منه».")

    known_ids = set(pack_by_id) | {s["id"] for s in scientific if s["id"]} | set(result.files) | set(files_by_name)
    for key in ("supporting_evidence", "counter_evidence", "key_words"):
        items = []
        for e in r[key]:
            if not isinstance(e, dict):
                continue
            ids = [str(i).strip() for i in e.get("source_ids") or [] if str(i).strip()]
            e["source_ids"] = [i for i in ids if i in known_ids]
            e["unknown_ids"] = [i for i in ids if i not in known_ids]
            items.append(e)
        r[key] = items

    if not result.web_search:
        warnings.append("لم يُستعمل البحث على الإنترنت في هذا التقرير (المنصة المتصلة لا تملكه أو عُطّل)، "
                        "فلا يحتوي على مصادر علمية متحقق منها.")
    elif result.searches == 0:
        warnings.append("لم يُجرِ النموذج أي بحث على الإنترنت في هذا التقرير.")
    elif result.failed_searches == result.searches:
        warnings.append("لم يكتمل البحث الخارجي: فشلت كل عمليات البحث على الإنترنت.")
    elif result.failed_searches:
        warnings.append(f"فشلت {ar(result.failed_searches)} من {searches_ar(result.searches)} على الإنترنت.")

    downgraded = None
    verified_count = sum(s["verified"] for s in scientific)
    if r["confidence_level"] in STRONG and verified_count == 0:
        downgraded = r["confidence_level"]
        r["confidence_level"] = "possible"
        warnings.append(f"خُفّض التقييم النهائي من «{CONFIDENCE_AR[downgraded]}» إلى «{CONFIDENCE_AR['possible']}» "
                        "لأنه لا يستند إلى أي مصدر علمي متحقق منه.")

    r["checks"] = {"web_search": result.web_search, "searches": result.searches, "failed_searches": result.failed_searches,
                   "pages_consulted": len(consulted), "verified_sources": verified_count, "unverified_sources": len(unverified),
                   "downgraded_from": downgraded, "warnings": warnings, "verified_links": sorted(verified_links),
                   "usage": _usage(result.usage)}
    return r


def _usage(u: dict | None) -> dict | None:
    """Token counts of the research (input, cached input, output, of which reasoning), for cost."""
    if not isinstance(u, dict):
        return None
    return {"input_tokens": u.get("input_tokens"), "cached_input_tokens": (u.get("input_tokens_details") or {}).get("cached_tokens"),
            "output_tokens": u.get("output_tokens"), "reasoning_tokens": (u.get("output_tokens_details") or {}).get("reasoning_tokens")}


# -- rendering --------------------------------------------------------------------------
def _clean(text, allowed: set[str]) -> str:
    """Model text as safe Markdown: links it did not visit removed, one paragraph per block,
    no line read as a heading, list, table or quote."""
    text = URL.sub(lambda m: display_url(m.group(0), full=True) if norm_url(m.group(0)) in allowed
                   else "[رابط غير متحقق حُذف]", str(text or ""))
    lines = [re.sub(r"^\s*(#+|>|[-*•]|\d+[.)]|\|)\s*", "", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln) or "—"


def _cell(text, allowed) -> str:
    return _clean(text, allowed).replace("\n", " ").replace("|", "/")


def _refs(e: dict) -> str:
    ids = e.get("source_ids") or []
    bad = e.get("unknown_ids") or []
    out = f" [{'، '.join(ids)}]" if ids else ""
    if bad:
        out += f" _(مصدر غير موجود: {'، '.join(bad)})_"
    if not ids and not bad:
        out += " _(بلا مصدر)_"
    return out


def render(r: dict, verse: dict, mock: bool = False) -> str:
    """The report as the reader sees it, in the order of the project's specification."""
    allowed = set((r.get("checks") or {}).get("verified_links") or [])
    c = lambda t: _clean(t, allowed)  # noqa: E731
    level = r.get("confidence_level")
    md = [f"# تقرير الباحث الآلي — سورة {verse['surah_name']}، الآية {ar(verse['ayah_number'])}", ""]
    if mock:
        md += ["> **هذا تقرير تجريبي وليس بحثًا.** منصة الذكاء الاصطناعي لم تُربط بعد، فهذا القالب يبيّن شكل التقرير فقط، "
               "ولا يحتوي على أي نتيجة علمية أو تفسيرية أو مصدر حقيقي.", ""]
    md += [f"**التقييم النهائي: {CONFIDENCE_AR.get(level, '— (تجريبي)')}**", ""]
    if not mock:
        md += [c(r["final_assessment"]), ""]

    # the verse itself is shown above the report, in the mushaf font, from AFAQ's stored text
    md += ["## الآية", f"سورة {verse['surah_name']}، الآية {ar(verse['ayah_number'])} (نصها معروض أعلى التقرير من مصحف المجمع).", ""]

    md += ["## الظاهرة العلمية محل الدراسة"]
    if r.get("scientific_topic") or mock:
        md += [f"**الظاهرة:** {c(r.get('scientific_topic'))}", "",
               f"**الادعاء العلمي المدروس:** {c(r.get('potential_claim'))}", "",
               f"**الجزء المرتبط من الآية:** {c(r.get('related_text'))}", "",
               f"**نوع العلاقة:** {LINK_AR.get(r.get('link_kind'), '—')}", ""]
    else:
        md += ["لم يجد البحث في الآية ظاهرة علمية واضحة قابلة للدراسة.", ""]

    md += ["## ماذا يقول النص؟", c(r.get("quranic_context")), ""]
    if r.get("key_words"):
        md += ["**الكلمات المهمة:**"] + [f"- **{_cell(k.get('word'), allowed)}:** {_cell(k.get('meaning'), allowed)}{_refs(k)}"
                                        for k in r["key_words"]] + [""]
    md += [f"**حدود ما يحتمله النص:** {c(r.get('interpretive_boundaries'))}", ""]
    if r.get("alternative_readings"):
        md += ["**معانٍ أخرى محتملة للنص:**"] + [f"- {_cell(x, allowed)}" for x in r["alternative_readings"]] + [""]

    md += ["## ماذا يقول العلم الحديث؟", c(r.get("scientific_background")), "",
           f"**مستوى الإجماع العلمي:** {CONSENSUS_AR.get(r.get('scientific_consensus'), '—')}"
           + (f" — {_cell(r['consensus_note'], allowed)}" if r.get("consensus_note") else ""), ""]
    md += ["## تاريخ المعرفة العلمية", c(r.get("historical_background")), "",
           f"**هل كانت معروفة قبل نزول القرآن؟** {KNOWN_AR.get(r.get('known_before_revelation'), '—')}", ""]
    md += ["## المقارنة", c(r.get("comparison")), ""]

    for title, key, empty in (("الأدلة المؤيدة", "supporting_evidence", "لم تُذكر أدلة مؤيدة."),
                              ("الأدلة المعارضة والقيود", "counter_evidence", "لم تُذكر أدلة معارضة.")):
        md += [f"## {title}"] + ([f"- {_cell(e.get('point'), allowed)}{_refs(e)}" for e in r.get(key) or []] or [empty]) + [""]
    md += ["## التفسيرات البديلة"] + ([f"- {_cell(x, allowed)}" for x in r.get("alternative_explanations") or []]
                                     or ["لم تُذكر تفسيرات بديلة."]) + [""]
    md += ["## النقد"] + ([f"- **{CRITIQUE_AR[x['issue']]}:** {_cell(x.get('note'), allowed)}" for x in r.get("critical_analysis") or []]
                          or ["لم تُذكر اعتراضات."]) + [""]

    sca, ca = r.get("scientific_claim_assessment") or {}, r.get("correspondence_assessment") or {}
    md += ["## التقييم", "| الخطوة | الحكم | السبب |", "|---|---|---|",
           f"| الادعاء العلمي | {CLAIM_AR.get(sca.get('verdict'), '—')} | {_cell(sca.get('reason'), allowed)} |",
           f"| التطابق مع النص القرآني | {MATCH_AR.get(ca.get('verdict'), '—')} | {_cell(ca.get('reason'), allowed)} |",
           f"| التقييم النهائي | **{CONFIDENCE_AR.get(level, '—')}** | {_cell(r.get('final_assessment'), allowed)} |", ""]

    if r.get("hypotheses"):
        md += ["## فرضيات بحثية (ليست حقائق ولا إعجازًا مثبتًا)"] + [f"- {_cell(x, allowed)}" for x in r["hypotheses"]] + [""]
    gaps = [*(r.get("research_gaps") or []), *((r.get("checks") or {}).get("warnings") or [])]
    if gaps:
        md += ["## حدود هذا البحث"] + [f"- {_cell(x, allowed)}" for x in gaps] + [""]

    md += ["## المصادر", "### المصادر القرآنية والتفسيرية"]
    md += [f"- **[{q['id']}] {q['title']}** ({q['kind']}{'، ' + q['author'] if q.get('author') else ''}): {_cell(q.get('used_for'), allowed)}"
           for q in r.get("quranic_sources") or []] or ["لا توجد."]
    md += ["", "### المصادر العلمية"]
    for s in r.get("scientific_sources") or []:
        meta = "، ".join(x for x in (s.get("authors_or_institution"), s.get("year"), TYPE_AR.get(s.get("source_type"), "")) if x)
        link = (f" — [{display_url(s['url'])}]({display_url(s['url'], full=True)})" if s.get("verified")
                else " — ⚠️ غير متحقق منه: لم يظهر في نتائج البحث الفعلية، فحُذف رابطه")
        md.append(f"- **[{s['id']}] {_cell(s['title'], allowed)}** ({_cell(meta, allowed)}){link}. {_cell(s.get('used_for'), allowed)}")
    if not r.get("scientific_sources"):
        md.append("لا توجد مصادر علمية." if not mock else "لا توجد مصادر في وضع الاختبار.")
    checks = r.get("checks")
    if checks and checks.get("web_search"):
        md += ["", f"_البحث على الإنترنت: {searches_ar(checks['searches'])}، و{ar(checks['pages_consulted'])} صفحة رجع إليها النموذج، "
                   f"و{ar(checks['verified_sources'])} مصدر علمي متحقق منه._"]
    return "\n".join(md).strip() + "\n"
