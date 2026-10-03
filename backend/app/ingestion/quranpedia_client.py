"""Client for the official, documented Quranpedia API.

Verified by inspecting https://quranpedia.net/api-docs and
https://quranpedia.net/dumps/LICENSE.md directly before writing this file
(see docs/SOURCE_FINDINGS.md). This client only calls documented endpoints —
it does not scrape HTML pages, and it respects the published rate limits
(120/min, 10,000/day) by doing simple client-side throttling.

This file is network code: it has not been executed inside this chat sandbox
(no outbound network there). Run it from an environment with real network
access (e.g. Claude Code) and verify with the accompanying tests first.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from ..config import QURANPEDIA_API_BASE

_MIN_INTERVAL_SECONDS = 60.0 / 120.0  # stay well under the documented 120/min limit


@dataclass
class QuranpediaAyah:
    id: int
    number: int
    surah: int
    page_number: int
    text: str
    options: list[str]


class QuranpediaClient:
    def __init__(self, base_url: str = QURANPEDIA_API_BASE, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self._last_call = 0.0

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        # Simple client-side throttle to respect the published rate limit.
        elapsed = time.monotonic() - self._last_call
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=15)
        self._last_call = time.monotonic()
        resp.raise_for_status()
        return resp.json()

    # ---- Quran text -----------------------------------------------------
    def list_mushafs(self) -> list[dict]:
        return self._get("/mushafs")  # type: ignore[return-value]

    def get_surah_ayahs(self, mushaf_id: int, surah_id: int) -> list[QuranpediaAyah]:
        raw = self._get(f"/mushafs/{mushaf_id}/{surah_id}")
        return [
            QuranpediaAyah(
                id=a["id"], number=a["number"], surah=a["surah"],
                page_number=a.get("page_number", 0), text=a["text"],
                options=a.get("options", []),
            )
            for a in raw  # type: ignore[union-attr]
        ]

    def get_ayah(self, mushaf_id: int, surah_id: int, ayah_number: int) -> QuranpediaAyah:
        a = self._get(f"/mushafs/{mushaf_id}/{surah_id}/{ayah_number}")
        return QuranpediaAyah(
            id=a["id"], number=a["number"], surah=a["surah"],  # type: ignore[index]
            page_number=a.get("page_number", 0), text=a["text"],  # type: ignore[union-attr]
            options=a.get("options", []),  # type: ignore[union-attr]
        )

    # ---- Tafsir -----------------------------------------------------------
    def list_surah_tafsir_books(self, surah_id: int) -> list[dict]:
        return self._get(f"/surah/tafsirs/{surah_id}")  # type: ignore[return-value]

    def get_tafsir_for_ayah(self, surah_id: int, ayah_number: int, book_id: int) -> dict:
        return self._get(f"/ayah/{surah_id}/{ayah_number}/book/{book_id}")  # type: ignore[return-value]

    def get_book(self, book_id: int) -> dict:
        return self._get(f"/book/{book_id}")  # type: ignore[return-value]

    # ---- Delta sync ---------------------------------------------------------
    def get_changes(self, since: str) -> dict:
        """since: ISO date string, must be within the last year per API policy."""
        return self._get("/changes", params={"since": since})  # type: ignore[return-value]
