"""Find verses containing a fragment the user typed.

Users type without diacritics and in ordinary (imla'i) spelling, while the
stored text is Uthmani script with full tashkeel. Both sides are therefore
normalized before a substring match:
- tashkeel, Quranic annotation marks, tatweel, ayah-end signs and digits removed;
- letter variants folded: أ إ آ ٱ -> ا, ى -> ي, ة -> ه, ؤ -> و, ئ -> ي.
Each verse is matched against both its imla'i text (KFGQPC aya_text_emlaey,
so "الصلاة" finds ٱلصَّلَوٰةَ) and its normalized Uthmani text (so a user
copying Uthmani spelling such as "الصلوة" also matches).

Normalization is for matching only: results always return the verse text
exactly as stored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Verse

MIN_QUERY_LETTERS = 2

# Arabic diacritics/annotations: U+0610–U+061A, U+064B–U+065F, U+0670 (dagger alef),
# U+06D6–U+06ED (Quranic marks incl. ۝ U+06DD), plus tatweel U+0640.
_MARKS_RE = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_DIGITS_RE = re.compile("[0-9٠-٩۰-۹]")
_NON_ARABIC_LETTER_RE = re.compile("[^ء-ي ]")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def normalize_arabic(text: str) -> str:
    text = _DIGITS_RE.sub("", _MARKS_RE.sub("", text)).translate(_FOLD)
    text = _NON_ARABIC_LETTER_RE.sub(" ", text)
    return " ".join(text.split())


@dataclass
class _IndexedVerse:
    surah_number: int
    ayah_number: int
    surah_name: str
    arabic_text: str
    page_number: int | None
    keys: tuple[str, ...]


# The Quran text changes only on re-import, so the normalized index is built
# once and rebuilt when the verses table changes (count or max id differ).
_index: list[_IndexedVerse] = []
_index_stamp: tuple | None = None


def _get_index(db: Session) -> list[_IndexedVerse]:
    global _index, _index_stamp
    stamp = db.query(func.count(Verse.id), func.max(Verse.id), func.max(Verse.source_id)).filter(
        Verse.reading == "hafs").one()
    if stamp != _index_stamp:
        rows = (
            db.query(Verse).filter_by(reading="hafs")
            .order_by(Verse.surah_number, Verse.ayah_number).all()
        )
        _index = [
            _IndexedVerse(
                v.surah_number, v.ayah_number, v.surah_name, v.arabic_text, v.page_number,
                tuple(dict.fromkeys(k for k in (normalize_arabic(v.text_imlaei or ""),
                                               normalize_arabic(v.arabic_text)) if k)),
            )
            for v in rows
        ]
        _index_stamp = stamp
    return _index


def search_verses(db: Session, query: str, limit: int = 50, offset: int = 0) -> dict:
    """Returns {"query", "normalized_query", "total", "offset", "results": [...]}:
    the matches in mushaf order from `offset`, at most `limit` of them; `total` is
    the full match count, so a caller pages with offset += len(results)."""
    needle = normalize_arabic(query)
    if len(needle.replace(" ", "")) < MIN_QUERY_LETTERS:
        raise ValueError("اكتب حرفين عربيين على الأقل للبحث.")
    matches = [v for v in _get_index(db) if any(needle in k for k in v.keys)]
    return {
        "query": query,
        "normalized_query": needle,
        "total": len(matches),
        "offset": offset,
        "results": [
            {
                "surah_number": v.surah_number, "surah_name": v.surah_name,
                "ayah_number": v.ayah_number, "text": v.arabic_text, "page_number": v.page_number,
            }
            for v in matches[offset:offset + limit]
        ],
    }
