"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Footer from "../components/Footer";
import ShareVerse from "../components/ShareVerse";
import SiteNav from "../components/SiteNav";
import { ar, SurahName } from "../components/common";
import { DEMO, link, readParams } from "../components/links";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type SurahInfo = { number: number; name: string; ayah_count: number; start_page: number; curated_ayahs: number; ijaz_ayahs: number };
type PageVerse = { surah_number: number; surah_name: string; ayah_number: number; text: string; juz_number: number | null; curated: boolean; ijaz_articles: number };
type MushafPage = { page: number; pages: number; juz: number[]; basmala: string | null; verses: PageVerse[] };
type Sel = { p: number | null; s: number | null; a: number | null };

// Surah names are stored in Uthmani script; strip the marks so the index filter matches plain typing.
// \u escapes: literal Arabic in a character class is reordered by right-to-left editors
const plain = (t: string) => t.replace(/[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]/g, "").replace(/[\u0623\u0625\u0622\u0671]/g, "\u0627").replace(/\u0629/g, "\u0647").replace(/\u0649/g, "\u064a");
const MARKS_KEY = "afaq-mushaf-marks";

function current(): Sel {
  const p = readParams();
  const num = (k: string, max: number) => { const v = Number(p.get(k)); return v >= 1 && v <= max ? v : null; };
  return { p: num("p", 604), s: num("s", 114), a: num("a", 286) };
}

export default function QuranPage() {
  const [index, setIndex] = useState<SurahInfo[]>([]);
  const [juzPages, setJuzPages] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState("");
  const [sel, setSel] = useState<Sel>({ p: null, s: null, a: null });
  const [page, setPage] = useState<MushafPage | null>(null);
  const [goTo, setGoTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  // the i'jaz underlines are off by default, so the page reads as a mushaf; the reader's choice is kept
  const [marks, setMarks] = useState(false);
  useEffect(() => { try { setMarks(localStorage.getItem(MARKS_KEY) === "1"); } catch { /* storage blocked */ } }, []);
  const showMarks = (on: boolean) => { setMarks(on); try { localStorage.setItem(MARKS_KEY, on ? "1" : "0"); } catch { /* storage blocked */ } };

  // address -> state. A surah/ayah without a page (an older link, or a link from elsewhere in the
  // site) is turned into the page that verse is on.
  const sync = useCallback(async () => {
    const c = current();
    if (c.p || !c.s) { setSel(c); return; }
    try {
      const r = await fetch(`${API_BASE}/surah/${c.s}`);
      if (!r.ok) { setSel({ p: null, s: null, a: null }); return; }
      const surah: { verses: { ayah_number: number; page_number: number | null }[] } = await r.json();
      const v = surah.verses.find((x) => x.ayah_number === (c.a ?? 1)) ?? surah.verses[0];
      const next = { p: v.page_number ?? 1, s: c.s, a: c.a };
      history.replaceState(null, "", link.mushafPage(next.p, next.s, next.a ?? undefined));
      setSel(next);
    } catch { setError("تعذّر الاتصال بالخادم."); }
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/surahs`).then(async (r) => {
      if (!r.ok) { setError("تعذّر جلب فهرس السور."); return; }
      const d = await r.json();
      setIndex(d.surahs); setJuzPages(d.juz_pages ?? {});
    }).catch(() => setError("تعذّر الاتصال بالخادم."));
    sync();
    const on = () => { sync(); };
    addEventListener("popstate", on);
    addEventListener("hashchange", on);
    return () => { removeEventListener("popstate", on); removeEventListener("hashchange", on); };
  }, [sync]);

  useEffect(() => {
    if (!sel.p) { setPage(null); return; }
    if (page?.page === sel.p) return;
    setError(null);
    fetch(`${API_BASE}/page/${sel.p}`).then(async (r) => {
      if (!r.ok) { setError((await r.json().catch(() => ({}))).detail || "تعذّر جلب الصفحة."); return; }
      setPage(await r.json());
      if (!sel.a) scrollTo(0, 0);
    }).catch(() => setError("تعذّر الاتصال بالخادم."));
  }, [sel.p]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (page && sel.s && sel.a) document.getElementById(`a${sel.s}-${sel.a}`)?.scrollIntoView({ block: "center" });
  }, [page, sel.s, sel.a]);

  const go = useCallback((p: number | null, s: number | null = null, a: number | null = null, push = true) => {
    const href = p ? link.mushafPage(p, s ?? undefined, a ?? undefined) : link.quran();
    if (DEMO && push) location.hash = href;
    else history[push ? "pushState" : "replaceState"](null, "", href);
    setSel({ p, s, a });
  }, []);

  // keyboard: as in a book read right to left, ← is the next page and → the previous
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!page || (e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowLeft" && page.page < page.pages) go(page.page + 1);
      if (e.key === "ArrowRight" && page.page > 1) go(page.page - 1);
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [page, go]);

  const shown = useMemo(() => {
    // digits typed either way: «18» or «١٨»
    const f = plain(filter.trim()).replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x660));
    return f ? index.filter((x) => plain(x.name).includes(f) || String(x.number) === f) : index;
  }, [index, filter]);

  const verse = page?.verses.find((v) => v.surah_number === sel.s && v.ayah_number === sel.a);
  const toggle = (v: PageVerse) => {
    const same = sel.s === v.surah_number && sel.a === v.ayah_number;
    go(sel.p, same ? null : v.surah_number, same ? null : v.ayah_number, false);
  };
  const total = page?.pages ?? 604;

  function jump(e: React.FormEvent) {
    e.preventDefault();
    const n = Number(goTo);
    if (n >= 1 && n <= total) { go(n); setGoTo(""); }
  }

  const pageForm = (id = "goto") => (
    <form className="page-jump" onSubmit={jump}>
      <label htmlFor={id}>اذهب إلى الصفحة</label>
      <input id={id} type="number" min={1} max={total} value={goTo} onChange={(e) => setGoTo(e.target.value)} placeholder={`${ar(1)}–${ar(total)}`} />
      <button type="submit" className="btn-ghost">اذهب</button>
    </form>
  );

  // the same bar above and below the page, so a reader at the foot of the page turns it there
  const pageNav = (bottom = false) => sel.p && (
    <nav className={`page-nav${bottom ? " page-nav-bottom" : ""}`} aria-label={bottom ? "التنقل بين الصفحات (أسفل الصفحة)" : "التنقل بين الصفحات"}>
      <a href={link.quran()} onClick={(e) => { e.preventDefault(); go(null); }}>فهرس السور</a>
      <span className="page-nav-turn">
        <button type="button" className="btn-ghost" disabled={sel.p <= 1} onClick={() => go(sel.p! - 1)}>→ السابقة</button>
        <span className="page-of">صفحة {ar(sel.p)} من {ar(total)}</span>
        <button type="button" className="btn-ghost" disabled={sel.p >= total} onClick={() => go(sel.p! + 1)}>التالية ←</button>
      </span>
      {pageForm(bottom ? "goto-bottom" : "goto")}
    </nav>
  );

  return (
    <div className="shell">
      <SiteNav current="quran" />
      <header className="masthead">
        <h1>القرآن الكريم</h1>
        <p>تصفّح المصحف صفحةً صفحة كما في مصحف المدينة النبوية (٦٠٤ صفحات)، واضغط أي آية لتنتقل إلى تفسيرها وما يتصل بها من المعرفة العلمية والإعجاز العلمي إن وُجد.</p>
      </header>
      <p className="error" role="alert">{error}</p>

      {!sel.p && (
        <>
          <div className="index-tools">
            <input className="filter" type="search" value={filter} onChange={(e) => setFilter(e.target.value)}
              placeholder="ابحث عن سورة بالاسم أو الرقم" aria-label="ابحث عن سورة" />
            {pageForm()}
          </div>
          <Legend />
          <ol className="surah-grid">
            {shown.map((x) => (
              <li key={x.number}>
                <a href={link.mushafPage(x.start_page)} onClick={(e) => { e.preventDefault(); go(x.start_page); }}>
                  <span className="num">{ar(x.number)}</span>
                  <span className="name"><SurahName name={x.name} /></span>
                  <span className="note">{ar(x.ayah_count)} آية — ص {ar(x.start_page)}</span>
                  {(x.curated_ayahs > 0 || x.ijaz_ayahs > 0) && (
                    <span className="marks">
                      {x.curated_ayahs > 0 && <span className="mark mark-curated" title={`${ar(x.curated_ayahs)} من آياتها لها مقارنة علمية موثّقة`}>{ar(x.curated_ayahs)}</span>}
                      {x.ijaz_ayahs > 0 && <span className="mark mark-ijaz" title={`${ar(x.ijaz_ayahs)} من آياتها لها مقالات في الإعجاز العلمي`}>{ar(x.ijaz_ayahs)}</span>}
                    </span>
                  )}
                </a>
              </li>
            ))}
          </ol>
          {Object.keys(juzPages).length > 0 && (
            <>
              <h2 className="subhead">الأجزاء</h2>
              <ol className="juz-list">
                {Object.entries(juzPages).map(([j, p]) => (
                  <li key={j}><a href={link.mushafPage(p)} onClick={(e) => { e.preventDefault(); go(p); }}>الجزء {ar(j)}<small>ص {ar(p)}</small></a></li>
                ))}
              </ol>
            </>
          )}
        </>
      )}

      {sel.p && (
        <>
          {pageNav()}
          <Legend toggle={{ on: marks, set: showMarks }} />

          <main className="mushaf-page" aria-label={`صفحة ${sel.p}`}>
            {!page || page.page !== sel.p ? <p className="empty">جارٍ التحميل...</p> : (
              <>
                <div className="mushaf-top">
                  <span>{[...new Map(page.verses.map((v) => [v.surah_number, v.surah_name])).values()].map((n, i) => (
                    <span key={i}>{i > 0 && " · "}<SurahName name={n} /></span>
                  ))}</span>
                  <span>{page.juz.map((j) => `الجزء ${ar(j)}`).join("، ")}</span>
                </div>
                {/* as in the printed mushaf, the two opening pages are centered */}
                <div className={`mushaf-text${page.page <= 2 ? " opening" : ""}`}>
                  {page.verses.map((v) => (
                    <span key={`${v.surah_number}:${v.ayah_number}`}>
                      {v.ayah_number === 1 && (
                        <span className="surah-head">
                          <span className="surah-title">سورة <SurahName name={v.surah_name} /></span>
                          {v.surah_number !== 1 && v.surah_number !== 9 && page.basmala && <span className="basmala">{page.basmala}</span>}
                        </span>
                      )}
                      {/* a span, not a <button>: buttons lay out as closed boxes, which would start
                          every ayah on a new line instead of flowing as in the mushaf */}
                      <span id={`a${v.surah_number}-${v.ayah_number}`} role="button" tabIndex={0}
                        className={`ayah${marks && v.curated ? " has-curated" : ""}${marks && v.ijaz_articles ? " has-ijaz" : ""}`}
                        aria-pressed={sel.s === v.surah_number && sel.a === v.ayah_number}
                        aria-label={`سورة ${v.surah_name} الآية ${v.ayah_number}${v.curated ? "، لها مقارنة علمية" : ""}${v.ijaz_articles ? "، لها مقالات في الإعجاز العلمي" : ""}`}
                        onClick={() => toggle(v)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(v); } }}>
                        {v.text}
                      </span>{" "}
                    </span>
                  ))}
                </div>
                <div className="mushaf-foot">{ar(page.page)}</div>
              </>
            )}
          </main>
          {pageNav(true)}
        </>
      )}

      {page && verse && (
        <aside className="ayah-panel" aria-label="الآية المختارة">
          <div className="ayah-panel-head">
            <strong>سورة <SurahName name={verse.surah_name} /> — الآية {ar(verse.ayah_number)}</strong>
            <span className="note">الصفحة {ar(page.page)}{verse.juz_number != null && `، الجزء ${ar(verse.juz_number)}`}</span>
            <button type="button" className="btn-ghost" onClick={() => go(sel.p, null, null, false)} aria-label="إغلاق">إغلاق</button>
          </div>
          <p className="ayah-panel-marks note">
            {verse.curated && <span className="mark mark-curated">مقارنة علمية موثّقة</span>}
            {verse.ijaz_articles > 0 && <span className="mark mark-ijaz">{ar(verse.ijaz_articles)} من مقالات الإعجاز العلمي</span>}
            {!verse.curated && !verse.ijaz_articles && "لا توجد لهذه الآية مقارنة علمية أو مقالات إعجاز في مصادر آفاق حتى الآن؛ التفسير متاح دائمًا."}
          </p>
          <div className="ayah-actions">
            <a className="btn-primary" href={link.verse(verse.surah_number, verse.ayah_number)}>التفسير والإعجاز العلمي</a>
            <a className="btn-ai" href={link.ai(verse.surah_number, verse.ayah_number)}>✦ الذكاء الاصطناعي في الإعجاز العلمي</a>
          </div>
          <ShareVerse s={verse.surah_number} a={verse.ayah_number} surah={verse.surah_name} text={verse.text} />
        </aside>
      )}
      <Footer />
    </div>
  );
}

/** What the coloured marks mean; on a page, also the switch that shows them under the ayahs. */
function Legend({ toggle }: { toggle?: { on: boolean; set: (on: boolean) => void } }) {
  return (
    <div className="map-legend mushaf-legend">
      {toggle && (
        <label className="switch">
          <input type="checkbox" checked={toggle.on} onChange={(e) => toggle.set(e.target.checked)} />
          إظهار علامات الإعجاز
        </label>
      )}
      {(!toggle || toggle.on) && (
        <>
          <span className="mark mark-curated" title="أعدّ آفاق للآية مقارنة علمية موثّقة المصادر">مقارنة علمية موثّقة في آفاق</span>
          <span className="mark mark-ijaz" title="تتناول الآية مقالات في الإعجاز العلمي (موقع الإعجاز العلمي، مصدر ثانوي)">مقالات في الإعجاز العلمي من مصدر ثانوي</span>
          {toggle && <span className="note">(خط أخضر مزدوج: الاثنان معًا)</span>}
        </>
      )}
    </div>
  );
}
