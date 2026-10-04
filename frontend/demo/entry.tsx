// Static demo: the real AFAQ page, with the API answered from bundled data.
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import AiIjazPage from "../app/ai-ijaz/page";
import Home from "../app/page";

type V = [number, number, string, string, string, number | null, number | null];
const DATA = JSON.parse(document.getElementById("afaq-data")!.textContent!) as {
  answers: Record<string, unknown>; verses: V[]; explore: unknown;
};

// Same normalization as backend/app/search.py.
const MARKS = /[ؐ-ًؚ-ٰٟۖ-ۭـ]/g;
const DIGITS = /[0-9٠-٩۰-۹]/g;
const NON_LETTER = /[^ء-ي ]/g;
const FOLD: Record<string, string> = { "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي" };
const norm = (t: string) => t.replace(MARKS, "").replace(DIGITS, "").replace(/[أإآٱىةؤئ]/g, (c) => FOLD[c])
  .replace(NON_LETTER, " ").split(/\s+/).filter(Boolean).join(" ");
const AI = JSON.parse(document.getElementById("afaq-ai")!.textContent!) as {
  status: Record<string, unknown>; disclaimer: string; report_template: string;
};
const KEYS = DATA.verses.map((v) => [norm(v[4]), norm(v[3])]);

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function minimalAnswer(v: V) {
  return {
    quranic_text: v[3], surah_number: v[0], ayah_number: v[1], surah_name: v[2], page_number: v[5], juz_number: v[6],
    verified_tafsir: [], linguistic: { words: [], meanings: [], e3rab: [], attribution: null },
    concepts: [], scientific_knowledge: [], topics: [], graph: { nodes: [{ id: "v", type: "verse", label: `${v[2]} ${v[1]}`, trust_category: "QURANIC_TEXT" }], edges: [] },
    possible_connections: [], hadith_matches: [], ijaz: { total: 0, articles: [], label: "" }, related_comparisons: [],
    not_established: ["النسخة التجريبية تعرض الطبقات الكاملة (التحليل اللغوي، التفسير، الخريطة، العلم) للآيات النموذجية فقط؛ وهي كلها متاحة لكل الآيات في نسخة الخادم."],
    sources: [{ title: "مصحف المدينة النبوية للنشر الحاسوبي — رواية حفص (الإصدار 3.0)", publisher: "مجمع الملك فهد لطباعة المصحف الشريف", url: "https://qurancomplex.gov.sa/quran-hafs/", trust_category: "QURANIC_TEXT" }],
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
  if (url.pathname === "/explore") return json(DATA.explore);
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

// One page, two views: #ai or #ai-v{surah}-{ayah} is the AI section, anything else the verse journey.
const isAi = () => /^#ai(-|$)/.test(location.hash);
function App() {
  const [ai, setAi] = useState(isAi);
  useEffect(() => {
    // the journey rewrites the hash on every verse it opens; only a switch of view scrolls to the top
    const on = () => setAi((was) => { const now = isAi(); if (now !== was) scrollTo(0, 0); return now; });
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  return ai ? <AiIjazPage /> : <Home />;
}

createRoot(document.getElementById("root")!).render(<App />);
