"use client";

import { useEffect, useState } from "react";
import Markdown from "./Markdown";
import { ar, Layer, TrustBadge } from "./common";
import { addHistory } from "./history";
import { link } from "./links";
import type { Trust } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type AiReportData = {
  verse: { surah_number: number; ayah_number: number; surah_name: string; text: string };
  mode: "mock" | "live"; provider: string; model: string | null; prompt_version: string;
  generated_at: string | null; saved?: boolean; trust_category: Trust; disclaimer: string; report_markdown: string | null;
  confidence_level?: string | null; confidence_label?: string | null;
  checks?: { searches: number; pages_consulted: number; verified_sources: number; unverified_sources: number; warnings: string[] } | null;
};

export type ResearchJob = {
  job_id: string; status: "running" | "done" | "failed"; elapsed: number; searches: number;
  stages: { key: string; label: string; state: "pending" | "active" | "done" | "skipped" }[];
  report?: AiReportData; error?: string;
};

/** Ask for a verse's report. Test mode and stored reports answer at once; a real research run
 * answers 202 with a job, followed here until it ends (onJob gets each state for the progress list). */
export async function startResearch(s: number, a: number, onJob: (j: ResearchJob) => void): Promise<AiReportData> {
  const res = await fetch(`${API_BASE}/ai-research`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ surah_number: s, ayah_number: a }),
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 200) return body as AiReportData;
  if (res.status !== 202) throw new Error(typeof body.detail === "string" ? body.detail : "تعذّر إنشاء التقرير.");
  let job = body as ResearchJob;
  let misses = 0;
  while (job.status === "running") {
    onJob(job);
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const next = await fetch(`${API_BASE}/ai-research/jobs/${job.job_id}`);
      const nb = await next.json().catch(() => ({}));
      if (!next.ok) throw new Error(typeof nb.detail === "string" ? nb.detail : "تعذّر متابعة البحث.");
      job = nb as ResearchJob; misses = 0;
    } catch (e) {
      // a dropped connection or two is not the end of a research that runs on the server
      if (++misses >= 5 || (e instanceof Error && e.message.includes("لم يُعثر"))) throw e;
    }
  }
  onJob(job);
  if (job.status === "failed" || !job.report) throw new Error(job.error || "تعذّر إنشاء التقرير.");
  return job.report;
}

const MARK = { done: "✓", active: "", pending: "", skipped: "–" } as const;

/** Where a running research is: the stages the server reports, never the model's reasoning. */
export function ResearchProgress({ job }: { job: ResearchJob | null }) {
  if (!job) return <p className="note" role="status">جارٍ بدء البحث...</p>;
  const m = Math.floor(job.elapsed / 60), sec = job.elapsed % 60;
  return (
    <div className="research-progress" role="status" aria-live="polite">
      <ol>
        {job.stages.map((st) => (
          <li key={st.key} className={`stage stage-${st.state}`}>
            <span className="stage-mark" aria-hidden="true">{MARK[st.state]}</span>
            {st.label}{st.state === "active" ? "..." : ""}{st.state === "skipped" ? " (لم يُحتج إليه)" : ""}
          </li>
        ))}
      </ol>
      <p className="note">مضى {ar(m)}:{ar(String(sec).padStart(2, "0"))} — البحث الكامل قد يستغرق عدة دقائق، ويمكنك ترك الصفحة مفتوحة.</p>
    </div>
  );
}

/** The report itself: disclaimer, the model's Markdown, and where it came from. */
export function AiReportBody({ r }: { r: AiReportData }) {
  return (
    <>
      <p className="ai-disclaimer">{r.disclaimer}</p>
      {r.confidence_label && (
        <p className="ai-verdict">التقييم النهائي: <strong>{r.confidence_label}</strong>
          {r.checks && <span className="note"> — المصادر العلمية المتحقق منها في نتائج البحث: {ar(r.checks.verified_sources)}{r.checks.unverified_sources ? `، وغير المتحقق منها: ${ar(r.checks.unverified_sources)}` : ""}</span>}
        </p>
      )}
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
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setR(null); setError(null);
    const params = new URLSearchParams({ surah_number: String(s), ayah_number: String(a) });
    fetch(`${API_BASE}/ai-research/report?${params}`)
      .then(async (res) => (res.ok ? setR(await res.json()) : setError((await res.json().catch(() => ({}))).detail || "تعذّر جلب التقرير.")))
      .catch(() => setError("تعذّر الاتصال بالخادم."));
  }, [s, a]);

  async function generate() {
    setBusy(true); setError(null); setJob(null);
    try {
      const body = await startResearch(s, a, setJob);
      setR(body);
      addHistory({ kind: "ai", s, a, surah: body.verse.surah_name, mode: body.mode });
    } catch (e) {
      setError(e instanceof TypeError ? "تعذّر الاتصال بالخادم." : (e as Error).message);
    } finally { setBusy(false); }
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
          {busy && <ResearchProgress job={job} />}
        </div>
      )}
      <p className="error" role="alert">{error}</p>
      <p className="note"><a href={link.ai(s, a)}>افتح في صفحة «الذكاء الاصطناعي في الإعجاز العلمي»</a></p>
    </Layer>
  );
}
