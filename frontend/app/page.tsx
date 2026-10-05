"use client";

import { useEffect, useState } from "react";
import Footer from "./components/Footer";
import HistoryRow from "./components/HistoryRow";
import Icon from "./components/Icon";
import Logo from "./components/Logo";
import SiteNav from "./components/SiteNav";
import { type HistoryEntry, readHistory } from "./components/history";
import { link } from "./components/links";
import { ar, SurahName } from "./components/common";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const CARDS = [
  { href: () => link.search(), icon: "search" as const, title: "بحث جديد", short: "بحث جديد",
    text: "ابحث بجزء من آية، أو بموضوع يقترح له الذكاء الاصطناعي الآيات المتصلة به، ثم استكشف رحلة الآية: اللغة، والتفسير عبر العصور، والمعرفة العلمية." },
  { href: link.history, icon: "history" as const, title: "سجل البحث", short: "سجل البحث",
    text: "عمليات بحثك السابقة والآيات التي فتحتها، مرتبة زمنيًا، لتعود إلى أيٍّ منها بضغطة." },
  { href: () => link.quran(), icon: "quran" as const, title: "القرآن الكريم", short: "القرآن الكريم",
    text: "تصفّح المصحف سورةً سورة، واضغط أي آية لتقرأ تفسيرها وما يتصل بها من الإعجاز العلمي إن وُجد." },
  { href: () => link.ai(), icon: "ai" as const, title: "الذكاء الاصطناعي في الإعجاز العلمي", short: "الإعجاز بالذكاء الاصطناعي",
    text: "باحث آلي ناقد يدرس الآية: يفهمها من التفاسير، ويقارنها بالعلم الحديث، ويحاول دحض كل ربط قبل أن يحكم." },
];

// topics and verse fragments to start from, as typed in the search box
type Featured = { surah_number: number; ayah_number: number; surah_name: string; text?: string; concepts: string[] };

// «آية اليوم»: one of the verses with a curated scientific comparison, the same for everyone on
// a given day. Short verses only, so the card stays a card.
function todays(verses: Featured[]): Featured | null {
  const fit = verses.filter((v) => v.text && v.text.length <= 260);
  if (!fit.length) return null;
  const now = new Date();
  const day = Math.floor(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / 86400000);
  return fit[day % fit.length];
}

const EXAMPLES = ["مدة الرضاعة الطبيعية", "ذكاء الإنسان", "الجبال", "البحار", "ظلمات بعضها فوق بعض", "خلق الإنسان"];

export default function Home() {
  const [recent, setRecent] = useState<HistoryEntry[]>([]);
  const [q, setQ] = useState("");
  const search = (query: string) => { if (query.trim()) location.href = link.search(query.trim()); };
  const [verse, setVerse] = useState<Featured | null>(null);
  useEffect(() => { setRecent(readHistory().slice(0, 4)); }, []);
  useEffect(() => {
    fetch(`${API_BASE}/explore`).then((r) => (r.ok ? r.json() : { verses: [] })).then((d) => setVerse(todays(d.verses ?? []))).catch(() => {});
  }, []);

  return (
    <div className="shell">
      <SiteNav current="home" />
      <header className="hero">
        {/* the logo's horizon, large and faint, behind the title */}
        <svg className="hero-horizon" viewBox="0 0 600 200" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
          <path d="M120 196a180 180 0 0 1 360 0" />
          <path className="line" d="M0 196h600" />
        </svg>
        <h1><Logo large /></h1>
        <p>حين يلتقي التفسير بالمعرفة — استكشاف الآية عبر التفسير الموثق والمعرفة العلمية، مع تصنيف واضح لكل معلومة.</p>
      </header>

      <form className="searchbar home-search" role="search" onSubmit={(e) => { e.preventDefault(); search(q); }}>
        <input id="home-q" type="search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="ابحث بجزء من آية أو بموضوع" aria-label="البحث بنص الآية أو بالموضوع" />
        <button className="btn-primary" type="submit">بحث</button>
      </form>
      <div className="examples" aria-label="أمثلة للبحث">
        <span className="note">جرّب:</span>
        {EXAMPLES.map((x) => <a key={x} className="chip" href={link.search(x)}>{x}</a>)}
      </div>

      {verse && (
        <section className="daily-verse" aria-labelledby="daily-h">
          <div className="daily-head">
            <h2 id="daily-h">آية اليوم</h2>
            <span className="note">سورة <SurahName name={verse.surah_name} /> — الآية {ar(verse.ayah_number)}</span>
          </div>
          <p className="daily-text">{verse.text}</p>
          {verse.concepts.length > 0 && (
            <p className="daily-concepts note">تتصل بها: {verse.concepts.slice(0, 3).join("، ")}</p>
          )}
          <a className="btn-primary" href={link.verse(verse.surah_number, verse.ayah_number)}>اقرأ التفسير والمعرفة العلمية</a>
        </section>
      )}

      <div className="home-grid">
        {CARDS.map((c) => (
          <a key={c.title} className="home-card" href={c.href()}>
            <span className="home-icon"><Icon name={c.icon} size={24} /></span>
            <strong><span className="title-full">{c.title}</span><span className="title-short">{c.short}</span></strong>
            <span className="home-card-text">{c.text}</span>
          </a>
        ))}
      </div>

      {recent.length > 0 && (
        <section className="card home-recent">
          <div className="layer-head"><h2>آخر ما بحثت عنه</h2><a className="note" href={link.history()}>السجل كاملًا</a></div>
          <ul className="history-list">{recent.map((e) => <HistoryRow key={e.at} e={e} />)}</ul>
        </section>
      )}

      <Footer />
    </div>
  );
}
