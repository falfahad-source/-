"use client";

import { useEffect, useState } from "react";
import Markdown from "./Markdown";
import { Layer, TrustBadge } from "./common";
import { addHistory } from "./history";
import { link } from "./links";
import type { Trust } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type AiReportData = {
  verse: { surah_number: number; ayah_number: number; surah_name: string; text: string };
  mode: "mock" | "live"; provider: string; model: string | null; prompt_version: string;
  generated_at: string | null; saved?: boolean; trust_category: Trust; disclaimer: string; report_markdown: string | null;
};

/** The report itself: disclaimer, the model's Markdown, and where it came from. */
export function AiReportBody({ r }: { r: AiReportData }) {
  return (
    <>
      <p className="ai-disclaimer">{r.disclaimer}</p>
      {r.report_markdown && <Markdown text={r.report_markdown} />}
      <p className="note">
        {r.provider}{r.model && ` (${r.model})`} — نسخة التعليمات {r.prompt_version}
        {r.generated_at && <> — {new Date(r.generated_at).toLocaleString("ar")}</>}
        {r.saved && " — تقرير محفوظ"}
      </p>
    </>
  );
}

/** «الذكاء الاصطناعي في الإعجاز العلمي» as a layer of the verse journey. It shows the verse's
 * report without paying for one: the test report in test mode, a stored one once a platform is
 * connected. A new paid report is generated only when the reader asks for it. */
export function AiLayer({ s, a }: { s: number; a: number }) {
  const [r, setR] = useState<AiReportData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setR(null); setError(null);
    const params = new URLSearchParams({ surah_number: String(s), ayah_number: String(a) });
    fetch(`${API_BASE}/ai-research/report?${params}`)
      .then(async (res) => (res.ok ? setR(await res.json()) : setError((await res.json().catch(() => ({}))).detail || "تعذّر جلب التقرير.")))
      .catch(() => setError("تعذّر الاتصال بالخادم."));
  }, [s, a]);

  async function generate() {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/ai-research`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ surah_number: s, ayah_number: a }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) { setError(typeof body.detail === "string" ? body.detail : "تعذّر إنشاء التقرير."); return; }
      setR(body);
      addHistory({ kind: "ai", s, a, surah: body.verse.surah_name, mode: body.mode });
    } catch { setError("تعذّر الاتصال بالخادم."); } finally { setBusy(false); }
  }

  return (
    <Layer id="ai-layer" step="٥" title="الذكاء الاصطناعي في الإعجاز العلمي" trust="UNVERIFIED_CLAIM"
      lead="باحث آلي ناقد يدرس الآية: يفهمها من التفاسير، ويقارنها بالعلم الحديث، ويحاول دحض كل ربط قبل أن يحكم.">
      {!r && !error && <p className="empty">جارٍ التحميل...</p>}
      {r?.mode === "mock" && <p className="ai-mode mock"><strong>وضع الاختبار.</strong> منصة الذكاء الاصطناعي لم تُربط بعد؛ التقرير قالب تجريبي بلا نتائج.</p>}
      {r && r.report_markdown && (
        <details className="fold ai-fold" open>
          <summary><strong>تقرير الباحث الآلي</strong>{r.mode === "mock" && <span className="pill">تجريبي</span>}<TrustBadge trust={r.trust_category} /></summary>
          <AiReportBody r={r} />
        </details>
      )}
      {r && !r.report_markdown && (
        <div className="ai-generate">
          <p className="lead" style={{ margin: 0 }}>لم يُنشأ تقرير لهذه الآية بعد. إنشاؤه يستغرق وقتًا ويُحتسب من حد التقارير في الساعة.</p>
          <button type="button" className="btn-primary" onClick={generate} disabled={busy}>{busy ? "جارٍ البحث والتحليل..." : "أنشئ تقرير الذكاء الاصطناعي"}</button>
        </div>
      )}
      <p className="error" role="alert">{error}</p>
      <p className="note"><a href={link.ai(s, a)}>افتح في صفحة «الذكاء الاصطناعي في الإعجاز العلمي»</a></p>
    </Layer>
  );
}
