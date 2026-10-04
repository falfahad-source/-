// Topic search for the static demo: a line-by-line port of backend/app/topic_search.py
// (keep the two in step; demo/check-topic-search.mjs compares them on real queries).
// Entries come from the export (`topic_index`) plus التفسير الميسر read from the page data.

// Same normalization as backend/app/search.py normalize_arabic.
// Written as \u escapes: right-to-left editors silently reorder literal Arabic in ranges.
const MARKS = /[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]/g;
const DIGITS = /[0-9\u0660-\u0669\u06F0-\u06F9]/g;
const NON_LETTER = /[^\u0621-\u064A ]/g;
const FOLD: Record<string, string> = {
  "\u0623": "\u0627", "\u0625": "\u0627", "\u0622": "\u0627", "\u0671": "\u0627",
  "\u0649": "\u064A", "\u0629": "\u0647", "\u0624": "\u0648", "\u0626": "\u064A",
};
export const norm = (t: string) => t.replace(MARKS, "").replace(DIGITS, "").replace(/[\u0623\u0625\u0622\u0671\u0649\u0629\u0624\u0626]/g, (c) => FOLD[c])
  .replace(NON_LETTER, " ").split(/\s+/).filter(Boolean).join(" ");

const STOPWORDS = new Set(["من", "في", "عن", "على", "الى", "الي", "ما", "ماذا", "هل", "هو", "هي", "مع", "او", "ثم", "كل",
  "ذلك", "هذا", "هذه", "التي", "الذي", "الذين", "ان", "قد", "لا", "لم", "بين", "عند", "حول",
  "ايه", "ايات", "الايه", "الايات", "القران", "اعجاز", "الاعجاز", "العلمي", "علمي"]);
const PREFIXES = ["وال", "بال", "فال", "كال", "لل", "ال"];
const PRONOUNS = ["هما", "ها", "هم", "هن", "كم", "نا"];
const SUFFIXES = ["يات", "ات", "ون", "ين", "ان", "يه", "ه", "ي"];
const WEIGHTS = { concept: 5, topic: 3, article: 2, tafsir: 1 } as const;
const FEW = 10;

export type Kind = keyof typeof WEIGHTS;
export type Entry = { kind: Kind; label: string; url: string | null; stems: Set<string>; verses: number[] };

export function stem(word: string): string {
  for (const p of PREFIXES) if (word.startsWith(p) && word.length - p.length >= 3) { word = word.slice(p.length); break; }
  for (const s of PRONOUNS) {
    if (word.endsWith(s) && word.length - s.length >= 3) {
      word = word.slice(0, -s.length);
      if (word.endsWith("ت")) word = word.slice(0, -1) + "ه";
      break;
    }
  }
  for (const s of SUFFIXES) if (word.endsWith(s) && word.length - s.length >= 3) { word = word.slice(0, -s.length); break; }
  return word;
}

export const stems = (text: string) => new Set(norm(text).split(" ").filter((w) => w && !STOPWORDS.has(w)).map(stem));

export function queryStems(q: string): string[] {
  const out: string[] = [];
  for (const w of norm(q).split(" ")) {
    if (!w || STOPWORDS.has(w)) continue;
    const s = stem(w);
    if (s.length >= 3 && !out.includes(s)) out.push(s);
  }
  return out;
}

export function coreStem(q: string): string | null {
  for (const w of norm(q).split(" ")) {
    if (w && !STOPWORDS.has(w) && PREFIXES.some((p) => w.startsWith(p))) {
      const s = stem(w);
      if (s.length >= 3) return s;
    }
  }
  return null;
}

const wordMatch = (q: string, c: string) =>
  c === q || c.startsWith(q) || (q.length >= 4 && c.includes(q)) || (c.length >= 4 && q.length - c.length <= 1 && q.startsWith(c));
const has = (w: string, cand: Set<string>) => { for (const c of cand) if (wordMatch(w, c)) return true; return false; };

type Reason = { kind: Kind; label: string; url: string | null; coverage: number };

function score(entries: Entry[], words: string[], hits: string[][], weight: Record<string, number>, core: string | null) {
  const sc = new Map<number, number>(), reasons = new Map<number, Reason[]>();
  const total = words.reduce((a, w) => a + weight[w], 0);
  entries.forEach((e, i) => {
    const h = hits[i];
    if (!h.length) return;
    const cov = h.reduce((a, w) => a + weight[w], 0) / total;
    if (e.kind === "tafsir") { if (cov < 0.75) return; }
    else if (cov < 0.5 && h.length / words.length < 0.5 && !(core && h.includes(core))) return;
    for (const v of e.verses) {
      const rs = reasons.get(v) ?? [];
      if (rs.some((r) => r.kind === e.kind && r.label === e.label)) continue;
      sc.set(v, (sc.get(v) ?? 0) + WEIGHTS[e.kind] * cov * cov);
      rs.push({ kind: e.kind, label: e.label, url: e.url, coverage: Math.round(cov * 100) / 100 });
      reasons.set(v, rs);
    }
  });
  return { sc, reasons };
}

/** Same result shape as GET /search/topics; `verse(i)` gives a verse's [surah, ayah, name, text, page]. */
export function searchTopics(entries: Entry[], verse: (i: number) => [number, number, string, string, number | null],
  q: string, limit: number, offset: number) {
  const words = queryStems(q);
  if (!words.length) throw new Error("اكتب موضوعًا من كلمة واحدة على الأقل (ثلاثة أحرف فأكثر)، مثل: الرضاعة، البحار، الجنين.");
  const hits = entries.map((e) => words.filter((w) => has(w, e.stems)));
  const n = entries.length;
  const weight: Record<string, number> = {};
  for (const w of words) weight[w] = Math.log((n + 1) / (hits.filter((h) => h.includes(w)).length + 1)) + 1;
  let r = score(entries, words, hits, weight, null);
  const core = coreStem(q);
  if (r.sc.size < FEW && words.length >= 2 && core) r = score(entries, words, hits, weight, core);
  const ranked = [...r.sc.keys()].sort((a, b) => {
    const d = r.sc.get(b)! - r.sc.get(a)!;
    if (Math.abs(d) > 1e-9) return d;
    const [sa, aa] = verse(a), [sb, ab] = verse(b);
    return sa - sb || aa - ab;
  });
  const results = ranked.slice(offset, offset + limit).map((i) => {
    const [s, a, name, text, page] = verse(i);
    const rs = [...r.reasons.get(i)!].sort((x, y) => WEIGHTS[y.kind] - WEIGHTS[x.kind] || y.coverage - x.coverage);
    return { surah_number: s, ayah_number: a, surah_name: name, text, page_number: page,
      score: Math.round(r.sc.get(i)! * 100) / 100, reasons: rs.slice(0, 4), more_reasons: Math.max(0, rs.length - 4) };
  });
  return { query: q, words, total: ranked.length, offset, results };
}
