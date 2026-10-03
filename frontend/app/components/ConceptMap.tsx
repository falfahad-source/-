"use client";

import { useMemo, useState } from "react";
import { LayerHead, ReviewPill, SurahName, TrustBadge } from "./common";
import type { Answer, GraphNode, OpenVerse } from "./types";

type Placed = GraphNode & { x: number; y: number; r: number };

const RADIUS = { verse: 54, phrase: 48, concept: 46, topic: 40 } as const;

// Radial layout: the verse in the centre, its key phrases and Quranic topics on the
// first ring, each scientific concept on the outer ring beside the phrase it is compared with.
function layout(a: Answer) {
  const { nodes, edges } = a.graph;
  const verse = nodes.find((n) => n.type === "verse")!;
  const ring1 = nodes.filter((n) => n.type === "phrase" || n.type === "topic");
  const r1 = Math.max(175, (ring1.length * 104) / (2 * Math.PI));
  const r2 = r1 + 118;
  const size = 2 * (ring1.some((n) => n.type === "phrase") ? r2 + RADIUS.concept : r1 + RADIUS.phrase) + 24;
  const c = size / 2;
  const placed = new Map<string, Placed>();
  placed.set(verse.id, { ...verse, x: c, y: c, r: RADIUS.verse });
  ring1.forEach((n, i) => {
    const ang = -Math.PI / 2 + (2 * Math.PI * i) / ring1.length;
    placed.set(n.id, { ...n, x: c + r1 * Math.cos(ang), y: c + r1 * Math.sin(ang), r: RADIUS[n.type] });
  });
  const step = Math.min(0.36, (Math.PI * 2) / Math.max(ring1.length, 1) / 2.2);
  for (const p of ring1.filter((n) => n.type === "phrase")) {
    const kids = edges.filter((e) => e.from === p.id && e.type === "possible_connection" && !placed.has(e.to));
    const base = Math.atan2(placed.get(p.id)!.y - c, placed.get(p.id)!.x - c);
    kids.forEach((e, k) => {
      const node = nodes.find((n) => n.id === e.to)!;
      const ang = base + (k - (kids.length - 1) / 2) * step;
      placed.set(node.id, { ...node, x: c + r2 * Math.cos(ang), y: c + r2 * Math.sin(ang), r: RADIUS.concept });
    });
  }
  // fit the drawing to the nodes actually placed, so sparse maps leave no empty band
  const pad = 14;
  const all = [...placed.values()];
  const minX = Math.min(...all.map((n) => n.x - n.r)) - pad, maxX = Math.max(...all.map((n) => n.x + n.r)) + pad;
  const minY = Math.min(...all.map((n) => n.y - n.r)) - pad, maxY = Math.max(...all.map((n) => n.y + n.r)) + pad;
  const viewBox = `${minX} ${minY} ${maxX - minX} ${maxY - minY}`;
  return { viewBox, placed, edges: edges.filter((e) => placed.has(e.from) && placed.has(e.to)) };
}

function lines(label: string): string[] {
  const w = label.split(" ");
  if (label.length <= 9 || w.length < 2) return [label];
  const mid = Math.ceil(w.length / 2);
  return [w.slice(0, mid).join(" "), w.slice(mid).join(" ")];
}

export default function ConceptMap({ a, open, onPhrase }: { a: Answer; open: OpenVerse; onPhrase: (k: string | null) => void }) {
  const { viewBox, placed, edges } = useMemo(() => layout(a), [a]);
  const [sel, setSel] = useState<string>(() => a.graph.nodes.find((n) => n.type === "phrase")?.id ?? a.graph.nodes[0].id);
  const node = placed.get(sel);

  function pick(id: string) {
    setSel(id);
    onPhrase(id.startsWith("phrase:") ? id.slice(7) : null);
  }

  return (
    <section className="card" id="concepts">
      <LayerHead step="٣" title="المفاهيم والظواهر ذات الصلة" trust="TAFSIR_VERIFIED">
        خريطة تربط ألفاظ الآية بموضوعاتها القرآنية وبالمفاهيم العلمية التي يمكن مقارنتها بها. اضغط على أي عقدة لعرض تفاصيلها ومصادرها.
      </LayerHead>
      <div className="map-wrap">
        <svg className="map" viewBox={viewBox} role="group" aria-label="خريطة المفاهيم">
          {edges.map((e) => {
            const f = placed.get(e.from)!, t = placed.get(e.to)!;
            return <line key={`${e.from}-${e.to}`} className={`edge ${e.type}`} x1={f.x} y1={f.y} x2={t.x} y2={t.y} />;
          })}
          {[...placed.values()].map((n) => {
            const ls = lines(n.label);
            const color = `var(--t-${({ QURANIC_TEXT: "quran", TAFSIR_VERIFIED: "tafsir", SCIENTIFIC_FACT: "science",
              POSSIBLE_CONNECTION: "connection", UNVERIFIED_CLAIM: "unverified" } as const)[n.trust_category]})`;
            const enLine = n.type === "concept" && n.label_en && n.label_en.length <= 18 ? n.label_en : null;
            return (
              <g key={n.id} className={`node ${n.type}`} role="button" tabIndex={0} aria-pressed={n.id === sel}
                aria-label={n.label} onClick={() => pick(n.id)}
                onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(n.id); } }}>
                <circle cx={n.x} cy={n.y} r={n.r} style={{ stroke: n.type === "verse" ? undefined : color }} />
                {ls.map((l, i) => (
                  <text key={i} x={n.x} y={n.y + (i - (ls.length - 1) / 2) * 15 - (enLine ? 6 : 0)}
                    style={n.type === "verse" ? undefined : { fontFamily: n.type === "concept" ? undefined : "var(--f-quran)" }}>{l}</text>
                ))}
                {enLine && <text className="en" x={n.x} y={n.y + (ls.length * 15) / 2 + 4}>{enLine}</text>}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="map-legend">
        <span><i />لفظ أو موضوع في الآية</span>
        <span><i className="dash" />مقارنة / ارتباط محتمل</span>
        <span>لون إطار العقدة = فئة الثقة</span>
      </div>
      {node && <NodeDetail a={a} node={node} open={open} />}
    </section>
  );
}

function NodeDetail({ a, node, open }: { a: Answer; node: GraphNode; open: OpenVerse }) {
  if (node.type === "phrase") {
    const p = a.concepts.find((x) => `phrase:${x.key}` === node.id);
    if (!p) return null;
    return (
      <div className="node-detail" aria-live="polite">
        <div className="layer-head"><h3 style={{ margin: 0, fontFamily: "var(--f-quran)", fontSize: "1.4rem" }}>{p.text}</h3><TrustBadge trust="QURANIC_TEXT" /></div>
        <p className="note">الكلمات {p.words[0]}–{p.words[1]} من الآية</p>
        {p.meanings.length > 0 ? (
          <>
            <div className="layer-head"><strong>معناها عند أهل الغريب</strong><TrustBadge trust="TAFSIR_VERIFIED" /></div>
            <ul className="meaning-list">{p.meanings.map((m, i) => <li key={i}>{m.meaning} <span className="note">— {m.book}</span></li>)}</ul>
          </>
        ) : <p className="empty">لا يوجد شرح لهذا اللفظ في كتب الغريب المستوعبة.</p>}
        {p.connections.length > 0 && (
          <div className="grid2" style={{ marginTop: 10 }}>
            {p.connections.map((c) => (
              <div className="link" key={c.concept}>
                <div className="layer-head" style={{ margin: 0 }}><h3>{c.concept_name_ar}</h3><TrustBadge trust="POSSIBLE_CONNECTION" /></div>
                <p>{c.explanation}</p>
                <ReviewPill status={c.review_status} by={c.reviewed_by} at={c.reviewed_at} />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  if (node.type === "concept") {
    const s = a.scientific_knowledge.find((x) => `concept:${x.concept}` === node.id);
    const from = a.possible_connections.filter((c) => `concept:${c.concept}` === node.id);
    return (
      <div className="node-detail" aria-live="polite">
        <div className="layer-head"><h3 style={{ margin: 0 }}>{node.label}</h3>{node.label_en && <span className="note" dir="ltr">{node.label_en}</span>}</div>
        {s && s.claims.length > 0 ? s.claims.map((c, i) => (
          <div className={`claim ${c.trust_category}`} key={i} style={{ marginBottom: 6 }}>
            <TrustBadge trust={c.trust_category} />
            <p>{c.claim}</p>
            <span className="note">المصدر: {c.source}{c.provenance_note ? ` — ${c.provenance_note}` : ""}</span>
          </div>
        )) : <p className="empty">لا يوجد مصدر علمي مرتبط بهذا المفهوم بعد.</p>}
        {from.map((c) => <p key={c.phrase} className="note">يُقارَن بلفظ «{c.phrase_label}»: {c.explanation}</p>)}
      </div>
    );
  }
  if (node.type === "topic") {
    const t = a.topics.find((x) => `topic:${x.id}` === node.id);
    if (!t) return null;
    return (
      <div className="node-detail" aria-live="polite">
        <div className="layer-head"><h3 style={{ margin: 0 }}>موضوع: {t.name}</h3><TrustBadge trust="TAFSIR_VERIFIED" /></div>
        {t.parent && <p className="note">ضمن موضوع: {t.parent}</p>}
        <p>{t.related_total === 0 ? "لا توجد آيات أخرى في هذا الموضوع." : `آيات أخرى في هذا الموضوع (${t.related_total}):`}</p>
        <div className="topic-list"><div className="verses">
          {t.related.map((r) => (
            <button key={`${r.surah_number}:${r.ayah_number}`} type="button" className="btn-ghost" onClick={() => open(r.surah_number, r.ayah_number)}>
              <SurahName name={r.surah_name} /> {r.ayah_number}
            </button>
          ))}
          {t.related_total > t.related.length && <span className="note">و{t.related_total - t.related.length} غيرها</span>}
        </div></div>
        <p className="note">{t.source}</p>
      </div>
    );
  }
  return (
    <div className="node-detail" aria-live="polite">
      <p style={{ margin: 0 }}>سورة <SurahName name={a.surah_name} />، الآية {a.ayah_number}. اختر لفظًا أو موضوعًا من الخريطة.</p>
    </div>
  );
}
