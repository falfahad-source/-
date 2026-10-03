import { LayerHead, toPlainText } from "./common";
import type { Answer } from "./types";

export default function TafsirTimeline({ a }: { a: Answer }) {
  const items = a.verified_tafsir;
  const rows: React.ReactNode[] = [];
  let lastEra = "";
  items.forEach((t, i) => {
    if (t.era !== lastEra) {
      rows.push(<li key={`era-${t.era}`} className="era-row" aria-hidden="true">{t.era}</li>);
      lastEra = t.era;
    }
    rows.push(
      <li key={`${t.source}-${i}`}>
        <div className="when">{t.year ? <>{t.year}هـ<small>{t.century_label}</small></> : <small>{t.century_label}</small>}</div>
        <details className="fold" open={i === 0}>
          <summary>
            <strong>{t.scholar}</strong>
            <span>{t.source}</span>
            {t.page && <span className="note">ص {t.page}</span>}
          </summary>
          <div className="read">{toPlainText(t.text)}</div>
        </details>
      </li>,
    );
  });
  return (
    <section className="card" id="tafsir">
      <LayerHead step="٢" title="التفسير عبر العصور" trust="TAFSIR_VERIFIED">
        ماذا قال المفسرون، بنصوصهم ومصادرهم، مرتّبين بحسب وفاة المؤلف. آفاق لا يختصر أقوالهم ولا يُنشئ تفسيرًا جديدًا.
      </LayerHead>
      {items.length === 0 ? <p className="empty">لا يوجد تفسير موثق مستوعب لهذه الآية بعد.</p> : <ol className="timeline">{rows}</ol>}
    </section>
  );
}
