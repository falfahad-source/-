"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Answer = {
  quranic_text: string;
  surah_number: number;
  ayah_number: number;
  surah_name: string;
  page_number: number | null;
  juz_number: number | null;
  verified_tafsir: { scholar: string | null; text: string; source: string }[];
  possible_connections: { label: string; explanation: string; source: string }[];
  hadith_matches: {
    label: string; search_query: string; text: string; narrator: string | null; muhaddith: string | null;
    book: string | null; reference: string | null; grade: string | null; source: string;
  }[];
  not_established: string[];
  sources: { title: string; url: string }[];
};

type SearchResult = {
  query: string;
  total: number;
  offset: number;
  results: { surah_number: number; surah_name: string; ayah_number: number; text: string; page_number: number | null }[];
};

// Surah names come from KFGQPC in Uthmani script (e.g. the ۡ sukun in النَّمۡلِ),
// which the UI font lacks, so they are rendered in the Hafs font like the verses.
function SurahName({ name }: { name: string }) {
  return <span style={{ fontFamily: '"KFGQPC Hafs", serif' }}>{name}</span>;
}

// Arabic number agreement: 1 آية واحدة، 2 آيتان، 3–10 آيات، 11+ آية.
function ayahCount(n: number): string {
  if (n === 1) return "آية واحدة";
  if (n === 2) return "آيتان";
  return n % 100 >= 3 && n % 100 <= 10 ? `${n} آيات` : `${n} آية`;
}

// Tafsir text is stored verbatim from Quranpedia, which includes markup
// (<span class="book-ayah">, <br />). Show it as plain text: parsing into a
// detached document and reading textContent never executes or injects anything.
function toPlainText(html: string): string {
  const withBreaks = html.replace(/<br\s*\/?>/gi, "\n");
  return new DOMParser().parseFromString(withBreaks, "text/html").body.textContent ?? "";
}

export default function Home() {
  const [surah, setSurah] = useState(1);
  const [ayah, setAyah] = useState(1);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);

  async function load(s: number = surah, a: number = ayah) {
    setError(null);
    setAnswer(null);
    setSurah(s);
    setAyah(a);
    const res = await fetch(`${API_BASE}/verse/${s}/${a}`);
    if (!res.ok) {
      setError((await res.json()).detail || "تعذّر جلب الآية.");
      return;
    }
    setAnswer(await res.json());
  }

  const PAGE_SIZE = 50;

  async function fetchSearchPage(q: string, offset: number): Promise<SearchResult | null> {
    const params = new URLSearchParams({ q, limit: String(PAGE_SIZE), offset: String(offset) });
    const res = await fetch(`${API_BASE}/search?${params}`);
    if (!res.ok) {
      setError((await res.json()).detail || "تعذّر البحث.");
      return null;
    }
    return res.json();
  }

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSearch(null);
    setSearching(true);
    try {
      setSearch(await fetchSearchPage(query, 0));
    } finally {
      setSearching(false);
    }
  }

  // Appends the next page. Uses the query the shown results came from, so editing
  // the box without pressing بحث never mixes results of two different searches.
  async function loadMore() {
    if (!search) return;
    setError(null);
    setSearching(true);
    try {
      const next = await fetchSearchPage(search.query, search.results.length);
      if (next) setSearch({ ...next, results: [...search.results, ...next.results] });
    } finally {
      setSearching(false);
    }
  }

  function choose(s: number, a: number) {
    load(s, a);
    // keep the results so the user can pick another ayah; jump to the answer
    setTimeout(() => document.getElementById("answer")?.scrollIntoView({ behavior: "smooth" }), 0);
  }

  return (
    <main style={{ maxWidth: 820, margin: "0 auto", padding: 24 }}>
      <h1>آفاق</h1>
      <p style={{ color: "#555" }}>استكشاف مصدرُه موثّق حول آيات القرآن الكريم — تفسير، علوم، ومقارنات مُصنَّفة بوضوح.</p>

      <form onSubmit={runSearch} style={{ display: "flex", gap: 8, margin: "16px 0 8px" }}>
        <input
          type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="اكتب جزءًا من الآية، مثل: الله لا إله إلا هو الحي القيوم"
          aria-label="البحث في نص الآيات" style={{ flex: 1, padding: 6 }}
        />
        <button type="submit" disabled={searching}>{searching ? "جارٍ البحث..." : "بحث"}</button>
      </form>

      <details style={{ margin: "0 0 16px", color: "#555" }}>
        <summary>أو اختر بالرقم</summary>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <input type="number" value={surah} min={1} max={114} onChange={(e) => setSurah(Number(e.target.value))} placeholder="رقم السورة" aria-label="رقم السورة" />
          <input type="number" value={ayah} min={1} onChange={(e) => setAyah(Number(e.target.value))} placeholder="رقم الآية" aria-label="رقم الآية" />
          <button onClick={() => load()}>استكشاف</button>
        </div>
      </details>

      {search && (
        <section aria-label="نتائج البحث">
          <p>
            {search.total === 0
              ? "لا توجد آيات تحتوي هذا النص."
              : search.total > search.results.length
                ? `وُجدت ${ayahCount(search.total)}، يُعرض منها ${search.results.length}. اختر الآية التي تريد تفسيرها:`
                : `وُجدت ${ayahCount(search.total)}. اختر الآية التي تريد تفسيرها:`}
          </p>
          <ol style={{ listStyle: "none", padding: 0 }}>
            {search.results.map((r) => {
              const selected = answer?.surah_number === r.surah_number && answer?.ayah_number === r.ayah_number;
              return (
                <li key={`${r.surah_number}:${r.ayah_number}`}>
                  <button
                    onClick={() => choose(r.surah_number, r.ayah_number)}
                    aria-pressed={selected}
                    style={{
                      display: "block", width: "100%", textAlign: "right", cursor: "pointer", marginBottom: 6,
                      padding: 8, borderRadius: 6, border: selected ? "2px solid #2a6" : "1px solid #ccc",
                      background: selected ? "#eefaf2" : "#fff",
                    }}
                  >
                    <strong>سورة <SurahName name={r.surah_name} /> — الآية {r.ayah_number}</strong>
                    <span style={{ display: "block", fontFamily: '"KFGQPC Hafs", serif', fontSize: 22, lineHeight: 1.9 }}>
                      {r.text}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
          {search.results.length < search.total && (
            <button onClick={loadMore} disabled={searching} style={{ display: "block", margin: "0 auto 16px", padding: "6px 16px" }}>
              {searching
                ? "جارٍ التحميل..."
                : `عرض المزيد (المتبقي ${search.total - search.results.length})`}
            </button>
          )}
        </section>
      )}

      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {answer && (
        <article id="answer">
          <section>
            <h2>أ. النص القرآني</h2>
            <p style={{ fontFamily: '"KFGQPC Hafs", serif', fontSize: 30, lineHeight: 2 }}>{answer.quranic_text}</p>
            <p style={{ color: "#555" }}>
              سورة <SurahName name={answer.surah_name} /> — الآية {answer.ayah_number}
              {answer.page_number != null && ` — الصفحة ${answer.page_number}`}
              {answer.juz_number != null && ` — الجزء ${answer.juz_number}`}
            </p>
          </section>

          <section>
            <h2>ج. التفسير الموثّق</h2>
            {answer.verified_tafsir.length === 0 && <p>لا يوجد تفسير موثّق مستوعب بعد لهذه الآية.</p>}
            {answer.verified_tafsir.map((t, i) => (
              <blockquote key={i}>
                <p style={{ whiteSpace: "pre-line" }}>{toPlainText(t.text)}</p>
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

          {answer.hadith_matches.length > 0 && (
            <section>
              <h2>أحاديث مرتبطة بالبحث النصي</h2>
              {/* Keyword matches, not tafsir; results include weak and fabricated narrations,
                  so the scholar's grade is shown on every card, never hidden. */}
              <p style={{ color: "#b00" }}>
                {answer.hadith_matches[0].label} كلمات البحث: «{answer.hadith_matches[0].search_query}». تحقق من حكم كل حديث.
              </p>
              {answer.hadith_matches.map((h, i) => (
                <div key={i} style={{ border: "1px solid #ccc", padding: 8, borderRadius: 6, marginBottom: 8 }}>
                  <p>{h.text}</p>
                  <p style={{ margin: 0 }}><strong>حكم المحدث:</strong> {h.grade || "غير مذكور"}</p>
                  <small>
                    الراوي: {h.narrator || "غير مذكور"} — المحدث: {h.muhaddith || "غير مذكور"} — المصدر: {h.book || "غير مذكور"}
                    {h.reference && ` (${h.reference})`}
                  </small>
                </div>
              ))}
            </section>
          )}

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
