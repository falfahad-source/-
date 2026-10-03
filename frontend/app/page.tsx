"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Answer = {
  quranic_text: string;
  verified_tafsir: { scholar: string | null; text: string; source: string }[];
  possible_connections: { label: string; explanation: string; source: string }[];
  not_established: string[];
  sources: { title: string; url: string }[];
};

export default function Home() {
  const [surah, setSurah] = useState(1);
  const [ayah, setAyah] = useState(1);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    setAnswer(null);
    const res = await fetch(`${API_BASE}/verse/${surah}/${ayah}`);
    if (!res.ok) {
      setError((await res.json()).detail || "تعذّر جلب الآية.");
      return;
    }
    setAnswer(await res.json());
  }

  return (
    <main style={{ maxWidth: 820, margin: "0 auto", padding: 24 }}>
      <h1>آفاق</h1>
      <p style={{ color: "#555" }}>استكشاف مصدرُه موثّق حول آيات القرآن الكريم — تفسير، علوم، ومقارنات مُصنَّفة بوضوح.</p>

      <div style={{ display: "flex", gap: 8, margin: "16px 0" }}>
        <input type="number" value={surah} min={1} max={114} onChange={(e) => setSurah(Number(e.target.value))} placeholder="رقم السورة" />
        <input type="number" value={ayah} min={1} onChange={(e) => setAyah(Number(e.target.value))} placeholder="رقم الآية" />
        <button onClick={load}>استكشاف</button>
      </div>

      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {answer && (
        <article>
          <section>
            <h2>أ. النص القرآني</h2>
            <p style={{ fontSize: 22 }}>{answer.quranic_text}</p>
          </section>

          <section>
            <h2>ج. التفسير الموثّق</h2>
            {answer.verified_tafsir.length === 0 && <p>لا يوجد تفسير موثّق مستوعب بعد لهذه الآية.</p>}
            {answer.verified_tafsir.map((t, i) => (
              <blockquote key={i}>
                <p>{t.text}</p>
                <footer>— {t.scholar || "غير معروف"}، {t.source}</footer>
              </blockquote>
            ))}
          </section>

          <section>
            <h2>هـ. مقارنات محتملة</h2>
            {/* UI must never visually imply this equals tafsir — hence the explicit badge on every card. */}
            {answer.possible_connections.length === 0 && <p>لا توجد مقارنات علمية موثّقة بعد.</p>}
            {answer.possible_connections.map((c, i) => (
              <div key={i} style={{ border: "1px solid #d99", padding: 8, borderRadius: 6 }}>
                <strong style={{ color: "#b00" }}>{c.label}</strong>
                <p>{c.explanation}</p>
                <small>المصدر: {c.source}</small>
              </div>
            ))}
          </section>

          <section>
            <h2>و. ما لا تثبته المصادر</h2>
            <ul>
              {answer.not_established.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </section>

          <section>
            <h2>ز. المصادر</h2>
            <ul>
              {answer.sources.map((s, i) => <li key={i}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>)}
            </ul>
          </section>
        </article>
      )}
    </main>
  );
}
