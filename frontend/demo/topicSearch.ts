// Topic search for the static demo: a line-by-line port of backend/app/topic_search.py
// (keep the two in step; demo/check-topic-search.mjs compares them on real queries).
// Entries come from the export (`topic_index`) plus التفسير الميسر read from the page data; the
// lemma map and synonyms from `topic_lexicon` and `topic_synonyms` (call loadLexicon first).

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

const SYNONYM_CREDIT = 0.8;

export type Kind = keyof typeof WEIGHTS;
type Words = [string, Set<string>][];  // a text's words as [stem, lemmas]; lemmas empty if unknown
export type Entry = { kind: Kind; label: string; url: string | null; words: Words; verses: number[] };

// The Quran word -> lemma map and the synonym groups, from the export (load before searching).
let LEX = new Map<string, Set<string>>();
let SYNONYM_GROUPS: string[][] = [];
export function loadLexicon(lexicon: { lemmas: string[]; forms: Record<string, number[]> }, synonyms: string[][]) {
  LEX = new Map(Object.entries(lexicon.forms).map(([w, ix]) => [w, new Set(ix.map((i) => lexicon.lemmas[i]))]));
  SYNONYM_GROUPS = synonyms;
}

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

function stripArticle(w: string): string {
  for (const p of PREFIXES) if (w.startsWith(p) && w.length - p.length >= 2) return w.slice(p.length);
  return w;
}

const EMPTY = new Set<string>();
const wordLemmas = (w: string) => LEX.get(w) ?? LEX.get(stripArticle(w)) ?? EMPTY;

export function textWords(text: string): Words {
  const seen = new Map<string, [string, Set<string>]>();
  for (const w of norm(text).split(" ")) {
    if (!w || STOPWORDS.has(w)) continue;
    const s = stem(w), l = wordLemmas(w);
    const key = `${s}|${[...l].sort().join(",")}`;
    if (!seen.has(key)) seen.set(key, [s, l]);
  }
  return [...seen.values()];
}

// «البرق والرعد»: words joined by و ask for either; a construct phrase asks for its subject
const isCoordinated = (q: string) => norm(q).split(" ").slice(1).some((w) => w.startsWith("وال"));

const wordMatch = (q: string, c: string) => q.length <= 3 ? c === q
  : c === q || c.startsWith(q) || c.includes(q) || (c.length >= 4 && q.length - c.length <= 1 && q.startsWith(c));
const meets = (a: Set<string>, b: Set<string>) => { for (const x of a) if (b.has(x)) return true; return false; };
const sameWord = (qs: string, ql: Set<string>, cs: string, cl: Set<string>) =>
  ql.size && cl.size ? meets(ql, cl) : wordMatch(qs, cs);

type Word = { stem: string; lemmas: Set<string>; synonyms: [string, string, Set<string>][] };

function queryWords(q: string): Word[] {
  const out: Word[] = [];
  for (const w of norm(q).split(" ")) {
    if (!w || STOPWORDS.has(w)) continue;
    const s = stem(w);
    if (s.length < 3 || out.some((x) => x.stem === s)) continue;
    const lemmas = wordLemmas(w);
    const syns: [string, string, Set<string>][] = [];
    for (const group of SYNONYM_GROUPS) {
      const members = group.map((m) => [m, stem(norm(m)), wordLemmas(norm(m))] as [string, string, Set<string>]);
      if (members.some(([, ms, ml]) => ms === s || (lemmas.size > 0 && meets(ml, lemmas))))
        syns.push(...members.filter(([, ms, ml]) => ms !== s && !(lemmas.size > 0 && meets(ml, lemmas))));
    }
    out.push({ stem: s, lemmas, synonyms: syns });
  }
  return out;
}

function credit(w: Word, words: Words, allowSynonyms: boolean): [number, string | null] {
  if (words.some(([cs, cl]) => sameWord(w.stem, w.lemmas, cs, cl))) return [1, null];
  if (allowSynonyms)
    for (const [word, ms, ml] of w.synonyms) if (words.some(([cs, cl]) => sameWord(ms, ml, cs, cl))) return [SYNONYM_CREDIT, word];
  return [0, null];
}

type Reason = { kind: Kind; label: string; url: string | null; coverage: number; synonyms: string[] };
type Hit = Map<string, [number, string | null]>;

function score(entries: Entry[], words: Word[], hits: Hit[], weight: Record<string, number>, either: boolean, core: string | null) {
  const total = words.reduce((a, w) => a + weight[w.stem], 0);
  const raw = new Map<number, number>(), reasons = new Map<number, Reason[]>(), best = new Map<number, Map<string, number>>();
  entries.forEach((e, i) => {
    const h = hits[i];
    if (!h.size) return;
    let sum = 0;
    for (const [w, [c]] of h) sum += weight[w] * c;
    const cov = sum / total;
    if (e.kind === "tafsir" && cov < 0.75) return;
    const via = [...new Set([...h.values()].map(([, v]) => v).filter((v): v is string => !!v))].sort();
    for (const v of e.verses) {
      const rs = reasons.get(v) ?? [];
      if (rs.some((r) => r.kind === e.kind && r.label === e.label)) continue;
      raw.set(v, (raw.get(v) ?? 0) + WEIGHTS[e.kind] * cov * cov);
      rs.push({ kind: e.kind, label: e.label, url: e.url, coverage: Math.round(cov * 100) / 100, synonyms: via });
      reasons.set(v, rs);
      const b = best.get(v) ?? new Map<string, number>();
      for (const [w, [c]] of h) b.set(w, Math.max(b.get(w) ?? 0, c));
      best.set(v, b);
    }
  });
  // a verse is judged on all its sources together (see _score in the backend)
  const sc = new Map<number, number>();
  for (const [v, got] of best) {
    let s2 = 0;
    for (const [w, c] of got) s2 += weight[w] * c;
    const vcov = s2 / total;
    if (vcov >= 0.5 || (either && got.size / words.length >= 0.5) || (core !== null && got.has(core))) sc.set(v, raw.get(v)! * vcov);
  }
  return { sc, reasons };
}

/** Same result shape as GET /search/topics; `verse(i)` gives a verse's [surah, ayah, name, text, page]. */
export function searchTopics(entries: Entry[], verse: (i: number) => [number, number, string, string, number | null],
  q: string, limit: number, offset: number) {
  const words = queryWords(q);
  if (!words.length) throw new Error("اكتب موضوعًا من كلمة واحدة على الأقل (ثلاثة أحرف فأكثر)، مثل: الرضاعة، البحار، الجنين.");
  const hits: Hit[] = entries.map((e) => {
    const h: Hit = new Map();
    for (const w of words) {
      const [c, via] = credit(w, e.words, e.kind !== "tafsir");
      if (c) h.set(w.stem, [c, via]);
    }
    return h;
  });
  const n = entries.length;
  const weight: Record<string, number> = {};
  for (const w of words) weight[w.stem] = Math.log((n + 1) / (hits.filter((h) => h.has(w.stem)).length + 1)) + 1;
  const either = isCoordinated(q);
  let r = score(entries, words, hits, weight, either, null);
  if (r.sc.size < FEW && words.length >= 2) {
    // the phrase's subject: its rarest word in the sources (the first such, on a tie)
    const core = words.reduce((a, w) => (weight[w.stem] > weight[a.stem] ? w : a)).stem;
    r = score(entries, words, hits, weight, either, core);
  }
  const ranked = [...r.sc.keys()].sort((a, b) => {
    const r6 = (x: number) => Math.round(x * 1e6) / 1e6;  // equal scores tie exactly, as in the backend
    const d = r6(r.sc.get(b)!) - r6(r.sc.get(a)!);
    if (d) return d;
    const [sa, aa] = verse(a), [sb, ab] = verse(b);
    return sa - sb || aa - ab;
  });
  const results = ranked.slice(offset, offset + limit).map((i) => {
    const [s, a, name, text, page] = verse(i);
    const rs = [...r.reasons.get(i)!].sort((x, y) => WEIGHTS[y.kind] - WEIGHTS[x.kind] || y.coverage - x.coverage);
    return { surah_number: s, ayah_number: a, surah_name: name, text, page_number: page,
      score: Math.round(r.sc.get(i)! * 100) / 100, reasons: rs.slice(0, 4), more_reasons: Math.max(0, rs.length - 4) };
  });
  return { query: q, words: words.map((w) => w.stem), total: ranked.length, offset, results };
}
