"use client";

import { useEffect, useMemo, useState } from "react";
import HistoryRow from "../components/HistoryRow";
import SiteNav from "../components/SiteNav";
import { clearHistory, type HistoryEntry, readHistory, removeHistory } from "../components/history";
import { link } from "../components/links";

type Filter = "all" | HistoryEntry["kind"];
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "الكل" }, { key: "search", label: "عمليات البحث" },
  { key: "verse", label: "الآيات" }, { key: "ai", label: "الذكاء الاصطناعي" },
];

const day = (iso: string) => new Date(iso).toLocaleDateString("ar", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryEntry[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  useEffect(() => { setItems(readHistory()); }, []);

  const groups = useMemo(() => {
    const out: { day: string; items: HistoryEntry[] }[] = [];
    for (const e of items ?? []) {
      if (filter !== "all" && e.kind !== filter) continue;
      const d = day(e.at);
      if (out[out.length - 1]?.day !== d) out.push({ day: d, items: [] });
      out[out.length - 1].items.push(e);
    }
    return out;
  }, [items, filter]);

  function clear() {
    if (!confirm("حذف سجل البحث كاملًا من هذا المتصفح؟")) return;
    clearHistory();
    setItems([]);
  }

  return (
    <div className="shell">
      <SiteNav current="history" />
      <header className="masthead">
        <h1>سجل البحث</h1>
        <p>عمليات بحثك والآيات التي فتحتها وتقارير الذكاء الاصطناعي، الأحدث أولًا. يُحفظ السجل في هذا المتصفح فقط.</p>
      </header>

      {items && items.length > 0 && (
        <div className="review-top">
          <div className="tabs" role="group" aria-label="تصفية السجل">
            {FILTERS.map((f) => (
              <button key={f.key} type="button" className="btn-ghost" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>{f.label}</button>
            ))}
          </div>
          <button type="button" className="btn-bad" onClick={clear}>حذف السجل</button>
        </div>
      )}

      {items && items.length === 0 && (
        <section className="card">
          <p className="empty" style={{ margin: 0 }}>لا يوجد سجل بعد. ابدأ <a href={link.search()}>بحثًا جديدًا</a> أو تصفّح <a href={link.quran()}>القرآن الكريم</a>.</p>
        </section>
      )}
      {items && items.length > 0 && groups.length === 0 && <p className="empty">لا توجد عناصر من هذا النوع.</p>}

      {groups.map((g) => (
        <section key={g.day} className="history-day">
          <h2 className="subhead">{g.day}</h2>
          <ul className="history-list card">
            {g.items.map((e) => (
              <HistoryRow key={e.at} e={e} onRemove={() => { removeHistory(e.at); setItems(readHistory()); }} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
