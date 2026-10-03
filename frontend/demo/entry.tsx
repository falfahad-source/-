// Static demo: the real AFAQ page, with the API answered from bundled data.
import { createRoot } from "react-dom/client";
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
  return json({ detail: "غير متاح في النسخة التجريبية." }, 404);
};

createRoot(document.getElementById("root")!).render(<Home />);
