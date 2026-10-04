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
text counts when its matches carry half the query's weight (three quarters for the
tafsir, which is long and would match loosely), or, for words joined by و («البرق
والرعد»), when it matches half of them; a partial match scores by the square of its
share, so verses matching the whole subject come first.

Two things widen a word beyond its spelling:
- the same word in another form, broken plurals included («البحار» = «البحر»,
  «الجبال» = «جبل»): the Quranic Arabic Corpus gives every Quran word its lemma, so a
  query word and a source word with the same lemma match fully;
- a synonym from app/synonyms.json («المطر» ~ «الغيث»، «الجبال» ~ «الرواسي»): a curated,
  reviewable list. A synonym counts SYNONYM_CREDIT of a match, is not used on the tafsir
  (long texts would match too loosely), and the result names the synonym it went through.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

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
    WordAnalysis,
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
SYNONYM_CREDIT = 0.8
SYNONYM_GROUPS: list[list[str]] = json.loads(
    (Path(__file__).with_name("synonyms.json")).read_text(encoding="utf-8"))["groups"]


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


def query_stems(q: str) -> list[str]:
    out = []
    for w in normalize_arabic(q).split():
        if w in STOPWORDS:
            continue
        s = stem(w)
        if len(s) >= 3 and s not in out:
            out.append(s)
    return out


def is_coordinated(q: str) -> bool:
    """«البرق والرعد»: words joined by و ask for either, so matching one of them is enough.
    A construct phrase («ذكاء الإنسان», «مدة الرضاعة») asks for its subject, not any word."""
    return any(w.startswith("وال") for w in normalize_arabic(q).split()[1:])


def _word_match(q: str, c: str) -> bool:
    # a stem of three letters or fewer must be the whole word: «لب» is not «لبن», «ملح» not «ملحد»
    if len(q) <= 3:
        return c == q
    return c == q or c.startswith(q) or q in c or (len(c) >= 4 and len(q) - len(c) <= 1 and q.startswith(c))


Lexicon = dict[str, set[str]]  # normalized Quran word (and without its article) -> lemmas


def strip_article(w: str) -> str:
    """Only the article and its conjunctions: unlike stem(), never cuts into the word itself
    (stemming «لبنين» = لِ + بنين gives «لبن», which would then mean «ابن»)."""
    for p in _PREFIXES:
        if w.startswith(p) and len(w) - len(p) >= 2:
            return w[len(p):]
    return w


def word_lemmas(lex: Lexicon, w: str) -> set[str]:
    return lex.get(w) or lex.get(strip_article(w)) or set()


Words = list[tuple[str, frozenset[str]]]  # a text's words as (stem, lemmas); lemmas empty if unknown


def text_words(lex: Lexicon, text: str) -> Words:
    seen: dict[tuple[str, frozenset[str]], None] = {}
    for w in normalize_arabic(text).split():
        if w not in STOPWORDS:
            seen[(stem(w), frozenset(word_lemmas(lex, w)))] = None
    return list(seen)


def _same_word(q_stem: str, q_lemmas: set[str], c_stem: str, c_lemmas: frozenset[str]) -> bool:
    """Two words are the same word when they share a lemma (which covers broken plurals);
    when either is not a Quran word, when their stems match. Lemmas decide when both are
    known, so a clitic that the stemmer cannot see apart (لِبَنِيه -> «لبن») does not match."""
    if q_lemmas and c_lemmas:
        return bool(q_lemmas & c_lemmas)
    return _word_match(q_stem, c_stem)


@dataclass
class _Word:
    """A query word: its stem, its lemmas, and its synonyms as (word, stem, lemmas)."""
    stem: str
    lemmas: set[str]
    synonyms: list[tuple[str, str, set[str]]]


def query_words(lex: Lexicon, q: str) -> list[_Word]:
    out: list[_Word] = []
    for w in normalize_arabic(q).split():
        if w in STOPWORDS:
            continue
        s = stem(w)
        if len(s) < 3 or any(x.stem == s for x in out):
            continue
        lemmas = word_lemmas(lex, w)
        syns: list[tuple[str, str, set[str]]] = []
        for group in SYNONYM_GROUPS:
            members = [(m, stem(normalize_arabic(m)), word_lemmas(lex, normalize_arabic(m))) for m in group]
            if any(ms == s or (lemmas and ml & lemmas) for _, ms, ml in members):
                syns += [x for x in members if x[1] != s and not (lemmas and x[2] & lemmas)]
        out.append(_Word(s, lemmas, syns))
    return out


def credit(w: _Word, words: Words, allow_synonyms: bool) -> tuple[float, str | None]:
    """How well a source text matches a query word: 1 for the word itself (any form),
    SYNONYM_CREDIT through a synonym (named in the result), else 0."""
    if any(_same_word(w.stem, w.lemmas, cs, cl) for cs, cl in words):
        return 1.0, None
    if allow_synonyms:
        for word, ms, ml in w.synonyms:
            if any(_same_word(ms, ml, cs, cl) for cs, cl in words):
                return SYNONYM_CREDIT, word
    return 0.0, None


@dataclass
class _Entry:
    kind: str                 # concept | topic | article | tafsir
    label: str                # what the reader sees as the reason
    words: Words
    verse_ids: list[int]
    url: str | None = None


@dataclass
class _Index:
    stamp: tuple
    entries: list[_Entry] = field(default_factory=list)
    verses: dict[int, tuple] = field(default_factory=dict)  # id -> (surah, ayah, name, text, page)
    lexicon: Lexicon = field(default_factory=dict)


def build_lexicon(db: Session) -> Lexicon:
    lex: Lexicon = defaultdict(set)
    for text, lemma in db.query(WordAnalysis.text, WordAnalysis.lemma).filter(WordAnalysis.lemma.isnot(None)):
        n, lm = normalize_arabic(text), normalize_arabic(lemma)
        if n and lm:
            lex[n].add(lm)
            lex[strip_article(n)].add(lm)
    return dict(lex)


_cache: _Index | None = None


def _build(db: Session, stamp: tuple) -> _Index:
    idx = _Index(stamp=stamp, lexicon=build_lexicon(db))
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
        idx.entries.append(_Entry("concept", c.name_ar, text_words(idx.lexicon, c.name_ar),
                                  sorted(concept_verses[c.key])))
    topic_verses: dict[int, list[int]] = defaultdict(list)
    for vt in db.query(VerseTopic):
        topic_verses[vt.topic_id].append(vt.verse_id)
    for t in db.query(Topic):
        if topic_verses.get(t.id):
            label = f"{t.parent_name} › {t.name}" if t.parent_name else t.name
            idx.entries.append(_Entry("topic", label, text_words(idx.lexicon, label), topic_verses[t.id]))
    art_verses: dict[int, list[int]] = defaultdict(list)
    for av in db.query(ArticleVerse):
        art_verses[av.article_id].append(av.verse_id)
    for a in db.query(ExternalArticle):
        if art_verses.get(a.id):
            idx.entries.append(_Entry("article", a.title, text_words(idx.lexicon, a.title), art_verses[a.id], a.url))
    book = db.query(Source).filter_by(citation_identifier=TAFSIR_BOOK).one_or_none()
    if book:
        for t in db.query(TafsirEntry).filter_by(source_id=book.id):
            idx.entries.append(_Entry("tafsir", book.title, text_words(idx.lexicon, t.original_text), [t.verse_id]))
    return idx


def _get_index(db: Session) -> _Index:
    global _cache
    stamp = (db.query(func.count(Verse.id)).scalar(), db.query(func.count(VerseTopic.id)).scalar(),
             db.query(func.count(ArticleVerse.id)).scalar(), db.query(func.count(Relationship.id)).scalar(),
             db.query(func.count(TafsirEntry.id)).scalar(), db.query(func.count(WordAnalysis.id)).scalar())
    if _cache is None or _cache.stamp != stamp:
        _cache = _build(db, stamp)
    return _cache


def warm_index(db: Session) -> None:
    """Build the index now rather than on the first search (see app.main)."""
    _get_index(db)


FEW = 10  # below this many verses, matches on the phrase's subject (rarest word) alone are added after the rest


def search_topics(db: Session, q: str, limit: int = 50, offset: int = 0) -> dict:
    idx = _get_index(db)
    words = query_words(idx.lexicon, q)
    if not words:
        raise ValueError("اكتب موضوعًا من كلمة واحدة على الأقل (ثلاثة أحرف فأكثر)، مثل: الرضاعة، البحار، الجنين.")
    # per entry: {query stem: (credit, synonym used or None)} for the words it matches
    hits = []
    for e in idx.entries:
        h = {}
        for w in words:
            c, via = credit(w, e.words, allow_synonyms=e.kind != "tafsir")
            if c:
                h[w.stem] = (c, via)
        hits.append(h)
    n = len(idx.entries)
    weight = {w.stem: math.log((n + 1) / (sum(1 for h in hits if w.stem in h) + 1)) + 1.0 for w in words}
    either = is_coordinated(q)
    score, reasons = _score(idx, words, hits, weight, either=either)
    if len(score) < FEW and len(words) >= 2:
        # the phrase's subject is its most informative word, the rarest in the sources: «الرضاعة»
        # in «مدة الرضاعة الطبيعية», «ذكاء» in «ذكاء الإنسان» (not «الإنسان», which is everywhere)
        core = max(words, key=lambda w: (weight[w.stem], -words.index(w))).stem
        score, reasons = _score(idx, words, hits, weight, either=either, core=core)
    # rounded so that equal scores tie exactly (whatever order the floats were added in), then mushaf order
    ranked = sorted(score, key=lambda vid: (-round(score[vid], 6), idx.verses[vid][0], idx.verses[vid][1]))
    rows = []
    for vid in ranked[offset: offset + limit]:
        s, a, name, text, page = idx.verses[vid]
        rs = sorted(reasons[vid], key=lambda r: (-WEIGHTS[r["kind"]], -r["coverage"]))
        rows.append({"surah_number": s, "ayah_number": a, "surah_name": name, "text": text, "page_number": page,
                     "score": round(score[vid], 2), "reasons": rs[:4], "more_reasons": max(0, len(rs) - 4)})
    return {"query": q, "words": [w.stem for w in words], "total": len(ranked), "offset": offset, "results": rows}


def _score(idx: _Index, words, hits, weight, either: bool = False, core: str | None = None):
    """Verses' scores and reasons. A verse is judged on all its sources together: the query
    words they match between them (each at its best credit) must carry half the query's
    weight; with `either` (coordinated words) it is enough to match half the words; with
    `core`, to match the phrase's subject (the few-results fallback). So «حركة الشمس» keeps
    a verse whose topics speak of «حركتهما» and of «الشمس» separately, while «ذكاء الإنسان»
    drops the verses that only speak of «الإنسان». The verse's score, the sum of its
    sources' scores, is then scaled by that coverage."""
    total = sum(weight.values())
    raw: dict[int, float] = defaultdict(float)
    reasons: dict[int, list[dict]] = defaultdict(list)
    best: dict[int, dict[str, float]] = defaultdict(dict)
    for e, h in zip(idx.entries, hits):
        if not h:
            continue
        cov = sum(weight[w] * c for w, (c, _) in h.items()) / total
        if e.kind == "tafsir" and cov < 0.75:
            continue
        via = sorted({v for _, v in h.values() if v})
        for vid in e.verse_ids:
            if any(r["kind"] == e.kind and r["label"] == e.label for r in reasons[vid]):
                continue  # two index entries with the same name are one reason, counted once
            raw[vid] += WEIGHTS[e.kind] * cov * cov  # a partial match ranks well below a full one
            reasons[vid].append({"kind": e.kind, "label": e.label, "url": e.url, "coverage": round(cov, 2),
                                 "synonyms": via})
            for w, (c, _) in h.items():
                best[vid][w] = max(best[vid].get(w, 0.0), c)
    score: dict[int, float] = {}
    for vid, got in best.items():
        vcov = sum(weight[w] * c for w, c in got.items()) / total
        if vcov >= 0.5 or (either and len(got) / len(words) >= 0.5) or core in got:
            score[vid] = raw[vid] * vcov
    return score, {vid: reasons[vid] for vid in score}
