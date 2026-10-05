"""The verse's Quranic source pack: what AFAQ already stores for the verse (tafsir verbatim
from Quranpedia, meanings of its rare words, i'rab, topics), sent with the request so the
model reads the actual sources instead of recalling them, and cites them by id (Q1, Q2...).

Only this verse's sources are sent, each cut to a bounded length, never whole books; books
AFAQ does not hold can be added to an OpenAI vector store and searched with File Search
(OPENAI_VECTOR_STORE_IDS, see providers.py).
"""
from __future__ import annotations

import html
import re

from sqlalchemy.orm import Session

from ..rag.answer_builder import build_answer

TAFSIR_CHARS = 2500      # per book; التفسير الميسر is far shorter, the long books are cut
IRAB_CHARS = 1500
MAX_TAFSIR_BOOKS = 6


def plain(text: str) -> str:
    """Quranpedia texts carry markup (<span class="book-ayah">, <br />): keep the words."""
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _cut(text: str, n: int) -> tuple[str, bool]:
    if len(text) <= n:
        return text, False
    return text[:n].rsplit(" ", 1)[0] + " …", True


def source_pack(db: Session, surah_number: int, ayah_number: int) -> list[dict]:
    """[{id, kind, kind_label, title, author, year, text, truncated}] in the order sent."""
    a = build_answer(db, surah_number, ayah_number)
    if a is None:
        return []
    out: list[dict] = []

    def add(kind: str, kind_label: str, title: str, author: str | None, year, text: str, limit: int):
        body, cut = _cut(plain(text), limit)
        if body:
            out.append({"id": f"Q{len(out) + 1}", "kind": kind, "kind_label": kind_label, "title": title,
                        "author": author, "year": year, "text": body, "truncated": cut})

    # التفسير الميسر first: short, plain, and covers every verse
    tafsir = sorted(a.verified_tafsir, key=lambda t: "الميسر" not in t["source"])[:MAX_TAFSIR_BOOKS]
    for t in tafsir:
        add("tafsir", "تفسير", t["source"], t.get("scholar"), t.get("year"), t["text"], TAFSIR_CHARS)
    meanings = a.linguistic.get("meanings", [])
    if meanings:
        books = sorted({m["book"] for m in meanings})
        add("lexicon", "معاني الغريب", "، ".join(books), None, None,
            "\n".join(f"{m['word']}: {m['meaning']} ({m['book']})" for m in meanings), TAFSIR_CHARS)
    for e in a.linguistic.get("e3rab", [])[:1]:
        add("irab", "إعراب", e["book"], e.get("author"), e.get("year"), e["text"], IRAB_CHARS)
    if a.topics:
        add("topics", "الموضوعات القرآنية", "فهرس موضوعات Quranpedia", None, None,
            "\n".join(f"- {t['parent'] + ' › ' if t.get('parent') else ''}{t['name']}" for t in a.topics), 1500)
    return out
