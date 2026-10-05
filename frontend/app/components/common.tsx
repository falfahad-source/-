import { createContext, useContext } from "react";
import type { ReviewStatus, Trust } from "./types";

/** A number in Arabic-Indic digits (٢٤), as everywhere in the interface. */
export function ar(n: number | string): string {
  return String(n).replace(/\d/g, (d) => "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"[+d]);
}

const TRUST_LABEL: Record<Trust, string> = {
  QURANIC_TEXT: "نص قرآني",
  TAFSIR_VERIFIED: "تفسير موثق",
  SCIENTIFIC_FACT: "حقيقة علمية مثبتة",
  POSSIBLE_CONNECTION: "مقارنة / ارتباط محتمل",
  UNVERIFIED_CLAIM: "ادعاء غير موثق",
};

export function TrustBadge({ trust, title }: { trust: Trust; title?: string }) {
  return <span className={`trust trust-${trust}`} title={title}>{TRUST_LABEL[trust]}</span>;
}

// Surah names come from KFGQPC in Uthmani script (e.g. the ۡ sukun in النَّمۡلِ),
// which the UI font lacks, so they are rendered in the Hafs font like the verses.
export function SurahName({ name }: { name: string }) {
  return <span className="sname">{name}</span>;
}

// Tafsir and i'rab are stored verbatim from Quranpedia, which includes markup
// (<span class="book-ayah">, <br />). Show it as plain text: parsing into a
// detached document and reading textContent never executes or injects anything.
export function toPlainText(html: string): string {
  const withBreaks = html.replace(/<br\s*\/?>/gi, "\n");
  return new DOMParser().parseFromString(withBreaks, "text/html").body.textContent ?? "";
}

// Arabic number agreement: 1 آية واحدة، 2 آيتان، 3–10 آيات، 11+ آية.
export function ayahCount(n: number): string {
  if (n === 1) return "آية واحدة";
  if (n === 2) return "آيتان";
  return n % 100 >= 3 && n % 100 <= 10 ? `${ar(n)} آيات` : `${ar(n)} آية`;
}

export function LayerHead({ step, title, trust, children }: {
  step?: string; title: string; trust?: Trust; children?: React.ReactNode;
}) {
  return (
    <>
      <div className="layer-head">
        <h2>{step && <span className="step">{step} </span>}{title}</h2>
        {trust && <TrustBadge trust={trust} />}
      </div>
      {children && <p className="lead">{children}</p>}
    </>
  );
}

/** Which layers of the verse journey are folded (see Layer). Without a provider every layer is open. */
export const FoldContext = createContext<{ closed: Set<string>; toggle: (id: string) => void } | null>(null);

/** One layer of the verse journey: its heading and lead are always shown; the content folds
 * away under the heading's button, so the reader can keep the page to the layers they read. */
export function Layer({ id, step, title, trust, lead, children }: {
  id: string; step?: string; title: string; trust?: Trust; lead?: React.ReactNode; children: React.ReactNode;
}) {
  const fold = useContext(FoldContext);
  const closed = fold?.closed.has(id) ?? false;
  return (
    <section className={`card layer${closed ? " folded" : ""}`} id={id}>
      <div className="layer-head">
        <h2>{step && <span className="step">{step} </span>}{title}</h2>
        {trust && <TrustBadge trust={trust} />}
        {fold && (
          <button type="button" className="btn-ghost fold-toggle" aria-expanded={!closed} aria-controls={`${id}-body`}
            onClick={() => fold.toggle(id)}>{closed ? "عرض" : "طيّ"}</button>
        )}
      </div>
      {lead && <p className="lead">{lead}</p>}
      <div id={`${id}-body`} hidden={closed}>{children}</div>
    </section>
  );
}

// Review state of a curated comparison (see /review).
export function ReviewPill({ status, by, at }: { status: ReviewStatus; by?: string | null; at?: string | null }) {
  if (status === "approved") return <span className="pill pill-ok">اعتمدها الباحث{by ? `: ${by}` : ""}{at ? ` — ${at}` : ""}</span>;
  if (status === "changes_requested") return <span className="pill">قيد المراجعة — طُلب تعديلها</span>;
  return <span className="pill">مسودة — بحاجة لمراجعة الباحث</span>;
}
