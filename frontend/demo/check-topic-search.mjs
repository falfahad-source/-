// Check that the demo's topic search (demo/topicSearch.ts) answers like the backend's
// (app/topic_search.py): same verses, same order, same reasons, for real queries.
//   (backend, on the database the demo was exported from) uvicorn app.main:app --port 8000
//   (frontend) node demo/check-topic-search.mjs [http://localhost:8000]
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const api = process.argv[2] ?? "http://localhost:8000";
const QUERIES = ["مدة الرضاعة الطبيعية", "البحار", "البحر", "الجنين", "الأجنة", "تكوين الجنين في الرحم", "حركة الشمس",
  "دوران الشمس", "البرق والرعد", "النحل والعسل", "الماء العذب والمالح", "الجبال", "الرواسي", "المطر", "الغيث",
  "الحليب", "اللبن", "الفطام", "زكاة", "رضا", "الصلاة", "النجوم", "الأنهار", "ذكاء الانسان", "عقل الانسان",
  "ذكاء الإنسان والتفكر", "طبقات المحيط"];

const mod = join(tmpdir(), "afaq-topic-search.mjs");
writeFileSync(mod, execFileSync("npx", ["--yes", "esbuild@0.24.0", join(here, "topicSearch.ts"), "--bundle",
  "--format=esm", "--log-level=warning"], { cwd: join(here, "..") }));
const { searchTopics, textWords, loadLexicon } = await import(pathToFileURL(mod).href);

// the same entries demo/entry.tsx builds
const DATA = JSON.parse(readFileSync(join(here, "data.json"), "utf8"));
loadLexicon(DATA.topic_lexicon, DATA.topic_synonyms);
const entries = DATA.topic_index.map(([kind, label, url, verses]) => ({ kind, label, url, words: textWords(label), verses }));
const book = DATA.brief.meta.source;
DATA.verses.forEach((v, i) => {
  const key = `${v[0]}:${v[1]}`;
  const full = DATA.answers[key];
  const text = full ? full.verified_tafsir.find((t) => t.source === book)?.text : DATA.brief.verses[key]?.[0];
  if (text) entries.push({ kind: "tafsir", label: book, url: null, words: textWords(text), verses: [i] });
});
const verse = (i) => { const v = DATA.verses[i]; return [v[0], v[1], v[2], v[3], v[5]]; };

const sig = (r) => r.results.map((x) => `${x.surah_number}:${x.ayah_number} ${x.reasons.map((y) => `${y.kind}/${y.label}/${(y.synonyms ?? []).join("+")}`).join(",")}`);
let bad = 0;
for (const q of QUERIES) {
  const server = await (await fetch(`${api}/search/topics?${new URLSearchParams({ q, limit: "30" })}`)).json();
  const demo = searchTopics(entries, verse, q, 30, 0);
  const a = sig(server), b = sig(demo);
  const same = server.total === demo.total && JSON.stringify(a) === JSON.stringify(b);
  if (!same) bad++;
  console.log(`${same ? "same" : "DIFF"}  ${q}: ${server.total} / ${demo.total}`);
  if (!same) a.forEach((x, i) => x !== b[i] && console.log(`   server: ${x}\n   demo:   ${b[i]}`));
}
process.exit(bad ? 1 : 0);
