"use client";

import { useEffect, useState } from "react";
import HistoryRow from "./components/HistoryRow";
import SiteNav from "./components/SiteNav";
import { type HistoryEntry, readHistory } from "./components/history";
import { link } from "./components/links";

const CARDS = [
  { href: () => link.search(), icon: "⌕", title: "بحث جديد",
    text: "ابحث بجزء من آية أو بموضوع مثل «مدة الرضاعة الطبيعية»، ثم استكشف رحلة الآية: اللغة، والتفسير عبر العصور، والمعرفة العلمية." },
  { href: link.history, icon: "↺", title: "سجل البحث",
    text: "عمليات بحثك السابقة والآيات التي فتحتها، مرتبة زمنيًا، لتعود إلى أيٍّ منها بضغطة." },
  { href: () => link.quran(), icon: "۞", title: "القرآن الكريم",
    text: "تصفّح المصحف سورةً سورة، واضغط أي آية لتقرأ تفسيرها وما يتصل بها من الإعجاز العلمي إن وُجد." },
  { href: () => link.ai(), icon: "✦", title: "الذكاء الاصطناعي في الإعجاز العلمي",
    text: "باحث آلي ناقد يدرس الآية: يفهمها من التفاسير، ويقارنها بالعلم الحديث، ويحاول دحض كل ربط قبل أن يحكم." },
];

export default function Home() {
  const [recent, setRecent] = useState<HistoryEntry[]>([]);
  useEffect(() => { setRecent(readHistory().slice(0, 4)); }, []);

  return (
    <div className="shell">
      <SiteNav current="home" />
      <header className="hero">
        <h1>آفاق <span>| AFAQ</span></h1>
        <p>حين يلتقي التفسير بالمعرفة — استكشاف الآية عبر التفسير الموثق والمعرفة العلمية، مع تصنيف واضح لكل معلومة.</p>
      </header>

      <div className="home-grid">
        {CARDS.map((c) => (
          <a key={c.title} className="home-card" href={c.href()}>
            <span className="home-icon" aria-hidden="true">{c.icon}</span>
            <strong>{c.title}</strong>
            <span>{c.text}</span>
          </a>
        ))}
      </div>

      {recent.length > 0 && (
        <section className="card home-recent">
          <div className="layer-head"><h2>آخر ما بحثت عنه</h2><a className="note" href={link.history()}>السجل كاملًا</a></div>
          <ul className="history-list">{recent.map((e) => <HistoryRow key={e.at} e={e} />)}</ul>
        </section>
      )}

      <footer className="foot">
        نص المصحف: مجمع الملك فهد لطباعة المصحف الشريف (رواية حفص، الإصدار 3.0).
        <br />
        آفاق لا يطلب من الذكاء الاصطناعي تفسير القرآن، بل يستعمله للتنقل في المعرفة الموثقة حوله.
      </footer>
    </div>
  );
}
