"use client";

import { useEffect, useMemo, useState } from "react";
import ConceptMap from "../components/ConceptMap";
import LinguisticLayer from "../components/LinguisticLayer";
import ScienceLayer from "../components/ScienceLayer";
import SiteNav from "../components/SiteNav";
import TafsirTimeline from "../components/TafsirTimeline";
import { ayahCount, LayerHead, SurahName, TrustBadge } from "../components/common";
import { addHistory } from "../components/history";
import { DEMO, link, readParams, replaceUrl, verseParam } from "../components/links";
import type { Answer, SearchResult, TopicReason, TopicResult } from "../components/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const PAGE_SIZE = 50;
const START: [number, number] = [24, 40]; // the concept document's use case, for the number picker

export default function SearchPage() {
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  // one query, two answers: verses whose text contains it, and verses the sources link to it as a topic
  const [search, setSearch] = useState<{ query: string; text: SearchResult | null; topic: TopicResult | null } | null>(null);
  const [tab, setTab] = useState<"topic" | "text">("topic");
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
    addHistory({ kind: "verse", s, a, surah: data.surah_name });
    replaceUrl(link.verse(s, a));
    if (scroll) document.getElementById("journey")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  useEffect(() => {
    // a verse to open (from the Quran browser, the history, a shared link) or a query to run again
    const p = readParams();
    const v = verseParam(p);
    if (v) load(v[0], v[1], false);
    const initial = p.get("q");
    if (initial) { setQuery(initial); runQuery(initial); }
    else if (!v) document.getElementById("q")?.focus();
    fetch(`${API_BASE}/explore`).then((r) => (r.ok ? r.json() : { verses: [] })).then((d) => setExplore(d.verses)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function fetchPage<T>(path: string, q: string, offset: number): Promise<T | { error: string }> {
    const params = new URLSearchParams({ q, limit: String(PAGE_SIZE), offset: String(offset) });
    try {
      const res = await fetch(`${API_BASE}${path}?${params}`);
      if (!res.ok) return { error: (await res.json().catch(() => ({}))).detail || "تعذّر البحث." };
      return res.json();
    } catch { return { error: "تعذّر الاتصال بالخادم." }; }
  }
  const ok = <T,>(r: T | { error: string }): T | null => (r && typeof r === "object" && "error" in r ? null : r as T);

  async function runQuery(q: string) {
    setError(null);
    setSearch(null);
    setSearching(true);
    try {
      const [t, p] = await Promise.all([fetchPage<SearchResult>("/search", q, 0), fetchPage<TopicResult>("/search/ai", q, 0)]);
      const text = ok(t), topic = ok(p);
      if (!text && !topic) { setError((t as { error: string }).error); return; }
      setSearch({ query: q, text, topic });
      // a verse fragment (several words) finds a few verses by text; a subject — one word, or none
      // or too many text matches — is better served by topic
      const nText = text?.total ?? 0, nTopic = topic?.total ?? 0;
      const fragment = q.trim().split(/\s+/).length >= 2 && nText >= 1 && nText <= 5;
      setTab(nTopic > 0 && !fragment ? "topic" : "text");
      addHistory({ kind: "search", query: q.trim(), total: Math.max(nText, nTopic) });
    } finally { setSearching(false); }
  }

  function runSearch(e: React.FormEvent) {
    e.preventDefault();
    runQuery(query);
  }

  // Appends the next page of the query the shown results came from, so editing
  // the box without pressing بحث never mixes results of two different searches.
  async function loadMore() {
    const cur = search?.[tab];
    if (!search || !cur) return;
    setSearching(true);
    try {
      const next = ok(await fetchPage<SearchResult & TopicResult>(tab === "text" ? "/search" : "/search/ai", search.query, cur.results.length));
      if (next) setSearch({ ...search, [tab]: { ...next, results: [...cur.results, ...next.results] } });
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
      <SiteNav current="search" />
      <header className="masthead">
        <h1>بحث جديد</h1>
        <p>ابحث بجزء من آية، أو بموضوع مثل «ذكاء الإنسان» ليقترح الذكاء الاصطناعي الآيات المتصلة به، ثم اختر الآية لتبدأ رحلتها.</p>
      </header>

      <form className="searchbar" onSubmit={runSearch} role="search">
        <input id="q" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="جزء من آية أو موضوع، مثل: ظلمات بعضها فوق بعض، أو مدة الرضاعة الطبيعية" aria-label="البحث بنص الآية أو بالموضوع" />
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
              <p className="empty">ابحث بجزء من آية أو بموضوع، ثم اختر الآية لتبدأ رحلتها. أو ابدأ بآية من الآيات النموذجية التي أُعدّت لها خريطة مفاهيم:</p>
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
              <div className="tabs result-tabs" role="tablist" aria-label="نوع النتائج">
                <button type="button" role="tab" className="btn-ghost" aria-selected={tab === "topic"} onClick={() => setTab("topic")}>
                  ✦ بالذكاء الاصطناعي ({search.topic?.total ?? 0})
                </button>
                <button type="button" role="tab" className="btn-ghost" aria-selected={tab === "text"} onClick={() => setTab("text")}>
                  نص الآية ({search.text?.total ?? 0})
                </button>
              </div>
              {tab === "topic" ? <TopicHits r={search.topic} answer={answer} load={load} />
                : <TextHits r={search.text} answer={answer} load={load} />}
              {(() => {
                const cur = search[tab];
                return cur && cur.results.length < cur.total && (
                  <button type="button" className="btn-ghost more" onClick={loadMore} disabled={searching}>
                    {searching ? "جارٍ التحميل..." : `عرض المزيد (المتبقي ${cur.total - cur.results.length})`}
                  </button>
                );
              })()}
            </>
          )}
        </aside>

        {answer ? <Journey a={answer} highlight={highlight} onPhrase={setPhrase} open={(s, a) => load(s, a)} />
          : (
            <main className="journey">
              <section className="card">
                <LayerHead title="ابدأ رحلة الآية" />
                <p className="lead">اكتب جزءًا من آية أو موضوعًا مثل «ذكاء الإنسان» في مربع البحث، ثم اختر الآية من النتائج لتظهر طبقاتها: التحليل اللغوي، والتفسير عبر العصور، والمفاهيم، والمعرفة العلمية.</p>
                <p className="note">أو تصفّح المصحف من <a href={link.quran()}>القرآن الكريم</a>، أو عُد إلى بحث سابق من <a href={link.history()}>سجل البحث</a>.</p>
              </section>
            </main>
          )}
      </div>

      <footer className="foot">
        نص المصحف: مجمع الملك فهد لطباعة المصحف الشريف (رواية حفص، الإصدار 3.0).
        <br />
        آفاق لا يطلب من الذكاء الاصطناعي تفسير القرآن، بل يستعمله للتنقل في المعرفة الموثقة حوله.
        {!DEMO && <><br /><a href="/review">مراجعة المقارنات (للباحثين)</a></>}
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
        <a href={link.ai(a.surah_number, a.ayah_number)}><b>✦</b>الذكاء الاصطناعي في الإعجاز العلمي</a>
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

type Hits = { answer: Answer | null; load: (s: number, a: number) => void };

function VerseHit({ r, answer, load, children }: Hits & {
  r: { surah_number: number; ayah_number: number; surah_name: string; text: string }; children?: React.ReactNode;
}) {
  return (
    <li>
      <button type="button" className="hit" onClick={() => load(r.surah_number, r.ayah_number)}
        aria-pressed={answer?.surah_number === r.surah_number && answer?.ayah_number === r.ayah_number}>
        <span className="ref">سورة <SurahName name={r.surah_name} /> — <b>الآية {r.ayah_number}</b></span>
        <span className="ayah">{r.text}</span>
        {children}
      </button>
    </li>
  );
}

function TextHits({ r, ...h }: Hits & { r: SearchResult | null }) {
  if (!r) return <p className="empty">اكتب حرفين عربيين على الأقل للبحث في نص الآيات.</p>;
  return (
    <>
      <p>
        {r.total === 0 ? "لا توجد آيات تحتوي هذا النص."
          : r.total > r.results.length
            ? `وُجدت ${ayahCount(r.total)} تحتوي هذا النص، يُعرض منها ${r.results.length}. اختر الآية:`
            : `وُجدت ${ayahCount(r.total)} تحتوي هذا النص. اختر الآية:`}
      </p>
      <ol>{r.results.map((x) => <VerseHit key={`${x.surah_number}:${x.ayah_number}`} r={x} {...h} />)}</ol>
    </>
  );
}

const REASON: Record<TopicReason["kind"], string> = {
  concept: "مقارنة علمية", topic: "موضوع", article: "مقال إعجاز", tafsir: "التفسير", ai: "سبب الصلة",
};

function TopicHits({ r, ...h }: Hits & { r: TopicResult | null }) {
  if (!r) return <p className="empty">اكتب موضوعًا من ثلاثة أحرف على الأقل، مثل: ذكاء الإنسان، الرضاعة، البحار.</p>;
  const live = r.mode === "live";
  return (
    <>
      {r.note && <p className="ai-mode mock">{r.note}</p>}
      {live && r.disclaimer && <p className="ai-disclaimer">{r.disclaimer}</p>}
      <p>
        {r.total === 0
          ? (live ? "لم يقترح الذكاء الاصطناعي آيات لهذا الموضوع." : "لم تربط المصادر أي آية بهذا الموضوع. جرّب كلمة أخرى أو ابحث في نص الآية.")
          : `${live ? "اقترح الذكاء الاصطناعي" : "وُجدت"} ${ayahCount(r.total)} ذات صلة بالموضوع، الأقوى صلة أولًا:`}
      </p>
      <ol>
        {r.results.map((x) => (
          <VerseHit key={`${x.surah_number}:${x.ayah_number}`} r={x} {...h}>
            <span className="reasons">
              {x.reasons.map((rs, i) => (
                <span key={i} className={`reason reason-${rs.kind}`}>
                  {rs.kind === "tafsir" ? `ورد في «${rs.label}»` : `${REASON[rs.kind]}: ${rs.label}`}
                  {rs.synonyms?.length ? <em className="via"> — بمرادف «{rs.synonyms.join("»، «")}»</em> : null}
                </span>
              ))}
              {x.more_reasons > 0 && <span className="note">و{x.more_reasons} غيرها</span>}
              {x.corrected && <span className="note">صُحّح رقم الآية من الاقتباس</span>}
            </span>
          </VerseHit>
        ))}
      </ol>
      {live && !!r.dropped && <p className="note">حُذف {ayahCount(r.dropped)} اقترحها النموذج ولم يُعثر على اقتباسها في المصحف.</p>}
      {!live && r.total > 0 && (
        <p className="note">الصلة من مصادر آفاق: مقارناته العلمية، وفهرس موضوعات Quranpedia، وعناوين مقالات الإعجاز (مصدر ثانوي)، ونص التفسير الميسر. ليست تفسيرًا للآية.</p>
      )}
    </>
  );
}
