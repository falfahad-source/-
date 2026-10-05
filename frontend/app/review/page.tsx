"use client";

import { useCallback, useEffect, useState } from "react";
import SiteNav from "../components/SiteNav";
import { SurahName, TrustBadge } from "../components/common";
import type { ReviewStatus, Trust } from "../components/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const TOKEN_KEY = "afaq-reviewer-token";

type Item = {
  key: string; status: ReviewStatus; explanation: string; curated_explanation: string;
  reviewed_by: string | null; reviewed_at: string | null; comment: string | null; source: string;
  verse: { surah_number: number; ayah_number: number; surah_name: string; text: string };
  phrase: { key: string; label: string; text: string; meanings: { word: string; meaning: string; book: string }[] };
  concept: { key: string; name_ar: string; name_en: string | null;
    claims: { claim: string; trust_category: Trust; source: string; url: string | null; quote: string | null; verified_at: string | null }[] };
  history: { reviewer: string; decision: ReviewStatus; comment: string | null; approved_text: string | null; at: string }[];
};
type Queue = { reviewer: string; counts: Record<ReviewStatus, number>; items: Item[] };

const STATUS_LABEL: Record<ReviewStatus, string> = {
  draft: "مسودة", approved: "معتمدة", changes_requested: "طُلب تعديلها", rejected: "مرفوضة",
};

function readToken(): string {
  try { return sessionStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; }
}
function writeToken(t: string | null) {
  try { if (t) sessionStorage.setItem(TOKEN_KEY, t); else sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
}

export default function ReviewPage() {
  const [token, setToken] = useState("");
  const [input, setInput] = useState("");
  const [queue, setQueue] = useState<Queue | null>(null);
  const [filter, setFilter] = useState<ReviewStatus | "all">("draft");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (t: string) => {
    setError(null);
    const res = await fetch(`${API_BASE}/review/queue`, { headers: { Authorization: `Bearer ${t}` } });
    if (!res.ok) {
      setError((await res.json().catch(() => ({}))).detail || "تعذّر تحميل قائمة المراجعة.");
      if (res.status === 401) { writeToken(null); setToken(""); }
      return;
    }
    setQueue(await res.json());
  }, []);

  useEffect(() => { const t = readToken(); if (t) { setToken(t); load(t); } }, [load]);

  function login(e: React.FormEvent) {
    e.preventDefault();
    const t = input.trim();
    writeToken(t); setToken(t); load(t);
  }

  function replace(updated: Item) {
    setQueue((q) => {
      if (!q) return q;
      const items = q.items.map((i) => (i.key === updated.key ? updated : i));
      const counts = { draft: 0, approved: 0, changes_requested: 0, rejected: 0 } as Record<ReviewStatus, number>;
      items.forEach((i) => { counts[i.status] += 1; });
      return { ...q, items, counts };
    });
  }

  if (!token || !queue) {
    return (
      <div className="shell">
        <SiteNav current="review" />
        <header className="masthead"><h1>مراجعة المقارنات</h1></header>
        <p className="lead">هذه الصفحة للباحثين المعتمدين: تراجع فيها المقارنات العلمية المقترحة قبل أن تظهر معتمدة للمستخدمين.</p>
        <form className="login" onSubmit={login}>
          <label htmlFor="token">رمز المراجع</label>
          <input id="token" type="password" autoComplete="off" value={input} onChange={(e) => setInput(e.target.value)} />
          <button className="btn-primary" type="submit" style={{ padding: "8px 16px" }}>دخول</button>
        </form>
        <p className="error" role="alert">{error}</p>
        <p className="note">يحصل الباحث على رمزه من مدير الخادم (إعداد AFAQ_REVIEWERS). يُحفظ الرمز في هذا التبويب فقط.</p>
      </div>
    );
  }

  const shown = queue.items.filter((i) => filter === "all" || i.status === filter);
  return (
    <div className="shell">
      <SiteNav current="review" />
      <header className="masthead">
        <h1>مراجعة المقارنات</h1>
        <p>المراجع: <strong>{queue.reviewer}</strong> — <button type="button" className="btn-ghost" onClick={() => { writeToken(null); setToken(""); setQueue(null); }}>خروج</button></p>
      </header>
      <div className="review-top">
        <div className="tabs" role="tablist" aria-label="تصفية حسب الحالة">
          {(["draft", "changes_requested", "approved", "rejected", "all"] as const).map((k) => (
            <button key={k} type="button" role="tab" aria-selected={filter === k} className="btn-ghost" onClick={() => setFilter(k)}>
              {k === "all" ? `الكل (${queue.items.length})` : `${STATUS_LABEL[k]} (${queue.counts[k] ?? 0})`}
            </button>
          ))}
        </div>
        <a href="/" className="note">العودة إلى الموقع</a>
      </div>
      <p className="error" role="alert">{error}</p>
      {shown.length === 0 && <p className="empty">لا توجد مقارنات بهذه الحالة.</p>}
      <div className="journey">
        {shown.map((i) => <ReviewCard key={i.key} item={i} token={token} onSaved={replace} onError={setError} />)}
      </div>
    </div>
  );
}

function ReviewCard({ item, token, onSaved, onError }: {
  item: Item; token: string; onSaved: (i: Item) => void; onError: (m: string | null) => void;
}) {
  const [text, setText] = useState(item.explanation);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const edited = text.trim() !== item.explanation.trim();
  const id = item.key.replace(/[^a-z0-9]/gi, "_");

  async function send(decision: ReviewStatus) {
    onError(null);
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/review/${encodeURIComponent(item.key)}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ decision, comment: comment || null, explanation: decision === "approved" ? text : null }),
      });
      const data = await res.json();
      if (!res.ok) { onError(data.detail || "تعذّر حفظ القرار."); return; }
      onSaved(data);
      setText(data.explanation);
      setComment("");
    } finally { setBusy(false); }
  }

  return (
    <article className="card review-card" aria-labelledby={`h-${id}`}>
      <div className="layer-head">
        <h2 id={`h-${id}`} style={{ fontSize: "1.05rem" }}>
          سورة <SurahName name={item.verse.surah_name} /> {item.verse.ayah_number}:
          {" "}<span style={{ fontFamily: "var(--f-quran)" }}>{item.phrase.label}</span> ↔ {item.concept.name_ar}
        </h2>
        <span className={`status status-${item.status}`}>{STATUS_LABEL[item.status]}</span>
        <a className="note" href={`/search?v=${item.verse.surah_number}:${item.verse.ayah_number}`} target="_blank" rel="noopener noreferrer">عرض الآية</a>
      </div>
      <p className="verse">{item.verse.text}</p>

      <div className="review-grid">
        <section>
          <div className="layer-head"><strong>معنى اللفظ عند أهل الغريب</strong><TrustBadge trust="TAFSIR_VERIFIED" /></div>
          {item.phrase.meanings.length === 0 ? <p className="empty">لا يوجد شرح لهذا اللفظ في كتب الغريب المستوعبة.</p> : (
            <ul className="meaning-list">{item.phrase.meanings.map((m, k) => <li key={k}><b>{m.word}</b>: {m.meaning} <span className="note">— {m.book}</span></li>)}</ul>
          )}
        </section>
        <section>
          <div className="layer-head"><strong>المعلومة العلمية</strong>{item.concept.name_en && <span className="note" dir="ltr">{item.concept.name_en}</span>}</div>
          {item.concept.claims.length === 0 ? <p className="empty">لا يوجد مصدر علمي مرتبط بهذا المفهوم.</p> : item.concept.claims.map((c, k) => (
            <div key={k} style={{ display: "grid", gap: 4, marginBottom: 6 }}>
              <TrustBadge trust={c.trust_category} />
              <span>{c.claim}</span>
              {c.quote && <span className="note" dir="ltr" style={{ textAlign: "right" }}>“{c.quote}”</span>}
              <span className="note">{c.url ? <a href={c.url} target="_blank" rel="noopener noreferrer">{c.source}</a> : c.source}{c.verified_at && ` — طوبق في ${c.verified_at}`}</span>
            </div>
          ))}
        </section>
      </div>

      <label htmlFor={`t-${id}`}><strong>نص المقارنة</strong> <span className="note">(يمكن تعديله قبل الاعتماد)</span></label>
      <textarea id={`t-${id}`} rows={4} value={text} onChange={(e) => setText(e.target.value)} />
      {item.explanation !== item.curated_explanation && <p className="note">النص المعتمد يختلف عن نص الملف الأصلي: «{item.curated_explanation}»</p>}
      <label htmlFor={`c-${id}`}><strong>ملاحظة</strong> <span className="note">(مطلوبة عند طلب التعديل أو الرفض)</span></label>
      <textarea id={`c-${id}`} rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
      <div className="review-actions">
        <button type="button" className="btn-ok" disabled={busy} onClick={() => send("approved")}>{edited ? "اعتماد بعد التعديل" : "اعتماد"}</button>
        <button type="button" className="btn-warn" disabled={busy || !comment.trim()} onClick={() => send("changes_requested")}>طلب تعديل</button>
        <button type="button" className="btn-bad" disabled={busy || !comment.trim()} onClick={() => send("rejected")}>رفض</button>
      </div>
      {item.history.length > 0 && (
        <details>
          <summary className="note">سجل المراجعة ({item.history.length})</summary>
          <ul className="history">
            {item.history.map((h, k) => (
              <li key={k}>{h.at.replace("T", " ")} — {h.reviewer}: {STATUS_LABEL[h.decision]}{h.comment ? ` — «${h.comment}»` : ""}</li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}
