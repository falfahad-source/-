"use client";

import { useState } from "react";
import { LayerHead, toPlainText } from "./common";
import type { Answer } from "./types";

export default function LinguisticLayer({ a, highlight }: { a: Answer; highlight: Set<number> }) {
  const { words, meanings, e3rab, attribution } = a.linguistic;
  const [sel, setSel] = useState<number | null>(null);
  const w = words.find((x) => x.number === sel);
  const byBook = meanings.reduce<Record<string, typeof meanings>>((acc, m) => {
    (acc[m.book] ||= []).push(m);
    return acc;
  }, {});

  return (
    <section className="card" id="language" aria-labelledby="language-h">
      <LayerHead step="١" title="التحليل اللغوي" trust="TAFSIR_VERIFIED">
        صرف كل كلمة، ومعاني الغريب كما شرحها أهل اللغة، وإعراب الآية من كتب الإعراب.
      </LayerHead>

      {words.length === 0 ? <p className="empty">لا يتوفر تحليل صرفي لهذه الآية بعد.</p> : (
        <>
          <div className="words" role="group" aria-label="كلمات الآية">
            {words.map((x) => (
              <button key={x.number} type="button" aria-pressed={x.number === sel}
                className={`word${highlight.has(x.number) ? " in-phrase" : ""}`}
                onClick={() => setSel(x.number === sel ? null : x.number)}>{x.text}</button>
            ))}
          </div>
          {w ? (
            <div className="word-detail" aria-live="polite">
              <dl className="kv">
                <dt>الكلمة</dt><dd>{w.text} <span className="note">(رقم {w.number})</span></dd>
                {w.root && <><dt>الجذر</dt><dd>{w.root}</dd></>}
                {w.lemma && <><dt>الأصل</dt><dd>{w.lemma}</dd></>}
                {w.pos && <><dt>النوع</dt><dd>{w.pos}</dd></>}
                {w.description && <><dt>الوصف</dt><dd>{w.description}</dd></>}
                {w.translation_en && <><dt>English</dt><dd dir="ltr" style={{ textAlign: "right" }}>{w.translation_en}</dd></>}
              </dl>
            </div>
          ) : <p className="note">اضغط على كلمة لعرض تحليلها الصرفي.</p>}
          {attribution && <p className="note">{attribution}</p>}
        </>
      )}

      <h3 className="subhead">معاني الغريب</h3>
      {meanings.length === 0 ? <p className="empty">لا توجد معانٍ غريبة مشروحة لهذه الآية في كتب الغريب المستوعبة.</p> : (
        Object.entries(byBook).map(([book, ms]) => (
          <div key={book} style={{ marginBottom: 8 }}>
            <div className="note">{book} — {ms[0].author}</div>
            <ul className="meaning-list">
              {ms.map((m, i) => <li key={i}><b>{m.word}</b>: {m.meaning}</li>)}
            </ul>
          </div>
        ))
      )}

      <h3 className="subhead">الإعراب</h3>
      {e3rab.length === 0 ? <p className="empty">لا يوجد إعراب مستوعب لهذه الآية.</p> : e3rab.map((e, i) => (
        <details className="fold" key={e.book} open={i === 0}>
          <summary>
            <strong>{e.book}</strong><span>{e.author}{e.year ? ` (ت ${e.year}هـ)` : ""}</span>
            {e.is_excerpt === false && <span className="pill">نص الصفحة كاملًا — قد يشمل آيات مجاورة</span>}
          </summary>
          <div className="read">{toPlainText(e.text)}</div>
        </details>
      ))}
    </section>
  );
}
