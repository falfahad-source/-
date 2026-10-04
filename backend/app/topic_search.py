"""Find verses by topic: the user types a subject («مدة الرضاعة الطبيعية», «البحار»)
instead of words from the verse, and gets the verses AFAQ's sources link to it.

No model guesses the link; every result says which source made it and how:
- a curated scientific comparison whose concept matches       (weight 5)
- a Quranpedia topic (or its parent topic) that matches       (weight 3)
- the title of a secondary i'jaz article citing the verse     (weight 2)
- التفسير الميسر of the verse mentioning every word typed     (weight 1)

Matching is word-based on lightly stemmed words (article and conjunction prefixes,
attached pronouns and common suffixes removed), so «الرضاعة» matches «الرَّضاعة»,
«الإرضاع» and «مدتها» matches «مدة», but «رضا» does not match «مرضاة». Each query word
weighs by how rare it is across the sources (inverse document frequency), so in
«مدة الرضاعة الطبيعية» the topic word «الرضاعة» counts for more than «مدة». A source
text counts when it matches half the query's words or words carrying half its
weight (three quarters of the weight for the tafsir, which is long and would match
loosely); a partial match scores by the square of its share, so verses matching the
whole subject come first.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import (
    ArticleVerse,
    Concept,
    ExternalArticle,
    Relationship,
    Source,
    TafsirEntry,
    Topic,
    Verse,
    VerseTopic,
)
from .search import normalize_arabic

TAFSIR_BOOK = "quranpedia:book:2012"  # التفسير الميسر
STOPWORDS = {"من", "في", "عن", "على", "الى", "الي", "ما", "ماذا", "هل", "هو", "هي", "مع", "او", "ثم", "كل",
             "ذلك", "هذا", "هذه", "التي", "الذي", "الذين", "ان", "قد", "لا", "لم", "بين", "عند", "حول",
             "ايه", "ايات", "الايه", "الايات", "القران", "اعجاز", "الاعجاز", "العلمي", "علمي"}
_PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال")
_PRONOUNS = ("هما", "ها", "هم", "هن", "كم", "نا")
_SUFFIXES = ("يات", "ات", "ون", "ين", "ان", "يه", "ه", "ي")
WEIGHTS = {"concept": 5.0, "topic": 3.0, "article": 2.0, "tafsir": 1.0}


def stem(word: str) -> str:
    for p in _PREFIXES:
        if word.startswith(p) and len(word) - len(p) >= 3:
            word = word[len(p):]
            break
    # an attached pronoun, then a taa marbuta written ت before it: مدتها -> مده
    for s in _PRONOUNS:
        if word.endswith(s) and len(word) - len(s) >= 3:
            word = word[: -len(s)]
            if word.endswith("ت"):
                word = word[:-1] + "ه"
            break
    for s in _SUFFIXES:
        if word.endswith(s) and len(word) - len(s) >= 3:
            word = word[: -len(s)]
            break
    return word


def stems(text: str) -> set[str]:
    return {stem(w) for w in normalize_arabic(text).split() if w not in STOPWORDS}


def query_stems(q: str) -> list[str]:
    out = []
    for w in normalize_arabic(q).split():
        if w in STOPWORDS:
            continue
        s = stem(w)
        if len(s) >= 3 and s not in out:
            out.append(s)
    return out


def core_stem(q: str) -> str | None:
    """The subject of a phrase: its first definite noun. In «مدة الرضاعة الطبيعية» the word
    before it is a construct head (مدة) and the one after an adjective (الطبيعية), so the
    subject is «الرضاعة»; in «تكوين الجنين في الرحم» it is «الجنين»."""
    for w in normalize_arabic(q).split():
        if w not in STOPWORDS and any(w.startswith(p) for p in _PREFIXES):
            s = stem(w)
            if len(s) >= 3:
                return s
    return None


def _word_match(q: str, c: str) -> bool:
    return c == q or c.startswith(q) or (len(q) >= 4 and q in c) or (len(c) >= 4 and len(q) - len(c) <= 1 and q.startswith(c))


def _has(w: str, cand: set[str]) -> bool:
    return any(_word_match(w, c) for c in cand)


def coverage(q: list[str], cand: set[str], weight: dict[str, float] | None = None) -> float:
    """Share of the query's weight that the candidate's words cover (each word 1 by default)."""
    weight = weight or {}
    total = sum(weight.get(w, 1.0) for w in q)
    return sum(weight.get(w, 1.0) for w in q if _has(w, cand)) / total if total else 0.0


@dataclass
class _Entry:
    kind: str                 # concept | topic | article | tafsir
    label: str                # what the reader sees as the reason
    stems: set[str]
    verse_ids: list[int]
    url: str | None = None


@dataclass
class _Index:
    stamp: tuple
    entries: list[_Entry] = field(default_factory=list)
    verses: dict[int, tuple] = field(default_factory=dict)  # id -> (surah, ayah, name, text, page)


_cache: _Index | None = None


def _build(db: Session, stamp: tuple) -> _Index:
    idx = _Index(stamp=stamp)
    for v in db.query(Verse).filter_by(reading="hafs"):
        idx.verses[v.id] = (v.surah_number, v.ayah_number, v.surah_name, v.arabic_text, v.page_number)
    # curated comparisons: concept -> phrase:<s>:<a>:key relationships
    by_key = {(v[0], v[1]): vid for vid, v in idx.verses.items()}
    concept_verses: dict[str, set[int]] = defaultdict(set)
    for r in db.query(Relationship).filter(Relationship.source_entity.like("phrase:%"),
                                           Relationship.target_entity.like("concept:%")):
        _, s, a, _k = r.source_entity.split(":", 3)
        vid = by_key.get((int(s), int(a)))
        if vid:
            concept_verses[r.target_entity.removeprefix("concept:")].add(vid)
    for c in db.query(Concept).filter(Concept.key.in_(list(concept_verses))):
        idx.entries.append(_Entry("concept", c.name_ar, stems(c.name_ar), sorted(concept_verses[c.key])))
    topic_verses: dict[int, list[int]] = defaultdict(list)
    for vt in db.query(VerseTopic):
        topic_verses[vt.topic_id].append(vt.verse_id)
    for t in db.query(Topic):
        if topic_verses.get(t.id):
            label = f"{t.parent_name} › {t.name}" if t.parent_name else t.name
            idx.entries.append(_Entry("topic", label, stems(label), topic_verses[t.id]))
    art_verses: dict[int, list[int]] = defaultdict(list)
    for av in db.query(ArticleVerse):
        art_verses[av.article_id].append(av.verse_id)
    for a in db.query(ExternalArticle):
        if art_verses.get(a.id):
            idx.entries.append(_Entry("article", a.title, stems(a.title), art_verses[a.id], a.url))
    book = db.query(Source).filter_by(citation_identifier=TAFSIR_BOOK).one_or_none()
    if book:
        for t in db.query(TafsirEntry).filter_by(source_id=book.id):
            idx.entries.append(_Entry("tafsir", book.title, stems(t.original_text), [t.verse_id]))
    return idx


def _get_index(db: Session) -> _Index:
    global _cache
    stamp = (db.query(func.count(Verse.id)).scalar(), db.query(func.count(VerseTopic.id)).scalar(),
             db.query(func.count(ArticleVerse.id)).scalar(), db.query(func.count(Relationship.id)).scalar(),
             db.query(func.count(TafsirEntry.id)).scalar())
    if _cache is None or _cache.stamp != stamp:
        _cache = _build(db, stamp)
    return _cache


FEW = 10  # below this many verses, matches on the phrase's subject alone are added after the rest


def search_topics(db: Session, q: str, limit: int = 50, offset: int = 0) -> dict:
    words = query_stems(q)
    if not words:
        raise ValueError("اكتب موضوعًا من كلمة واحدة على الأقل (ثلاثة أحرف فأكثر)، مثل: الرضاعة، البحار، الجنين.")
    idx = _get_index(db)
    hits = [[w for w in words if _has(w, e.stems)] for e in idx.entries]
    df = {w: sum(1 for h in hits if w in h) for w in words}
    n = len(idx.entries)
    weight = {w: math.log((n + 1) / (df[w] + 1)) + 1.0 for w in words}
    score, reasons = _score(idx, words, hits, weight)
    core = core_stem(q)
    if len(score) < FEW and len(words) >= 2 and core:
        score, reasons = _score(idx, words, hits, weight, core=core)
    ranked = sorted(score, key=lambda vid: (-score[vid], idx.verses[vid][0], idx.verses[vid][1]))
    rows = []
    for vid in ranked[offset: offset + limit]:
        s, a, name, text, page = idx.verses[vid]
        rs = sorted(reasons[vid], key=lambda r: (-WEIGHTS[r["kind"]], -r["coverage"]))
        rows.append({"surah_number": s, "ayah_number": a, "surah_name": name, "text": text, "page_number": page,
                     "score": round(score[vid], 2), "reasons": rs[:4], "more_reasons": max(0, len(rs) - 4)})
    return {"query": q, "words": words, "total": len(ranked), "offset": offset, "results": rows}


def _score(idx: _Index, words, hits, weight, core: str | None = None):
    """Verses' scores and reasons. With `core`, entries that match only the phrase's
    subject word are let in as well (the few-results fallback)."""
    score: dict[int, float] = defaultdict(float)
    reasons: dict[int, list[dict]] = defaultdict(list)
    for e, h in zip(idx.entries, hits):
        if not h:
            continue
        cov = sum(weight[w] for w in h) / sum(weight.values())
        if e.kind == "tafsir":
            if cov < 0.75:
                continue
        elif cov < 0.5 and len(h) / len(words) < 0.5 and core not in h:
            continue
        for vid in e.verse_ids:
            if any(r["kind"] == e.kind and r["label"] == e.label for r in reasons[vid]):
                continue  # two index entries with the same name are one reason, counted once
            score[vid] += WEIGHTS[e.kind] * cov * cov  # a partial match ranks well below a full one
            reasons[vid].append({"kind": e.kind, "label": e.label, "url": e.url, "coverage": round(cov, 2)})
    return score, reasons
