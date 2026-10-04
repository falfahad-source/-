"use client";

import { useEffect, useState } from "react";
import Markdown from "../components/Markdown";
import { SurahName, TrustBadge } from "../components/common";
import type { Trust } from "../components/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Status = {
  mode: "mock" | "live"; provider: string; model: string | null; configured: boolean;
  missing_settings: string[]; prompt_version: string; prompt: string;
};
type Report = {
  verse: { surah_number: number; ayah_number: number; surah_name: string; text: string };
  mode: "mock" | "live"; provider: string; model: string | null; prompt_version: string;
  generated_at: string; trust_category: Trust; disclaimer: string; report_markdown: string;
};

export default function AiIjazPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [num, setNum] = useState<[number, number]>([24, 40]);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const m = /^(\d{1,3}):(\d{1,3})$/.exec(new URLSearchParams(location.search).get("v") ?? "");
    if (m) setNum([+m[1], +m[2]]);
    fetch(`${API_BASE}/ai-research/status`)
      .then(async (r) => (r.ok ? setStatus(await r.json()) : setError((await r.json().catch(() => ({}))).detail || "تعذّر الاتصال بالخادم.")))
      .catch(() => setError("تعذّر الاتصال بالخادم."));
  }, []);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setReport(null);
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/ai-research`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ surah_number: num[0], ayah_number: num[1] }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const d = body.detail;
        setError(typeof d === "string" ? d : "تعذّر إنشاء التقرير. تحقق من رقم السورة والآية.");
        return;
      }
      setReport(body);
      try { history.replaceState(null, "", `?v=${num[0]}:${num[1]}`); } catch { /* not allowed in some frames */ }
    } catch {
      setError("تعذّر الاتصال بالخادم.");
    } finally { setBusy(false); }
  }

  return (
    <div className="shell">
      <header className="masthead">
        <h1>آفاق <span>| الذكاء الاصطناعي في الإعجاز العلمي</span></h1>
        <p>باحث ذكاء اصطناعي ناقد: يفهم الآية من التفاسير، ويبحث في العلم الحديث، ويحاول دحض كل ربط قبل أن يحكم عليه.</p>
      </header>
      <p className="note"><a href={`/?v=${num[0]}:${num[1]}`}>← العودة إلى رحلة الآية</a></p>

      {status && (
        <div className={`ai-mode ${status.mode}`} role="status">
          {status.mode === "mock" ? (
            <><strong>وضع الاختبار.</strong> منصة الذكاء الاصطناعي لم تُربط بعد؛ يعمل القسم كاملًا لكن التقرير قالب تجريبي بلا نتائج.</>
          ) : status.configured ? (
            <><strong>متصل بمنصة الذكاء الاصطناعي</strong>{status.model && <> — النموذج: <code dir="ltr">{status.model}</code></>}.</>
          ) : (
            <><strong>المنصة غير مكتملة الإعداد على الخادم:</strong> <code dir="ltr">{status.missing_settings.join(", ")}</code></>
          )}
        </div>
      )}

      <form className="ai-form" onSubmit={run}>
        <label>رقم السورة
          <input type="number" min={1} max={114} required value={num[0]} onChange={(e) => setNum([Number(e.target.value), num[1]])} />
        </label>
        <label>رقم الآية
          <input type="number" min={1} max={286} required value={num[1]} onChange={(e) => setNum([num[0], Number(e.target.value)])} />
        </label>
        <button className="btn-primary" type="submit" disabled={busy}>{busy ? "جارٍ البحث والتحليل..." : "ابدأ البحث"}</button>
      </form>
      <p className="error" role="alert">{error}</p>

      {report && (
        <main className="journey">
          <section className="card verse-card" aria-label="الآية">
            <div className="layer-head"><h2 style={{ margin: 0 }}>الآية</h2><TrustBadge trust="QURANIC_TEXT" /></div>
            <p className="verse">{report.verse.text}</p>
            <div className="meta">
              <span>سورة <SurahName name={report.verse.surah_name} /></span><span>الآية <b>{report.verse.ayah_number}</b></span>
            </div>
          </section>

          <section className="card" aria-label="تقرير الذكاء الاصطناعي">
            <div className="layer-head">
              <h2>تقرير الباحث الآلي</h2>
              <TrustBadge trust={report.trust_category} />
              {report.mode === "mock" && <span className="pill">تجريبي</span>}
            </div>
            <p className="ai-disclaimer">{report.disclaimer}</p>
            <Markdown text={report.report_markdown} />
            <p className="note">
              {report.provider}{report.model && ` (${report.model})`} — نسخة التعليمات {report.prompt_version} — {new Date(report.generated_at).toLocaleString("ar")}
            </p>
          </section>
        </main>
      )}

      {status && (
        <details className="fold" style={{ marginTop: 16 }}>
          <summary><strong>التعليمات المرسلة إلى الذكاء الاصطناعي</strong><span className="note">نسخة {status.prompt_version}</span></summary>
          <p className="read">{status.prompt}</p>
        </details>
      )}
    </div>
  );
}
