import type { ReviewStatus, Trust } from "./types";

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
  return n % 100 >= 3 && n % 100 <= 10 ? `${n} آيات` : `${n} آية`;
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

// Review state of a curated comparison (see /review).
export function ReviewPill({ status, by, at }: { status: ReviewStatus; by?: string | null; at?: string | null }) {
  if (status === "approved") return <span className="pill pill-ok">اعتمدها الباحث{by ? `: ${by}` : ""}{at ? ` — ${at}` : ""}</span>;
  if (status === "changes_requested") return <span className="pill">قيد المراجعة — طُلب تعديلها</span>;
  return <span className="pill">مسودة — بحاجة لمراجعة الباحث</span>;
}
