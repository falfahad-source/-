// Static demo: the real AFAQ page, with the API answered from bundled data.
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import AiIjazPage from "../app/ai-ijaz/page";
import HistoryPage from "../app/history/page";
import Home from "../app/page";
import QuranPage from "../app/quran/page";
import SearchPage from "../app/search/page";
import { type Entry, type Kind, loadLexicon, norm, searchTopics, textWords } from "./topicSearch";

// [surah, ayah, surah name, text, imla'i text, page, juz, i'jaz article count (newer exports)]
type V = [number, number, string, string, string, number | null, number | null, number?];
const DATA = JSON.parse(document.getElementById("afaq-data")!.textContent!) as {
  answers: Record<string, unknown>; verses: V[]; explore: unknown;
};

const AI = JSON.parse(document.getElementById("afaq-ai")!.textContent!) as {
  status: Record<string, unknown>; disclaimer: string; report_template: string; topic_note?: string;
};
const AI_TOPIC_NOTE = AI.topic_note ?? "منصة الذكاء الاصطناعي لم تُربط بعد، فالنتائج مؤقتًا من البحث في مصادر آفاق.";
// Curated verses are the ones with a full answer; i'jaz counts come with the verse in newer exports,
// otherwise only the full answers know them.
const curated = (v: V) => `${v[0]}:${v[1]}` in DATA.answers;
const ijaz = (v: V) => v[7] ?? (DATA.answers[`${v[0]}:${v[1]}`] as { ijaz?: { total: number } } | undefined)?.ijaz?.total ?? 0;
const SURAHS: { number: number; name: string; ayah_count: number; curated_ayahs: number; ijaz_ayahs: number }[] = [];
for (const v of DATA.verses) {
  if (SURAHS[SURAHS.length - 1]?.number !== v[0]) SURAHS.push({ number: v[0], name: v[2], ayah_count: 0, curated_ayahs: 0, ijaz_ayahs: 0 });
  const x = SURAHS[SURAHS.length - 1];
  x.ayah_count += 1;
  if (curated(v)) x.curated_ayahs += 1;
  if (ijaz(v)) x.ijaz_ayahs += 1;
}
const KEYS = DATA.verses.map((v) => [norm(v[4]), norm(v[3])]);

// Topic search index, built on the first topic search: the exported entries, then التفسير الميسر
// of every verse (in the curated answers, or in `brief` for the others).
let TOPIC_ENTRIES: Entry[] | null = null;
function topicEntries(): Entry[] {
  if (TOPIC_ENTRIES) return TOPIC_ENTRIES;
  const D = DATA as unknown as {
    topic_index?: [Kind, string, string | null, number[]][];
    topic_lexicon?: { lemmas: string[]; forms: Record<string, number[]> }; topic_synonyms?: string[][];
  };
  loadLexicon(D.topic_lexicon ?? { lemmas: [], forms: {} }, D.topic_synonyms ?? []);
  const entries: Entry[] = (D.topic_index ?? []).map(([kind, label, url, verses]) => ({ kind, label, url, words: textWords(label), verses }));
  const book = LIGHT.brief?.meta?.source as string | undefined;
  if (book) {
    DATA.verses.forEach((v, i) => {
      const key = `${v[0]}:${v[1]}`;
      const full = DATA.answers[key] as { verified_tafsir?: { source: string; text: string }[] } | undefined;
      const text = full ? full.verified_tafsir?.find((t) => t.source === book)?.text : LIGHT.brief?.verses[key]?.[0];
      if (text) entries.push({ kind: "tafsir", label: book, url: null, words: textWords(text), verses: [i] });
    });
  }
  return (TOPIC_ENTRIES = entries);
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

// Lighter answer for verses without a curated map: their text, one short tafsir and their i'jaz
// article links, when the data has them (see backend/app/demo_export.py `_light`).
type Light = {
  brief?: { meta: Record<string, unknown> | null; verses: Record<string, [string, string | null]> };
  ijaz?: { label: string; article_fields: string[]; link_fields: string[]; articles: unknown[][];
    verses: Record<string, [number, [number, ...unknown[]][]]> };
};
const LIGHT = DATA as unknown as Light;
const zip = (keys: string[], vals: unknown[]) => Object.fromEntries(keys.map((k, i) => [k, vals[i]]));

function minimalAnswer(v: V) {
  const key = `${v[0]}:${v[1]}`;
  const brief = LIGHT.brief?.verses[key];
  const tafsir = brief && LIGHT.brief?.meta
    ? [{ ...LIGHT.brief.meta, text: brief[0], page: brief[1], disagreement_group: `surah${v[0]}:ayah${v[1]}` }] : [];
  const links = LIGHT.ijaz?.verses[key];
  const ij = LIGHT.ijaz;
  const articles = links && ij
    ? links[1].map(([i, ...rest]) => ({ ...zip(ij.article_fields, ij.articles[i]), ...zip(ij.link_fields, rest) })) : [];
  const sources = [{ title: "مصحف المدينة النبوية للنشر الحاسوبي — رواية حفص (الإصدار 3.0)", publisher: "مجمع الملك فهد لطباعة المصحف الشريف", url: "https://qurancomplex.gov.sa/quran-hafs/", trust_category: "QURANIC_TEXT" }];
  if (tafsir.length) sources.push({ title: String(LIGHT.brief!.meta!.source), publisher: "Quranpedia.net", url: "https://quranpedia.net", trust_category: "TAFSIR_VERIFIED" });
  if (articles.length) sources.push({ title: String(articles[0].source), publisher: "quran-m.com", url: "https://quran-m.com", trust_category: "POSSIBLE_CONNECTION" });
  return {
    quranic_text: v[3], surah_number: v[0], ayah_number: v[1], surah_name: v[2], page_number: v[5], juz_number: v[6],
    verified_tafsir: tafsir, linguistic: { words: [], meanings: [], e3rab: [], attribution: null },
    concepts: [], scientific_knowledge: [], topics: [], graph: { nodes: [{ id: "v", type: "verse", label: `${v[2]} ${v[1]}`, trust_category: "QURANIC_TEXT" }], edges: [] },
    possible_connections: [], hadith_matches: [],
    ijaz: { total: links ? links[0] : 0, articles, label: ij?.label ?? "" }, related_comparisons: [],
    not_established: [
      tafsir.length
        ? "النسخة التجريبية تعرض لهذه الآية «التفسير الميسر» وحده، والطبقات الكاملة (التفاسير التسعة، التحليل اللغوي، الخريطة، العلم) للآيات النموذجية؛ وهي كلها متاحة لكل الآيات في نسخة الخادم."
        : "النسخة التجريبية تعرض الطبقات الكاملة (التحليل اللغوي، التفسير، الخريطة، العلم) للآيات النموذجية فقط؛ وهي كلها متاحة لكل الآيات في نسخة الخادم.",
      ...(links ? [`تُعرض ${articles.length} من ${links[0]} من القراءات الإعجازية من مصدر ثانوي بروابطها فقط؛ لم يتحقق آفاق من معلوماتها العلمية.`] : []),
    ],
    sources,
    trust_legend: (Object.values(DATA.answers)[0] as { trust_legend: unknown }).trust_legend,
  };
}

const realFetch = window.fetch.bind(window);
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, location.href);
  if (url.origin !== "https://afaq.demo") return realFetch(input, init);
  const verse = /^\/verse\/(\d+)\/(\d+)$/.exec(url.pathname);
  if (verse) {
    const key = `${+verse[1]}:${+verse[2]}`;
    if (DATA.answers[key]) return json(DATA.answers[key]);
    const v = DATA.verses.find((x) => x[0] === +verse[1] && x[1] === +verse[2]);
    return v ? json(minimalAnswer(v)) : json({ detail: "لم يتم العثور على هذه الآية في المصادر المعتمدة المستوعبة حتى الآن." }, 404);
  }
  if (url.pathname === "/search/ai") {
    // no AI platform in the demo: test mode, answered by the source search, as a server in test mode
    try {
      const r = searchTopics(topicEntries(), (i) => { const v = DATA.verses[i]; return [v[0], v[1], v[2], v[3], v[5]]; },
        url.searchParams.get("q") ?? "", +(url.searchParams.get("limit") ?? 50), +(url.searchParams.get("offset") ?? 0));
      return json({ ...r, mode: "mock", note: AI_TOPIC_NOTE, dropped: 0, disclaimer: null });
    } catch (e) { return json({ detail: (e as Error).message }, 422); }
  }
  if (url.pathname === "/search/topics") {
    try {
      return json(searchTopics(topicEntries(), (i) => { const v = DATA.verses[i]; return [v[0], v[1], v[2], v[3], v[5]]; },
        url.searchParams.get("q") ?? "", +(url.searchParams.get("limit") ?? 50), +(url.searchParams.get("offset") ?? 0)));
    } catch (e) { return json({ detail: (e as Error).message }, 422); }
  }
  if (url.pathname === "/explore") return json(DATA.explore);
  if (url.pathname === "/surahs") return json({ surahs: SURAHS });
  const surah = /^\/surah\/(\d+)$/.exec(url.pathname);
  if (surah) {
    const vs = DATA.verses.filter((v) => v[0] === +surah[1]);
    if (!vs.length) return json({ detail: "لم يتم العثور على هذه السورة في المصادر المعتمدة المستوعبة حتى الآن." }, 404);
    return json({ number: vs[0][0], name: vs[0][2], verses: vs.map((v) => ({
      ayah_number: v[1], text: v[3], page_number: v[5], juz_number: v[6], curated: curated(v), ijaz_articles: ijaz(v) })) });
  }
  if (url.pathname === "/search") {
    const q = url.searchParams.get("q") ?? "";
    const needle = norm(q);
    if (needle.replace(/ /g, "").length < 2) return json({ detail: "اكتب حرفين عربيين على الأقل للبحث." }, 422);
    const limit = +(url.searchParams.get("limit") ?? 50), offset = +(url.searchParams.get("offset") ?? 0);
    const hits = DATA.verses.filter((_, i) => KEYS[i][0].includes(needle) || KEYS[i][1].includes(needle));
    return json({ query: q, normalized_query: needle, total: hits.length, offset,
      results: hits.slice(offset, offset + limit).map((v) => ({ surah_number: v[0], ayah_number: v[1], surah_name: v[2], text: v[3], page_number: v[5] })) });
  }
  // «الذكاء الاصطناعي في الإعجاز العلمي»: the same answers as a server in test mode (AFAQ_AI_PROVIDER=mock)
  if (url.pathname === "/ai-research/status") return json(AI.status);
  if (url.pathname === "/ai-research" && init?.method === "POST") {
    const { surah_number: s, ayah_number: a } = JSON.parse(String(init.body));
    if (!(s >= 1 && s <= 114 && a >= 1 && a <= 286)) return json({ detail: "رقم السورة أو الآية خارج النطاق." }, 422);
    const v = DATA.verses.find((x) => x[0] === s && x[1] === a);
    if (!v) return json({ detail: "لم يتم العثور على هذه الآية في المصادر المعتمدة المستوعبة حتى الآن." }, 404);
    return json({
      verse: { surah_number: v[0], ayah_number: v[1], surah_name: v[2], text: v[3] },
      mode: AI.status.mode, provider: AI.status.provider, model: AI.status.model, prompt_version: AI.status.prompt_version,
      generated_at: new Date().toISOString(), trust_category: "UNVERIFIED_CLAIM", disclaimer: AI.disclaimer,
      report_markdown: AI.report_template.replace("{surah_name}", v[2]).replace("{ayah_number}", String(v[1])),
    });
  }
  return json({ detail: "غير متاح في النسخة التجريبية." }, 404);
};

// One page, every view a hash route (see app/components/links.ts).
type Route = "home" | "search" | "history" | "quran" | "ai";
function route(): Route {
  const h = location.hash;
  if (/^#(search|v\d)/.test(h)) return "search";
  if (/^#history/.test(h)) return "history";
  if (/^#quran/.test(h)) return "quran";
  if (/^#ai(-|$)/.test(h)) return "ai";
  return "home";
}
const PAGES: Record<Route, () => JSX.Element> = { home: Home, search: SearchPage, history: HistoryPage, quran: QuranPage, ai: AiIjazPage };

function App() {
  const [view, setView] = useState({ r: route(), n: 0 });
  useEffect(() => {
    // Pages rewrite the address with replaceState (no event) as the reader moves, so a hashchange is
    // a link the reader followed: open that page afresh, as a server build would. The Quran browser
    // follows its own surah links, so it keeps its state.
    const on = () => setView((was) => {
      const r = route();
      if (r === "quran" && was.r === "quran") return was;
      scrollTo(0, 0);
      return { r, n: was.n + 1 };
    });
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  const Page = PAGES[view.r];
  return <Page key={`${view.r}-${view.n}`} />;
}

createRoot(document.getElementById("root")!).render(<App />);
