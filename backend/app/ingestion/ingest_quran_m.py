"""Index i'jaz articles from quran-m.com (موسوعة الإعجاز العلمي) against verses.

    python -m app.ingestion.ingest_quran_m

The site states «جميع الحقوق محفوظة», so this is an index, not a copy: for each
post only the title, link, date, categories and a short excerpt are kept, plus
the verses the post discusses. Readers follow the link to read the article.
robots.txt allows everything but search pages; posts are read through the
site's public WordPress API (100 per request, one request per second).

A post is linked to a verse when it either
- cites it, e.g. «[النمل: 18]» or «(الجاثية: 13)», ranges like «[الرحمن: 19-20]»
  included; or
- quotes it between ﴿ ﴾ without a citation, and the quote (3+ words) matches at
  most 3 verses in the verse search (diacritics and spelling normalized).
Every link is a POSSIBLE_CONNECTION: a secondary reading, not tafsir, and its
scientific statements are not verified by AFAQ.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import time

import requests
from sqlalchemy.orm import Session

from ..db import SessionLocal, init_db
from ..models import ArticleVerse, ExternalArticle, Source, Verse
from ..search import normalize_arabic, search_verses
from ..trust import TrustCategory

SITE = "https://quran-m.com"
API = f"{SITE}/wp-json/wp/v2"
EXCERPT_CHARS = 280
MAX_QUOTE_MATCHES = 3

_TO_LATIN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_CITATION = re.compile(
    r"[\[\(]\s*(?:سورة\s+)?([ء-يً-ْٰـ ]{2,30}?)\s*[:：،,]\s*"
    r"(?:الآية|الآيات|آية)?\s*([0-9٠-٩]+)(?:\s*[-–—]\s*([0-9٠-٩]+))?\s*[\]\)]")
_QUOTE = re.compile(r"﴿([^﴾]{6,400})﴾")


def plain(rendered: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", rendered)).split())


def surah_numbers(db: Session) -> dict[str, int]:
    """Normalized surah name -> number, from the stored verses (e.g. "الجاثيه" -> 45)."""
    names = {}
    for s, name in db.query(Verse.surah_number, Verse.surah_name).distinct():
        n = normalize_arabic(name)
        names[n] = s
        names[n.removeprefix("ال")] = s  # «[نمل: 18]» is rare but harmless
    return names


def verse_links(text: str, db: Session, surahs: dict[str, int],
                ayah_counts: dict[int, int]) -> dict[tuple[int, int], tuple[str, str]]:
    """{(surah, ayah): (method, matched_text)} for one article's plain text."""
    found: dict[tuple[int, int], tuple[str, str]] = {}
    for name, a1, a2 in _CITATION.findall(text):
        s = surahs.get(normalize_arabic(name)) or surahs.get(normalize_arabic(name).removeprefix("ال"))
        if not s:
            continue
        lo = int(a1.translate(_TO_LATIN))
        hi = int(a2.translate(_TO_LATIN)) if a2 else lo
        if not (1 <= lo <= hi <= ayah_counts.get(s, 0)) or hi - lo > 10:
            continue
        for a in range(lo, hi + 1):
            found.setdefault((s, a), ("citation", f"[{name.strip()}: {a1}{'-' + a2 if a2 else ''}]"))
    for q in _QUOTE.findall(text):
        if len(normalize_arabic(q).split()) < 3:
            continue
        try:
            res = search_verses(db, q, limit=MAX_QUOTE_MATCHES + 1)
        except ValueError:
            continue
        if 0 < res["total"] <= MAX_QUOTE_MATCHES:
            for r in res["results"]:
                found.setdefault((r["surah_number"], r["ayah_number"]), ("quote", q.strip()[:120]))
    return found


def excerpt_of(post: dict) -> str:
    text = plain(post.get("excerpt", {}).get("rendered", "")) or plain(post["content"]["rendered"])
    text = re.sub(r"\s*\[(?:…|\.\.\.)\]\s*$", "", text)
    return text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"


def get_source(db: Session) -> Source:
    src = db.query(Source).filter_by(citation_identifier="quran-m").first()
    if src is None:
        src = Source(
            citation_identifier="quran-m", title="موسوعة الإعجاز العلمي في القرآن الكريم والسنة النبوية",
            publisher="quran-m.com", author="عبد الدائم الكحيل وآخرون", source_type="ijaz_site", url=SITE,
            retrieval_date=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),  # naive UTC, matches column
            trust_category=TrustCategory.POSSIBLE_CONNECTION,
        )
        db.add(src)
        db.flush()
    return src


def import_posts(db: Session, posts: list[dict], categories: dict[int, str]) -> tuple[int, int]:
    """Returns (articles added, verse links added). Re-importing a post refreshes its links."""
    src = get_source(db)
    surahs = surah_numbers(db)
    ayah_counts: dict[int, int] = {}
    for s, a in db.query(Verse.surah_number, Verse.ayah_number).filter(Verse.reading == "hafs"):
        ayah_counts[s] = max(ayah_counts.get(s, 0), a)
    verse_ids = {(v.surah_number, v.ayah_number): v.id for v in db.query(Verse).filter_by(reading="hafs")}
    added = linked = 0
    for p in posts:
        art = db.query(ExternalArticle).filter_by(source_id=src.id, external_id=p["id"]).first()
        if art is None:
            art = ExternalArticle(source_id=src.id, external_id=p["id"], title="", url="")
            db.add(art)
            added += 1
        art.title = plain(p["title"]["rendered"])
        art.url = p["link"]
        art.published = (p.get("date") or "")[:10] or None
        art.categories = "، ".join(categories[c] for c in p.get("categories", []) if c in categories) or None
        art.excerpt = excerpt_of(p)
        db.flush()
        db.query(ArticleVerse).filter_by(article_id=art.id).delete()
        for (s, a), (method, matched) in verse_links(plain(p["content"]["rendered"]), db, surahs, ayah_counts).items():
            if (s, a) in verse_ids:
                db.add(ArticleVerse(article_id=art.id, verse_id=verse_ids[(s, a)], match_method=method,
                                    matched_text=matched))
                linked += 1
    db.commit()
    return added, linked


def fetch_all(session: requests.Session | None = None, pause: float = 1.0):
    s = session or requests.Session()
    s.headers["User-Agent"] = "AFAQ-indexer/1.0 (links to articles; stores no article text)"
    cats = {c["id"]: html.unescape(c["name"])
            for c in s.get(f"{API}/categories", params={"per_page": 100}, timeout=60).json()}
    page, pages = 1, 1
    while page <= pages:
        r = s.get(f"{API}/posts", params={"per_page": 100, "page": page,
                                          "_fields": "id,link,title,date,categories,excerpt,content"}, timeout=120)
        r.raise_for_status()
        pages = int(r.headers.get("X-WP-TotalPages", "1"))
        yield cats, r.json()
        page += 1
        time.sleep(pause)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        total_a = total_l = 0
        for cats, posts in fetch_all():
            a, n = import_posts(db, posts, cats)
            total_a += a
            total_l += n
            print(f"page: {len(posts)} posts, {a} new, {n} verse links")
        print(f"done: {total_a} new articles, {total_l} verse links")
    finally:
        db.close()


if __name__ == "__main__":
    main()
