import { LayerHead, TrustBadge } from "./common";
import type { Answer } from "./types";

export default function ScienceLayer({ a }: { a: Answer }) {
  const science = a.scientific_knowledge;
  const links = a.possible_connections;
  return (
    <section className="card" id="science">
      <LayerHead step="٤" title="المعرفة العلمية الحديثة">
        معطيات علمية للمقارنة والاستكشاف، دون تحويل المقارنة إلى تفسير قطعي للآية. كل معلومة تحمل مصدرها وفئة ثقتها.
      </LayerHead>
      {science.length === 0 ? <p className="empty">لم تُربط هذه الآية بمعرفة علمية موثقة بعد.</p> : (
        <div className="grid2">
          {science.map((s) => (
            <article key={s.concept} className={`claim ${s.claims[0]?.trust_category ?? "UNVERIFIED_CLAIM"}`}>
              <div className="layer-head" style={{ margin: 0 }}>
                <h3>{s.name_ar}</h3>
                {s.name_en && <span className="note" dir="ltr">{s.name_en}</span>}
              </div>
              {s.claims.length === 0 ? (
                <>
                  <TrustBadge trust="UNVERIFIED_CLAIM" />
                  <p className="empty">لا يوجد مصدر علمي مرتبط بهذا المفهوم بعد.</p>
                </>
              ) : s.claims.map((c, i) => (
                <div key={i} style={{ display: "grid", gap: 4 }}>
                  <TrustBadge trust={c.trust_category} />
                  <p>{c.claim}</p>
                  {c.quote && <blockquote dir="ltr" style={{ margin: 0, textAlign: "right" }} className="note">“{c.quote}”</blockquote>}
                  <span className="note">
                    المصدر: {c.url ? <a href={c.url} target="_blank" rel="noopener noreferrer">{c.source}</a> : c.source}
                    {c.verified_at && ` — طوبق في ${c.verified_at}`}
                  </span>
                  {c.provenance_note && <span className="note">{c.provenance_note}</span>}
                </div>
              ))}
            </article>
          ))}
        </div>
      )}
      {links.length > 0 && (
        <>
          <h3 className="subhead">المقارنات المقترحة</h3>
          <p className="lead">آفاق لا يقول «هذا تفسير الآية»، بل: هناك ظاهرة علمية يمكن مقارنتها، بينما التفسير الموثق هو ما في الطبقة الثانية.</p>
          <div className="grid2">
            {links.map((c, i) => (
              <div className="link" key={i}>
                <div className="layer-head" style={{ margin: 0 }}>
                  <h3>{c.phrase_label && <><span style={{ fontFamily: "var(--f-quran)" }}>{c.phrase_label}</span> ↔ </>}{c.concept_name_ar ?? c.explanation}</h3>
                </div>
                <TrustBadge trust="POSSIBLE_CONNECTION" />
                <p>{c.explanation}</p>
                <span className="pill">{c.review_status === "draft" ? "مسودة — بحاجة لمراجعة الباحث" : "روجعت"}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
