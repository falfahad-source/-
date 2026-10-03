"use client";

import { useEffect, useMemo, useState } from "react";
import ConceptMap from "./components/ConceptMap";
import LinguisticLayer from "./components/LinguisticLayer";
import ScienceLayer from "./components/ScienceLayer";
import TafsirTimeline from "./components/TafsirTimeline";
import { ayahCount, LayerHead, SurahName, TrustBadge } from "./components/common";
import type { Answer, SearchResult } from "./components/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const PAGE_SIZE = 50;
const START: [number, number] = [24, 40]; // the concept document's use case

export default function Home() {
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [num, setNum] = useState<[number, number]>(START);
  const [phrase, setPhrase] = useState<string | null>(null);
  const [explore, setExplore] = useState<{ surah_number: number; ayah_number: number; surah_name: string; concepts: string[] }[]>([]);

  async function load(s: number, a: number, scroll = true) {
    setError(null);
    const res = await fetch(`${API_BASE}/verse/${s}/${a}`);
    if (!res.ok) {
      setError((await res.json()).detail || "تعذّر جلب الآية.");
      return;
    }
    const data: Answer = await res.json();
    setAnswer(data);
    setNum([s, a]);
    setPhrase(data.concepts[0]?.key ?? null);
    try { history.replaceState(null, "", `?v=${s}:${a}`); } catch { /* not allowed in some frames */ }
    if (scroll) document.getElementById("journey")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  useEffect(() => {
    const m = /^(\d{1,3}):(\d{1,3})$/.exec(new URLSearchParams(location.search).get("v") ?? "");
    load(m ? +m[1] : START[0], m ? +m[2] : START[1], false);
    fetch(`${API_BASE}/explore`).then((r) => (r.ok ? r.json() : { verses: [] })).then((d) => setExplore(d.verses)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function fetchPage(q: string, offset: number): Promise<SearchResult | null> {
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
    try { setSearch(await fetchPage(query, 0)); } finally { setSearching(false); }
  }

  // Appends the next page of the query the shown results came from, so editing
  // the box without pressing بحث never mixes results of two different searches.
  async function loadMore() {
    if (!search) return;
    setSearching(true);
    try {
      const next = await fetchPage(search.query, search.results.length);
      if (next) setSearch({ ...next, results: [...search.results, ...next.results] });
    } finally { setSearching(false); }
  }

  const highlight = useMemo(() => {
    const p = answer?.concepts.find((c) => c.key === phrase);
    const set = new Set<number>();
    if (p) for (let i = p.words[0]; i <= p.words[1]; i++) set.add(i);
    return set;
  }, [answer, phrase]);

  return (
    <div className="shell">
      <header className="masthead">
        <h1>آفاق <span>| AFAQ</span></h1>
        <p>حين يلتقي التفسير بالمعرفة — استكشاف الآية عبر التفسير الموثق والمعرفة العلمية، مع تصنيف واضح لكل معلومة.</p>
      </header>

      <form className="searchbar" onSubmit={runSearch} role="search">
        <input id="q" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="اكتب جزءًا من الآية، مثل: ظلمات بعضها فوق بعض" aria-label="البحث في نص الآيات" />
        <button className="btn-primary" type="submit" disabled={searching}>{searching ? "جارٍ البحث..." : "بحث"}</button>
      </form>
      <details className="by-number">
        <summary>أو اختر بالرقم</summary>
        <div>
          <input id="surah" type="number" min={1} max={114} value={num[0]} aria-label="رقم السورة"
            onChange={(e) => setNum([Number(e.target.value), num[1]])} />
          <input id="ayah" type="number" min={1} value={num[1]} aria-label="رقم الآية"
            onChange={(e) => setNum([num[0], Number(e.target.value)])} />
          <button type="button" className="btn-ghost" onClick={() => load(num[0], num[1])}>استكشاف</button>
        </div>
      </details>
      <p className="error" role="alert">{error}</p>

      <div className="layout">
        <aside className="results" aria-label="نتائج البحث">
          <h2>{search ? "نتائج البحث" : "آيات نموذجية"}</h2>
          {!search ? (
            <>
              <p className="empty">ابحث بجزء من آية، ثم اختر الآية لتبدأ رحلتها. أو ابدأ بآية من الآيات النموذجية التي أُعدّت لها خريطة مفاهيم:</p>
              <ol>
                {explore.map((v) => (
                  <li key={`${v.surah_number}:${v.ayah_number}`}>
                    <button type="button" className="hit" onClick={() => load(v.surah_number, v.ayah_number)}
                      aria-pressed={answer?.surah_number === v.surah_number && answer?.ayah_number === v.ayah_number}>
                      <span className="ref">سورة <SurahName name={v.surah_name} /> — <b>الآية {v.ayah_number}</b></span>
                      <span className="note">{v.concepts.join("، ")}</span>
                    </button>
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <>
              <p>
                {search.total === 0 ? "لا توجد آيات تحتوي هذا النص."
                  : search.total > search.results.length
                    ? `وُجدت ${ayahCount(search.total)}، يُعرض منها ${search.results.length}. اختر الآية:`
                    : `وُجدت ${ayahCount(search.total)}. اختر الآية:`}
              </p>
              <ol>
                {search.results.map((r) => (
                  <li key={`${r.surah_number}:${r.ayah_number}`}>
                    <button type="button" className="hit" onClick={() => load(r.surah_number, r.ayah_number)}
                      aria-pressed={answer?.surah_number === r.surah_number && answer?.ayah_number === r.ayah_number}>
                      <span className="ref">سورة <SurahName name={r.surah_name} /> — <b>الآية {r.ayah_number}</b></span>
                      <span className="ayah">{r.text}</span>
                    </button>
                  </li>
                ))}
              </ol>
              {search.results.length < search.total && (
                <button type="button" className="btn-ghost more" onClick={loadMore} disabled={searching}>
                  {searching ? "جارٍ التحميل..." : `عرض المزيد (المتبقي ${search.total - search.results.length})`}
                </button>
              )}
            </>
          )}
        </aside>

        {answer && <Journey a={answer} highlight={highlight} onPhrase={setPhrase} open={(s, a) => load(s, a)} />}
      </div>

      <footer className="foot">
        نص المصحف: مجمع الملك فهد لطباعة المصحف الشريف (رواية حفص، الإصدار 3.0). التفاسير والغريب والإعراب والموضوعات:
        {" "}<a href="https://quranpedia.net" target="_blank" rel="noopener noreferrer">الموسوعة القرآنية Quranpedia.net</a>.
        التحليل الصرفي: Quranic Arabic Corpus (corpus.quran.com). آفاق لا يطلب من الذكاء الاصطناعي تفسير القرآن، بل يستعمله للتنقل في المعرفة الموثقة حوله.
        {" "}<a href="/review">مراجعة المقارنات (للباحثين)</a>.
      </footer>
    </div>
  );
}

function Journey({ a, highlight, onPhrase, open }: {
  a: Answer; highlight: Set<number>; onPhrase: (k: string | null) => void; open: (s: number, a: number) => void;
}) {
  return (
    <main className="journey" id="journey">
      <section className="card verse-card" aria-label="الآية">
        <div className="layer-head"><h2 style={{ margin: 0 }}>الآية</h2><TrustBadge trust="QURANIC_TEXT" /></div>
        <p className="verse">{a.quranic_text}</p>
        <div className="meta">
          <span>سورة <SurahName name={a.surah_name} /></span><span>الآية <b>{a.ayah_number}</b></span>
          {a.page_number != null && <span>الصفحة <b>{a.page_number}</b></span>}
          {a.juz_number != null && <span>الجزء <b>{a.juz_number}</b></span>}
        </div>
        <div className="legend" aria-label="فئات الثقة">
          {a.trust_legend.map((t) => <TrustBadge key={t.category} trust={t.category} title={t.description} />)}
        </div>
      </section>

      <nav className="stepnav" aria-label="طبقات الرحلة">
        <a href="#language"><b>١</b>التحليل اللغوي</a>
        <a href="#tafsir"><b>٢</b>التفسير عبر العصور</a>
        <a href="#concepts"><b>٣</b>المفاهيم والظواهر</a>
        <a href="#science"><b>٤</b>المعرفة العلمية</a>
        {a.hadith_matches.length > 0 && <a href="#hadith">الأحاديث</a>}
        <a href="#limits">ما لا تثبته المصادر</a>
      </nav>

      <LinguisticLayer key={`l-${a.surah_number}-${a.ayah_number}`} a={a} highlight={highlight} />
      <TafsirTimeline a={a} />
      <ConceptMap key={`m-${a.surah_number}-${a.ayah_number}`} a={a} open={open} onPhrase={onPhrase} />
      <ScienceLayer a={a} open={open} />

      {a.hadith_matches.length > 0 && (
        <section className="card" id="hadith">
          <LayerHead title="أحاديث مرتبطة بالبحث النصي" trust="POSSIBLE_CONNECTION">
            {a.hadith_matches[0].label} كلمات البحث: «{a.hadith_matches[0].search_query}». تحقق من حكم كل حديث.
          </LayerHead>
          {a.hadith_matches.map((h, i) => (
            <div className="hadith" key={i}>
              <p className="read" style={{ margin: 0 }}>{h.text}</p>
              <p style={{ margin: "4px 0 0" }}><strong>حكم المحدث:</strong> {h.grade || "غير مذكور"}</p>
              <span className="note">الراوي: {h.narrator || "غير مذكور"} — المحدث: {h.muhaddith || "غير مذكور"} — المصدر: {h.book || "غير مذكور"}{h.reference && ` (${h.reference})`}</span>
            </div>
          ))}
        </section>
      )}

      <section className="card" id="limits">
        <LayerHead title="ما لا تثبته المصادر" />
        {a.not_established.length === 0 ? <p className="empty">لا توجد ملاحظات.</p>
          : <ul className="notes">{a.not_established.map((m, i) => <li key={i}>{m}</li>)}</ul>}
        <h3 className="subhead">المصادر</h3>
        <ul className="sources">
          {a.sources.map((s, i) => (
            <li key={i}>
              {/^https?:/.test(s.url) ? <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a> : <span>{s.title}</span>}
              <span className="note">{s.publisher}</span>
              <TrustBadge trust={s.trust_category} />
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
