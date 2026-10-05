"use client";

import { useEffect, useState } from "react";
import { AiReportBody, type AiReportData, type ResearchJob, ResearchProgress, startResearch } from "../components/AiReport";
import Footer from "../components/Footer";
import SiteNav from "../components/SiteNav";
import { ar, SurahName, TrustBadge } from "../components/common";
import { addHistory } from "../components/history";
import { link, readParams, replaceUrl, verseParam } from "../components/links";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Status = {
  mode: "mock" | "live"; provider: string; model: string | null; configured: boolean;
  missing_settings: string[]; tools?: string[]; prompt_version: string; prompt: string;
};
type Report = AiReportData;
const TOOL: Record<string, string> = { web_search: "البحث على الإنترنت", file_search: "البحث في الملفات المرجعية", structured_outputs: "مخرجات منظمة" };

export default function AiIjazPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [num, setNum] = useState<[number, number]>([24, 40]);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const v = verseParam(readParams());
    if (v) setNum(v);
    fetch(`${API_BASE}/ai-research/status`)
      .then(async (r) => (r.ok ? setStatus(await r.json()) : setError((await r.json().catch(() => ({}))).detail || "تعذّر الاتصال بالخادم.")))
      .catch(() => setError("تعذّر الاتصال بالخادم."));
  }, []);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setReport(null);
    setJob(null);
    setBusy(true);
    try {
      const body = await startResearch(num[0], num[1], setJob);
      setReport(body);
      addHistory({ kind: "ai", s: num[0], a: num[1], surah: body.verse.surah_name, mode: body.mode });
      replaceUrl(link.ai(num[0], num[1]));
    } catch (e) {
      setError(e instanceof TypeError ? "تعذّر الاتصال بالخادم." : (e as Error).message || "تعذّر إنشاء التقرير. تحقق من رقم السورة والآية.");
    } finally { setBusy(false); }
  }

  return (
    <div className="shell">
      <SiteNav current="ai" />
      <header className="masthead">
        <h1>الذكاء الاصطناعي في الإعجاز العلمي</h1>
        <p>باحث ذكاء اصطناعي ناقد: يفهم الآية من التفاسير، ويبحث في العلم الحديث، ويحاول دحض كل ربط قبل أن يحكم عليه.</p>
      </header>
      <p className="note"><a href={link.verse(num[0], num[1])}>← التفسير والمعرفة العلمية لهذه الآية</a></p>

      {status && (
        <div className={`ai-mode ${status.mode}`} role="status">
          {status.mode === "mock" ? (
            <><strong>وضع الاختبار.</strong> منصة الذكاء الاصطناعي لم تُربط بعد؛ يعمل القسم كاملًا لكن التقرير قالب تجريبي بلا نتائج.</>
          ) : status.configured ? (
            <><strong>متصل بـ{status.provider}</strong>{status.model && <> — النموذج: <code dir="ltr">{status.model}</code></>}
              {status.tools && status.tools.length > 0 && <> — الأدوات: {status.tools.map((t) => TOOL[t] ?? t).join("، ")}</>}.</>
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
      {busy && <ResearchProgress job={job} />}
      <p className="error" role="alert">{error}</p>

      {report && (
        <main className="journey">
          <section className="card verse-card" aria-label="الآية">
            <div className="layer-head"><h2 style={{ margin: 0 }}>الآية</h2><TrustBadge trust="QURANIC_TEXT" /></div>
            <p className="verse">{report.verse.text}</p>
            <div className="meta">
              <span>سورة <SurahName name={report.verse.surah_name} /></span><span>الآية <b>{ar(report.verse.ayah_number)}</b></span>
            </div>
          </section>

          <section className="card" aria-label="تقرير الذكاء الاصطناعي">
            <div className="layer-head">
              <h2>تقرير الباحث الآلي</h2>
              <TrustBadge trust={report.trust_category} />
              {report.mode === "mock" && <span className="pill">تجريبي</span>}
            </div>
            <AiReportBody r={report} />
          </section>
        </main>
      )}

      {status && (
        <details className="fold" style={{ marginTop: 16 }}>
          <summary><strong>التعليمات المرسلة إلى الذكاء الاصطناعي</strong><span className="note">نسخة {status.prompt_version}</span></summary>
          <p className="read">{status.prompt}</p>
        </details>
      )}
      <Footer />
    </div>
  );
}
