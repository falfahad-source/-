"use client";

import { useState } from "react";
import { ar, Layer, toPlainText } from "./common";
import type { Answer, Tafsir } from "./types";

// Longer entries show their first lines, with «اقرأ المزيد» for the rest.
const LONG = 320;

export default function TafsirTimeline({ a }: { a: Answer }) {
  // التفسير الميسر, short and covering every ayah, comes first as the summary; the detailed
  // books follow in order of their authors' deaths.
  const brief = a.verified_tafsir.find((t) => t.source.includes("الميسر"));
  const items = a.verified_tafsir.filter((t) => t !== brief);
  const rows: React.ReactNode[] = [];
  let lastEra = "";
  items.forEach((t, i) => {
    if (t.era !== lastEra) {
      rows.push(<li key={`era-${t.era}`} className="era-row" aria-hidden="true">{t.era}</li>);
      lastEra = t.era;
    }
    rows.push(
      <li key={`${t.source}-${i}`}>
        <div className="when">{t.year ? <>{ar(t.year)}هـ<small>{t.century_label}</small></> : <small>{t.century_label}</small>}</div>
        <Entry t={t} />
      </li>,
    );
  });
  return (
    <Layer id="tafsir" step="٢" title="التفسير عبر العصور" trust="TAFSIR_VERIFIED"
      lead="ماذا قال المفسرون، بنصوصهم ومصادرهم، مرتّبين بحسب وفاة المؤلف. آفاق لا يختصر أقوالهم ولا يُنشئ تفسيرًا جديدًا.">
      {a.verified_tafsir.length === 0 && <p className="empty">لا يوجد تفسير موثق مستوعب لهذه الآية بعد.</p>}
      {brief && (
        <div className="tafsir-brief">
          <div className="tafsir-head"><strong>المعنى الإجمالي</strong><span className="note">{brief.scholar ? `${brief.scholar} — ` : ""}{brief.source}</span></div>
          <div className="read">{toPlainText(brief.text)}</div>
        </div>
      )}
      {items.length > 0 && (
        <>
          {brief && <h3 className="subhead">التفاسير المفصّلة ({ar(items.length)})</h3>}
          <ol className="timeline">{rows}</ol>
        </>
      )}
    </Layer>
  );
}

function Entry({ t }: { t: Tafsir }) {
  const text = toPlainText(t.text);
  const long = text.length > LONG;
  const [open, setOpen] = useState(false);
  return (
    <div className="tafsir-entry">
      <div className="tafsir-head">
        <strong>{t.scholar}</strong>
        <span>{t.source}</span>
        {t.page && <span className="note">ص {ar(t.page)}</span>}
      </div>
      <div className={`read${long && !open ? " clamp" : ""}`}>{text}</div>
      {long && (
        <button type="button" className="link-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "عرض أقل" : "اقرأ المزيد"}
        </button>
      )}
    </div>
  );
}
