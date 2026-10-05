"""AI platform adapters, chosen by environment and read on every request (so tests and a
changed .env need no code change). Keys are read on the server only, never sent to the
browser, never written to logs or error messages.

  AFAQ_AI_PROVIDER         "mock" (default: test mode), "openai" or "http"

  openai — OpenAI Responses API, with Web Search, optional File Search and Structured Outputs:
  OPENAI_API_KEY           required
  OPENAI_MODEL             default gpt-6.1-sol (checked against OpenAI's model docs, 2026-10-05)
  OPENAI_REASONING_EFFORT  low | medium | high (default) | xhigh | max
  OPENAI_VECTOR_STORE_IDS  comma-separated vector stores for File Search (extra books); optional
  OPENAI_WEB_SEARCH        "0" turns Web Search off (then no scientific link can be verified)
  OPENAI_BASE_URL          default https://api.openai.com/v1 (a proxy or a test server)
  OPENAI_MAX_OUTPUT_TOKENS default 64000 (reasoning and the JSON together)

  http — any OpenAI-compatible chat-completions platform, no tools:
  AFAQ_AI_API_URL, AFAQ_AI_API_KEY, AFAQ_AI_MODEL

  AFAQ_AI_TIMEOUT          seconds of silence allowed from the platform, default 600
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable

import requests

DEFAULT_OPENAI_MODEL = "gpt-6.1-sol"
EFFORTS = ("low", "medium", "high", "xhigh", "max")


class ProviderError(RuntimeError):
    """The platform could not produce a report (misconfigured, unreachable, bad reply)."""


@dataclass
class ProviderInfo:
    mode: str          # "mock" | "live"
    name: str
    model: str | None
    configured: bool   # False when a live platform is selected but a required setting is missing
    missing: list[str]
    tools: list[str] = field(default_factory=list)   # "web_search", "file_search", "structured_outputs"


@dataclass
class ResearchResult:
    """What a platform returned for one verse, before report.py checks it."""
    data: dict                                   # the report JSON (schema.py)
    consulted_urls: set[str] = field(default_factory=set)   # pages Web Search actually returned or opened
    files: dict[str, str] = field(default_factory=dict)     # File Search results: file_id -> filename
    searches: int = 0
    failed_searches: int = 0
    web_search: bool = False                     # whether the platform could search the web at all
    usage: dict | None = None                    # tokens, as the platform reports them (cost)


# progress callback: on_event(kind, detail) with kind in started | web_search | file_search | writing
OnEvent = Callable[[str, dict], None]


def _noop(kind: str, detail: dict) -> None:
    pass


def parse_json(text: str) -> dict:
    """The report JSON, tolerating a code fence or text around it."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ProviderError("ردّ منصة الذكاء الاصطناعي ليس بصيغة JSON المطلوبة.")
    return data


class MockProvider:
    """Test mode: no network, deterministic output (see mock.py)."""

    def info(self) -> ProviderInfo:
        return ProviderInfo(mode="mock", name="وضع الاختبار (بدون منصة ذكاء اصطناعي)", model=None,
                            configured=True, missing=[])

    def research(self, instructions: str, user: str, schema: dict, *, verse: dict, on_event: OnEvent = _noop) -> ResearchResult:
        from .mock import mock_data
        return ResearchResult(data=mock_data(verse))

    def generate(self, system: str, user: str, *, verse: dict | None) -> str:
        raise ProviderError("وضع الاختبار لا يولّد نصًا.")


class HttpProvider:
    """Any platform with an OpenAI-compatible /chat/completions endpoint. It has no tools:
    no web search, so report.py drops every scientific link as unverified."""

    def __init__(self, env=os.environ):
        self.url = env.get("AFAQ_AI_API_URL", "").strip()
        self.key = env.get("AFAQ_AI_API_KEY", "").strip()
        self.model = env.get("AFAQ_AI_MODEL", "").strip()
        self.timeout = float(env.get("AFAQ_AI_TIMEOUT", "600") or 600)

    def info(self) -> ProviderInfo:
        missing = [n for n, v in (("AFAQ_AI_API_URL", self.url), ("AFAQ_AI_API_KEY", self.key),
                                  ("AFAQ_AI_MODEL", self.model)) if not v]
        return ProviderInfo(mode="live", name="منصة ذكاء اصطناعي متوافقة (Chat Completions)", model=self.model or None,
                            configured=not missing, missing=missing)

    def generate(self, system: str, user: str, *, verse: dict | None) -> str:
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

    def research(self, instructions: str, user: str, schema: dict, *, verse: dict, on_event: OnEvent = _noop) -> ResearchResult:
        on_event("started", {})
        system = (instructions + "\n\nلا تملك في هذه المنصة أداة بحث على الإنترنت: اذكر ذلك في research_gaps، "
                  "ولا تذكر مصادر علمية من ذاكرتك على أنها نتائج بحث.\n\nأخرج JSON واحدًا يطابق هذا المخطط:\n"
                  + json.dumps(schema, ensure_ascii=False))
        on_event("writing", {})
        return ResearchResult(data=parse_json(self.generate(system, user, verse=verse)))


class OpenAIProvider:
    """OpenAI Responses API: the researcher instructions, the verse with its source pack, the
    Web Search tool (and File Search when vector stores are set), Structured Outputs for the
    report JSON. Streamed, so the page can show which stage the research is in."""

    RETRIES = 2

    def __init__(self, env=os.environ):
        self.key = env.get("OPENAI_API_KEY", "").strip()
        self.model = env.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
        effort = env.get("OPENAI_REASONING_EFFORT", "high").strip().lower()
        self.effort = effort if effort in EFFORTS else "high"
        self.stores = [s.strip() for s in env.get("OPENAI_VECTOR_STORE_IDS", "").split(",") if s.strip()]
        self.web = env.get("OPENAI_WEB_SEARCH", "1").strip() != "0"
        self.base = (env.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1").rstrip("/")
        self.timeout = float(env.get("AFAQ_AI_TIMEOUT", "600") or 600)
        self.max_tokens = int(env.get("OPENAI_MAX_OUTPUT_TOKENS", "64000") or 64000)

    def info(self) -> ProviderInfo:
        missing = [] if self.key else ["OPENAI_API_KEY"]
        tools = (["web_search"] if self.web else []) + (["file_search"] if self.stores else []) + ["structured_outputs"]
        return ProviderInfo(mode="live", name="OpenAI (Responses API)", model=self.model,
                            configured=not missing, missing=missing, tools=tools)

    # -- HTTP -------------------------------------------------------------------------
    def _post(self, body: dict, stream: bool) -> requests.Response:
        if not self.key:
            raise ProviderError("منصة الذكاء الاصطناعي غير مكتملة الإعداد: OPENAI_API_KEY")
        for attempt in range(self.RETRIES + 1):
            try:
                res = requests.post(f"{self.base}/responses", json=body, stream=stream,
                                    headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                                    timeout=(15, self.timeout))
            except requests.Timeout as e:
                raise ProviderError("انتهت مهلة انتظار ردّ OpenAI.") from e
            except requests.RequestException as e:
                raise ProviderError(f"تعذّر الاتصال بـOpenAI ({type(e).__name__}).") from e
            if res.status_code == 200:
                return res
            if res.status_code in (429, 500, 502, 503) and attempt < self.RETRIES:
                wait = res.headers.get("retry-after", "")
                time.sleep(min(float(wait) if wait.replace(".", "", 1).isdigit() else 2 ** (attempt + 1), 30))
                continue
            raise ProviderError(self._http_error(res))
        raise ProviderError("تعذّر الحصول على ردّ من OpenAI.")  # pragma: no cover

    def _http_error(self, res: requests.Response) -> str:
        try:
            err = res.json().get("error") or {}
        except ValueError:
            err = {}
        code, msg = res.status_code, str(err.get("message") or "")[:300]
        if code in (401, 403):
            return "مفتاح OpenAI غير صالح أو لا يملك صلاحية هذا النموذج."
        if code == 404:
            return f"النموذج {self.model} غير متاح لهذا الحساب في OpenAI."
        if code == 429:
            return "تجاوزت الحد المسموح لدى OpenAI (Rate limit) أو نفد الرصيد. حاول لاحقًا."
        if code >= 500:
            return f"خطأ مؤقت لدى OpenAI (الرمز {code}). حاول لاحقًا."
        return f"رفضت OpenAI الطلب (الرمز {code}){': ' + msg if msg else ''}."

    # -- research ---------------------------------------------------------------------
    def research(self, instructions: str, user: str, schema: dict, *, verse: dict, on_event: OnEvent = _noop) -> ResearchResult:
        tools, include = [], []
        if self.web:
            tools.append({"type": "web_search"})
            include.append("web_search_call.action.sources")
        if self.stores:
            tools.append({"type": "file_search", "vector_store_ids": self.stores, "max_num_results": 8})
            include.append("file_search_call.results")
        body = {
            "model": self.model,
            "instructions": instructions,   # fixed text first: OpenAI caches the shared prefix
            "input": user,
            "tools": tools,
            "include": include,
            "reasoning": {"effort": self.effort},
            "text": {"format": {"type": "json_schema", "name": "ijaz_research_report", "schema": schema, "strict": True}},
            "max_output_tokens": self.max_tokens,
            "store": False,
            "stream": True,
        }
        res = self._post(body, stream=True)
        on_event("started", {})
        final = None
        try:
            for event in _sse(res):
                kind = event.get("type", "")
                if kind.startswith("response.web_search_call."):
                    on_event("web_search", {"status": kind.rsplit(".", 1)[-1]})
                elif kind.startswith("response.file_search_call."):
                    on_event("file_search", {"status": kind.rsplit(".", 1)[-1]})
                elif kind == "response.output_text.delta":
                    on_event("writing", {})
                elif kind in ("response.completed", "response.incomplete", "response.failed"):
                    final = event.get("response") or {}
                    break
                elif kind == "error":
                    raise ProviderError(f"خطأ من OpenAI أثناء البحث: {str(event.get('message') or event.get('code') or '')[:300]}")
        except requests.RequestException as e:
            raise ProviderError("انقطع الاتصال بـOpenAI أثناء البحث، أو طال صمته عن المهلة.") from e
        finally:
            res.close()
        if final is None:
            raise ProviderError("انتهى ردّ OpenAI قبل اكتمال التقرير.")
        if final.get("status") == "failed":
            err = final.get("error") or {}
            raise ProviderError(f"فشل البحث لدى OpenAI: {str(err.get('message') or err.get('code') or '')[:300]}")
        if final.get("status") == "incomplete":
            reason = (final.get("incomplete_details") or {}).get("reason") or ""
            raise ProviderError("توقف ردّ OpenAI قبل اكتماله"
                                + (" لبلوغه الحد الأقصى للنص (OPENAI_MAX_OUTPUT_TOKENS)." if reason == "max_output_tokens" else f" ({reason})."))
        return self._result(final)

    def _result(self, response: dict) -> ResearchResult:
        out = ResearchResult(data={}, web_search=self.web, usage=response.get("usage"))
        texts, refusal = [], None
        for item in response.get("output") or []:
            t = item.get("type")
            if t == "web_search_call":
                out.searches += 1
                if item.get("status") == "failed":
                    out.failed_searches += 1
                action = item.get("action") or {}
                for s in action.get("sources") or []:
                    if s.get("url"):
                        out.consulted_urls.add(s["url"])
                if action.get("url"):                         # open_page / find_in_page
                    out.consulted_urls.add(action["url"])
            elif t == "file_search_call":
                for r in item.get("results") or []:
                    if r.get("file_id"):
                        out.files[r["file_id"]] = r.get("filename") or r["file_id"]
            elif t == "message":
                for c in item.get("content") or []:
                    if c.get("type") == "output_text":
                        texts.append(c.get("text") or "")
                        for a in c.get("annotations") or []:
                            if a.get("type") == "url_citation" and a.get("url"):
                                out.consulted_urls.add(a["url"])
                    elif c.get("type") == "refusal":
                        refusal = c.get("refusal") or ""
        if refusal is not None and not "".join(texts).strip():
            raise ProviderError("امتنع النموذج عن إعداد التقرير" + (f": {refusal[:200]}" if refusal else "."))
        out.data = parse_json("".join(texts))
        return out

    # -- plain text (topic search) -----------------------------------------------------
    def generate(self, system: str, user: str, *, verse: dict | None) -> str:
        res = self._post({"model": self.model, "instructions": system, "input": user,
                          "reasoning": {"effort": "low"}, "store": False}, stream=False)
        try:
            body = res.json()
        except ValueError as e:
            raise ProviderError("ردّ OpenAI ليس بالصيغة المتوقعة.") from e
        text = "".join(c.get("text") or "" for item in body.get("output") or [] if item.get("type") == "message"
                       for c in item.get("content") or [] if c.get("type") == "output_text")
        if not text.strip():
            raise ProviderError("ردّت OpenAI بنص فارغ.")
        return text


def _sse(res: requests.Response):
    """Server-sent events of a streamed response, as parsed JSON objects.

    Read as bytes and split on "\n" only: decoding first (iter_lines(decode_unicode=True))
    would split Arabic text, since requests decodes an event stream without a charset as
    Latin-1, where the byte 0x85 inside letters like «م» is a line separator."""
    buf, data = b"", []

    def lines():
        nonlocal buf
        for chunk in res.iter_content(chunk_size=None):
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                yield line.rstrip(b"\r").decode("utf-8", "replace")
        if buf:
            yield buf.decode("utf-8", "replace")
        yield ""

    for line in lines():
        if line == "":
            if data:
                payload, data = "\n".join(data), []
                if payload.strip() == "[DONE]":
                    return
                try:
                    yield json.loads(payload)
                except ValueError:
                    continue
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())


def get_provider(env=os.environ):
    kind = env.get("AFAQ_AI_PROVIDER", "mock").strip().lower() or "mock"
    if kind == "mock":
        return MockProvider()
    if kind == "openai":
        return OpenAIProvider(env)
    if kind == "http":
        return HttpProvider(env)
    raise ProviderError(f"قيمة AFAQ_AI_PROVIDER غير معروفة: {kind!r} (المسموح: mock أو openai أو http).")
