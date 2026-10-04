"""Export the data for the static demo page (frontend/demo, see its build.mjs).

    python -m app.demo_export ../frontend/demo/data.json

Full answers (every layer) for the verses that have a curated concept map, the
text of all verses for client-side search, and the /explore list. Other verses get
a lighter answer built in the page: one short tafsir (BRIEF_TAFSIR_BOOK) and their
i'jaz article links, stored compactly here so the file stays small.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from sqlalchemy import func

from .db import SessionLocal, init_db
from .main import explore
from .models import ArticleVerse, Source, TafsirEntry, Verse, VersePhrase
from .rag.answer_builder import build_answer
from .rag.layers import IJAZ_LABEL, ijaz_articles, tafsir_timeline

BRIEF_TAFSIR_BOOK = "quranpedia:book:2012"  # التفسير الميسر — short, covers every ayah
ARTICLE_FIELDS = ("title", "url", "published", "categories", "excerpt", "source", "trust_category")
LINK_FIELDS = ("match_method", "matched_text", "verses_in_article", "focused")


def _light(db, model: set[str]) -> dict:
    """Brief tafsir and i'jaz links for every verse without a full answer:
      brief = {meta: entry fields shared by every verse, verses: {"s:a": [text, page]}}
      ijaz  = {label, articles: [article fields], verses: {"s:a": [total, [[article index, *link fields]]]}}"""
    book = db.query(Source).filter_by(citation_identifier=BRIEF_TAFSIR_BOOK).one_or_none()
    brief_meta, brief, articles, index, links = None, {}, [], {}, {}
    linked = {vid for (vid,) in db.query(ArticleVerse.verse_id).distinct()}
    for v in db.query(Verse).filter_by(reading="hafs").order_by(Verse.surah_number, Verse.ayah_number):
        key = f"{v.surah_number}:{v.ayah_number}"
        if key in model:
            continue
        if book:
            entries = db.query(TafsirEntry).filter_by(verse_id=v.id, source_id=book.id).all()
            for e in tafsir_timeline(entries)[:1]:
                brief_meta = brief_meta or {k: x for k, x in e.items() if k not in ("text", "page", "disagreement_group")}
                brief[key] = [e["text"], e.get("page")]
        if v.id in linked:
            ij = ijaz_articles(db, v)
            rows = []
            for a in ij["articles"]:
                if a["url"] not in index:
                    index[a["url"]] = len(articles)
                    articles.append([a[f] for f in ARTICLE_FIELDS])
                rows.append([index[a["url"]], *(a[f] for f in LINK_FIELDS)])
            links[key] = [ij["total"], rows]
    return {"brief": {"meta": brief_meta, "verses": brief},
            "ijaz": {"label": IJAZ_LABEL, "article_fields": ARTICLE_FIELDS, "link_fields": LINK_FIELDS,
                     "articles": articles, "verses": links}}


def _topic_index(db, verses: list) -> list:
    """The topic search index (app.topic_search) for the page's own search: [kind, label,
    url, [positions in `verses`]] per entry. Tafsir entries are left out: the page reads
    التفسير الميسر from the answers and from `brief`, which already carry it."""
    from .topic_search import _build

    pos = {(v[0], v[1]): i for i, v in enumerate(verses)}
    idx = _build(db, stamp=())
    out = []
    for e in idx.entries:
        if e.kind == "tafsir":
            continue
        refs = sorted({pos[idx.verses[vid][:2]] for vid in e.verse_ids if idx.verses[vid][:2] in pos})
        out.append([e.kind, e.label, e.url, refs])
    return out


def export(path: Path) -> dict:
    init_db()
    db = SessionLocal()
    try:
        model = sorted({(v.surah_number, v.ayah_number)
                        for v in db.query(Verse).join(VersePhrase, VersePhrase.verse_id == Verse.id)})
        answers = {f"{s}:{a}": dataclasses.asdict(build_answer(db, s, a)) for s, a in model}
        ijaz = dict(db.query(ArticleVerse.verse_id, func.count()).group_by(ArticleVerse.verse_id).all())
        verses = [[v.surah_number, v.ayah_number, v.surah_name, v.arabic_text, v.text_imlaei or "",
                   v.page_number, v.juz_number, ijaz.get(v.id, 0)]
                  for v in db.query(Verse).filter_by(reading="hafs").order_by(Verse.surah_number, Verse.ayah_number)]
        light = _light(db, set(answers))
        topic_index = _topic_index(db, verses)
    finally:
        db.close()
    data = {"answers": answers, "verses": verses, "explore": explore(), **light, "topic_index": topic_index}
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"model_verses": len(answers), "verses": len(verses), "bytes": path.stat().st_size}


if __name__ == "__main__":
    print(export(Path(sys.argv[1] if len(sys.argv) > 1 else "../frontend/demo/data.json")))
