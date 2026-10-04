import { ayahCount } from "./common";
import type { HistoryEntry } from "./history";
import { link } from "./links";

const KIND: Record<HistoryEntry["kind"], string> = { search: "بحث", verse: "آية", ai: "ذكاء اصطناعي" };

export default function HistoryRow({ e, onRemove }: { e: HistoryEntry; onRemove?: () => void }) {
  const href = e.kind === "search" ? link.search(e.query) : e.kind === "verse" ? link.verse(e.s, e.a) : link.ai(e.s, e.a);
  const title = e.kind === "search" ? <>«{e.query}»</> : <>سورة <span className="sname">{e.surah}</span> — الآية {e.a}</>;
  const detail = e.kind === "search" ? (e.total ? ayahCount(e.total) : "لا نتائج") : e.kind === "ai" && e.mode === "mock" ? "تقرير تجريبي" : "";
  return (
    <li>
      <span className={`kind kind-${e.kind}`}>{KIND[e.kind]}</span>
      <a href={href}>{title}</a>
      {detail && <span className="note">{detail}</span>}
      <time className="note" dateTime={e.at}>{new Date(e.at).toLocaleString("ar", { dateStyle: "medium", timeStyle: "short" })}</time>
      {onRemove && <button type="button" className="btn-ghost" onClick={onRemove} aria-label="حذف من السجل">حذف</button>}
    </li>
  );
}
