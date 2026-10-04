"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import SiteNav from "../components/SiteNav";
import { SurahName } from "../components/common";
import { DEMO, link, readParams } from "../components/links";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type SurahInfo = { number: number; name: string; ayah_count: number; curated_ayahs: number; ijaz_ayahs: number };
type SurahVerse = { ayah_number: number; text: string; page_number: number | null; juz_number: number | null; curated: boolean; ijaz_articles: number };
type Surah = { number: number; name: string; verses: SurahVerse[] };

// Surah names are stored in Uthmani script; strip the marks so the index filter matches plain typing.
const plain = (t: string) => t.replace(/[ؐ-ًؚ-ٰٟۖ-ۭ]/g, "").replace(/[أإآٱ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي");

function current(): { s: number | null; a: number | null } {
  const p = readParams();
  const s = Number(p.get("s")), a = Number(p.get("a"));
  return { s: s >= 1 && s <= 114 ? s : null, a: a >= 1 ? a : null };
}

export default function QuranPage() {
  const [index, setIndex] = useState<SurahInfo[]>([]);
  const [filter, setFilter] = useState("");
  const [sel, setSel] = useState<{ s: number | null; a: number | null }>({ s: null, a: null });
  const [surah, setSurah] = useState<Surah | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/surahs`).then(async (r) => (r.ok ? setIndex((await r.json()).surahs) : setError("تعذّر جلب فهرس السور.")))
      .catch(() => setError("تعذّر الاتصال بالخادم."));
    const sync = () => setSel(current());
    sync();
    addEventListener("popstate", sync);
    addEventListener("hashchange", sync);
    return () => { removeEventListener("popstate", sync); removeEventListener("hashchange", sync); };
  }, []);

  useEffect(() => {
    if (!sel.s) { setSurah(null); return; }
    if (surah?.number === sel.s) return;
    setError(null);
    fetch(`${API_BASE}/surah/${sel.s}`).then(async (r) => {
      if (!r.ok) { setError((await r.json().catch(() => ({}))).detail || "تعذّر جلب السورة."); return; }
      setSurah(await r.json());
      if (!sel.a) scrollTo(0, 0);
    }).catch(() => setError("تعذّر الاتصال بالخادم."));
  }, [sel.s]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (surah && sel.a) document.getElementById(`a${sel.a}`)?.scrollIntoView({ block: "center" });
  }, [surah, sel.a]);

  const go = useCallback((s: number | null, a: number | null = null, push = true) => {
    const href = link.quran(s ?? undefined, a ?? undefined);
    if (DEMO) { if (push) location.hash = href; else history.replaceState(null, "", href); }
    else history[push ? "pushState" : "replaceState"](null, "", href);
    setSel({ s, a });
  }, []);

  const shown = useMemo(() => {
    const f = plain(filter.trim());
    return f ? index.filter((x) => plain(x.name).includes(f) || String(x.number) === f) : index;
  }, [index, filter]);

  const info = index.find((x) => x.number === sel.s);
  const verse = surah?.verses.find((v) => v.ayah_number === sel.a);

  return (
    <div className="shell">
      <SiteNav current="quran" />
      <header className="masthead">
        <h1>القرآن الكريم</h1>
        <p>تصفّح المصحف، واضغط أي آية لتنتقل إلى تفسيرها وما يتصل بها من المعرفة العلمية والإعجاز العلمي إن وُجد.</p>
      </header>
      <p className="error" role="alert">{error}</p>

      {!sel.s && (
        <>
          <input className="filter" type="search" value={filter} onChange={(e) => setFilter(e.target.value)}
            placeholder="ابحث عن سورة بالاسم أو الرقم" aria-label="ابحث عن سورة" />
          <ol className="surah-grid">
            {shown.map((x) => (
              <li key={x.number}>
                <a href={link.quran(x.number)} onClick={(e) => { e.preventDefault(); go(x.number); }}>
                  <span className="num">{x.number}</span>
                  <span className="name"><SurahName name={x.name} /></span>
                  <span className="note">{x.ayah_count} آية</span>
                  {(x.curated_ayahs > 0 || x.ijaz_ayahs > 0) && (
                    <span className="marks">
                      {x.curated_ayahs > 0 && <span className="mark mark-curated" title="آيات لها مقارنة علمية موثّقة">{x.curated_ayahs}</span>}
                      {x.ijaz_ayahs > 0 && <span className="mark mark-ijaz" title="آيات لها مقالات في الإعجاز العلمي">{x.ijaz_ayahs}</span>}
                    </span>
                  )}
                </a>
              </li>
            ))}
          </ol>
          <Legend />
        </>
      )}

      {sel.s && (
        <main className="card mushaf">
          <div className="mushaf-head">
            <a href={link.quran()} onClick={(e) => { e.preventDefault(); go(null); }}>← فهرس السور</a>
            <h2>سورة <SurahName name={surah?.name ?? info?.name ?? ""} /></h2>
            <span className="mushaf-nav">
              {sel.s > 1 && <a href={link.quran(sel.s - 1)} onClick={(e) => { e.preventDefault(); go(sel.s! - 1); }}>السابقة</a>}
              {sel.s < 114 && <a href={link.quran(sel.s + 1)} onClick={(e) => { e.preventDefault(); go(sel.s! + 1); }}>التالية</a>}
            </span>
          </div>
          {!surah ? <p className="empty">جارٍ التحميل...</p> : (
            <>
              <p className="mushaf-text">
                {surah.verses.map((v) => (
                  <button key={v.ayah_number} id={`a${v.ayah_number}`} type="button"
                    className={`ayah${v.curated ? " has-curated" : ""}${v.ijaz_articles ? " has-ijaz" : ""}`}
                    aria-pressed={sel.a === v.ayah_number}
                    aria-label={`الآية ${v.ayah_number}${v.curated ? "، لها مقارنة علمية" : ""}${v.ijaz_articles ? "، لها مقالات في الإعجاز العلمي" : ""}`}
                    onClick={() => go(sel.s, sel.a === v.ayah_number ? null : v.ayah_number, false)}>
                    {v.text}
                  </button>
                ))}
              </p>
              <Legend />
            </>
          )}
        </main>
      )}

      {surah && verse && (
        <aside className="ayah-panel" aria-label="الآية المختارة">
          <div className="ayah-panel-head">
            <strong>سورة <SurahName name={surah.name} /> — الآية {verse.ayah_number}</strong>
            {verse.page_number != null && <span className="note">الصفحة {verse.page_number}، الجزء {verse.juz_number}</span>}
            <button type="button" className="btn-ghost" onClick={() => go(sel.s, null, false)} aria-label="إغلاق">إغلاق</button>
          </div>
          <p className="ayah-panel-marks note">
            {verse.curated && <span className="mark mark-curated">مقارنة علمية موثّقة</span>}
            {verse.ijaz_articles > 0 && <span className="mark mark-ijaz">{verse.ijaz_articles} من مقالات الإعجاز العلمي</span>}
            {!verse.curated && !verse.ijaz_articles && "لا توجد لهذه الآية مقارنة علمية أو مقالات إعجاز في مصادر آفاق حتى الآن؛ التفسير متاح دائمًا."}
          </p>
          <div className="ayah-actions">
            <a className="btn-primary" href={link.verse(surah.number, verse.ayah_number)}>التفسير والإعجاز العلمي</a>
            <a className="btn-ai" href={link.ai(surah.number, verse.ayah_number)}>✦ الذكاء الاصطناعي في الإعجاز العلمي</a>
          </div>
        </aside>
      )}
    </div>
  );
}

function Legend() {
  return (
    <p className="map-legend">
      <span><span className="mark mark-curated" /> مقارنة علمية موثّقة في آفاق</span>
      <span><span className="mark mark-ijaz" /> مقالات في الإعجاز العلمي من مصدر ثانوي</span>
      <span className="note">(خط أخضر مزدوج: الاثنان معًا)</span>
    </p>
  );
}
