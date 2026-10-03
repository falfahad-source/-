"""Client for Dorar.net's hadith-encyclopedia API (الموسوعة الحديثية).

Documented at https://dorar.net/article/389 and in Dorar's sample PHP:
    GET https://dorar.net/dorar_api.json?skey=<search words>
    -> {"ahadith": {"result": "<html>"}}
The result is display HTML (up to 15 hadith per query), not structured data,
so parse_results() extracts each hadith from the documented markup:
    <div class="hadith">N - text</div>
    <div class="hadith-info"><span class="info-subtitle">الراوي:</span> ... </div>
    --------------

This is a keyword search over hadith; it has no notion of surah/ayah and is
NOT a tafsir source. Dorar's Cloudflare blocks cloud/datacenter IPs, so run
live ingestion from a normal network; tests use a saved real response.
"""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass

import requests

DORAR_API_URL = "https://dorar.net/dorar_api.json"
DORAR_DOC_URL = "https://dorar.net/article/389"

_MIN_INTERVAL_SECONDS = 1.0  # no published limit; stay polite

_HADITH_RE = re.compile(r'<div class="hadith"[^>]*>(.*?)</div>', re.DOTALL)
_INFO_RE = re.compile(r'<div class="hadith-info">(.*?)</div>', re.DOTALL)
_FIELD_RE = re.compile(
    r'<span class="info-subtitle">\s*([^<:]+?)\s*:\s*</span>(.*?)(?=<span class="info-subtitle">|$)', re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")
_RANK_PREFIX_RE = re.compile(r"^\s*(\d+)\s*-\s*")

_FIELD_NAMES = {
    "الراوي": "narrator",
    "المحدث": "muhaddith",
    "المصدر": "book",
    "الصفحة أو الرقم": "reference",
    "خلاصة حكم المحدث": "grade",
}


@dataclass
class DorarHadith:
    rank: int
    text: str
    narrator: str | None
    muhaddith: str | None
    book: str | None
    reference: str | None
    grade: str | None
    raw_html: str


def _clean(fragment: str) -> str:
    """Drop markup (e.g. <span class="search-keys"> highlighting) and squeeze
    whitespace; the words themselves are left untouched."""
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub("", fragment))).strip()


def parse_results(result_html: str) -> list[DorarHadith]:
    hadiths = []
    for block in result_html.split("--------------"):
        text_m, info_m = _HADITH_RE.search(block), _INFO_RE.search(block)
        if not text_m:
            continue  # header/footer chunk (canonical link, "المزيد")
        text = _clean(text_m.group(1))
        rank_m = _RANK_PREFIX_RE.match(text)
        rank = int(rank_m.group(1)) if rank_m else len(hadiths) + 1
        text = _RANK_PREFIX_RE.sub("", text)
        text = re.sub(r"\s*\.$", "", text)  # the API appends " ." after every hadith
        fields: dict[str, str | None] = dict.fromkeys(_FIELD_NAMES.values())
        if info_m:
            for label, value in _FIELD_RE.findall(info_m.group(1)):
                key = _FIELD_NAMES.get(label.strip())
                if key:
                    cleaned = _clean(value)
                    fields[key] = None if cleaned in ("", "-") else cleaned
        hadiths.append(DorarHadith(rank=rank, text=text, raw_html=block.strip(), **fields))
    return hadiths


class DorarClient:
    def __init__(self, url: str = DORAR_API_URL, session: requests.Session | None = None):
        self.url = url
        self.session = session or requests.Session()
        self._last_call = 0.0

    def search(self, query: str) -> list[DorarHadith]:
        elapsed = time.monotonic() - self._last_call
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        resp = self.session.get(self.url, params={"skey": query}, timeout=20)
        self._last_call = time.monotonic()
        resp.raise_for_status()
        return parse_results(resp.json()["ahadith"]["result"])
