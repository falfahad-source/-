"""AI platform adapters. Chosen by environment, read on every request so a restart is
not needed in tests:

  AFAQ_AI_PROVIDER   "mock" (default, test mode) or "http"
  AFAQ_AI_API_URL    full URL of an OpenAI-compatible chat-completions endpoint
                     (e.g. https://api.example.com/v1/chat/completions)
  AFAQ_AI_API_KEY    sent as "Authorization: Bearer <key>"; server-side only
  AFAQ_AI_MODEL      model name the platform expects
  AFAQ_AI_TIMEOUT    seconds, default 300 (a full research report is long)

If the platform turns out not to speak the chat-completions format, add another class
with the same `generate(system, user) -> str` method and select it here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests


class ProviderError(RuntimeError):
    """The platform could not produce a report (misconfigured, unreachable, bad reply)."""


@dataclass
class ProviderInfo:
    mode: str          # "mock" | "live"
    name: str
    model: str | None
    configured: bool   # False when "http" is selected but a required setting is missing
    missing: list[str]


class MockProvider:
    """Test mode: no network, deterministic output (see mock.py)."""

    def info(self) -> ProviderInfo:
        return ProviderInfo(mode="mock", name="وضع الاختبار (بدون منصة ذكاء اصطناعي)", model=None,
                            configured=True, missing=[])

    def generate(self, system: str, user: str, *, verse: dict) -> str:
        from .mock import mock_report
        return mock_report(verse)


class HttpProvider:
    """Any platform exposing an OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, env=os.environ):
        self.url = env.get("AFAQ_AI_API_URL", "").strip()
        self.key = env.get("AFAQ_AI_API_KEY", "").strip()
        self.model = env.get("AFAQ_AI_MODEL", "").strip()
        self.timeout = float(env.get("AFAQ_AI_TIMEOUT", "300") or 300)

    def info(self) -> ProviderInfo:
        missing = [n for n, v in (("AFAQ_AI_API_URL", self.url), ("AFAQ_AI_API_KEY", self.key),
                                  ("AFAQ_AI_MODEL", self.model)) if not v]
        return ProviderInfo(mode="live", name="منصة الذكاء الاصطناعي المتصلة", model=self.model or None,
                            configured=not missing, missing=missing)

    def generate(self, system: str, user: str, *, verse: dict) -> str:
        info = self.info()
        if not info.configured:
            raise ProviderError("منصة الذكاء الاصطناعي غير مكتملة الإعداد: " + "، ".join(info.missing))
        try:
            res = requests.post(
                self.url,
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                json={"model": self.model,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise ProviderError(f"تعذّر الاتصال بمنصة الذكاء الاصطناعي ({type(e).__name__}).") from e
        if res.status_code != 200:
            raise ProviderError(f"ردّت منصة الذكاء الاصطناعي بالرمز {res.status_code}.")
        try:
            content = res.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ProviderError("ردّ منصة الذكاء الاصطناعي ليس بالصيغة المتوقعة.") from e
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("ردّت منصة الذكاء الاصطناعي بتقرير فارغ.")
        return content


def get_provider(env=os.environ):
    kind = env.get("AFAQ_AI_PROVIDER", "mock").strip().lower() or "mock"
    if kind == "mock":
        return MockProvider()
    if kind == "http":
        return HttpProvider(env)
    raise ProviderError(f"قيمة AFAQ_AI_PROVIDER غير معروفة: {kind!r} (المسموح: mock أو http).")
