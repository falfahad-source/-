import { ayahCount, LayerHead, ReviewPill, SurahName, TrustBadge } from "./common";
import type { Answer, OpenVerse } from "./types";

export default function ScienceLayer({ a, open }: { a: Answer; open: OpenVerse }) {
  const science = a.scientific_knowledge;
  const links = a.possible_connections;
  return (
    <section className="card" id="science">
      <LayerHead step="٤" title="المعرفة العلمية الحديثة">
        معطيات علمية للمقارنة والاستكشاف، دون تحويل المقارنة إلى تفسير قطعي للآية. كل معلومة تحمل مصدرها وفئة ثقتها.
      </LayerHead>
      {science.length === 0 ? (
        <p className="empty">
          لم تُعدّ مقارنة علمية موثقة لهذه الآية بعد.
          {a.related_comparisons.length > 0 && " لكن توجد مقارنات في آيات تشترك معها في الموضوع (أدناه)."}
        </p>
      ) : (
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
                <ReviewPill status={c.review_status} by={c.reviewed_by} at={c.reviewed_at} />
              </div>
            ))}
          </div>
        </>
      )}
      {a.related_comparisons.length > 0 && (
        <>
          <h3 className="subhead">مقارنات علمية في آيات تشترك معها في الموضوع</h3>
          <p className="lead">آيات أُعدّت لها مقارنات علمية موثقة المصادر، وتشترك مع هذه الآية في موضوع قرآني.</p>
          <div className="grid2">
            {a.related_comparisons.map((r) => (
              <button type="button" key={`${r.surah_number}:${r.ayah_number}`} className="hit" onClick={() => open(r.surah_number, r.ayah_number)}>
                <span className="ref">سورة <SurahName name={r.surah_name} /> — <b>الآية {r.ayah_number}</b></span>
                <span>{r.concepts.join("، ")}</span>
                <span className="note">الموضوع المشترك: {r.shared_topics.join("، ")}</span>
              </button>
            ))}
          </div>
        </>
      )}

      <h3 className="subhead">قراءات إعجازية من مصادر ثانوية</h3>
      {a.ijaz.total === 0 ? <p className="empty">لا توجد مقالات إعجاز مفهرسة تتناول هذه الآية.</p> : (
        <>
          <div className="layer-head" style={{ margin: 0 }}><TrustBadge trust="POSSIBLE_CONNECTION" /></div>
          <p className="lead">{a.ijaz.label}</p>
          <ul className="ijaz">
            {a.ijaz.articles.map((x) => (
              <li key={x.url}>
                <a href={x.url} target="_blank" rel="noopener noreferrer"><strong>{x.title}</strong></a>
                {x.excerpt && <p className="note" style={{ margin: "2px 0" }}>{x.excerpt}</p>}
                <span className="note">
                  {x.source}{x.published ? ` — ${x.published}` : ""}{x.categories ? ` — ${x.categories}` : ""}
                  {" — "}{x.match_method === "citation" ? "يذكر الآية بالإحالة" : "يقتبس نص الآية"}
                  {!x.focused && ` ضمن مقال يذكر ${ayahCount(x.verses_in_article)}`}
                </span>
              </li>
            ))}
          </ul>
          {a.ijaz.total > a.ijaz.articles.length && <p className="note">و{a.ijaz.total - a.ijaz.articles.length} مقالًا آخر.</p>}
        </>
      )}
    </section>
  );
}
