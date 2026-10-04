// The reader's search history (سجل البحث). There are no accounts, so it lives in this
// browser only (localStorage); every access is guarded because storage can be blocked.
export type HistoryEntry =
  | { kind: "search"; query: string; total: number; at: string }
  | { kind: "verse"; s: number; a: number; surah: string; at: string }
  | { kind: "ai"; s: number; a: number; surah: string; mode: string; at: string };

type NewEntry = HistoryEntry extends infer E ? (E extends HistoryEntry ? Omit<E, "at"> : never) : never;

const KEY = "afaq-history";
const MAX = 300;

const same = (x: HistoryEntry, y: NewEntry) =>
  x.kind === y.kind && (x.kind === "search" ? x.query === (y as { query: string }).query
    : x.s === (y as { s: number }).s && x.a === (y as { a: number }).a);

export function readHistory(): HistoryEntry[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v : [];
  } catch { return []; }
}

function write(items: HistoryEntry[]) {
  try { localStorage.setItem(KEY, JSON.stringify(items.slice(0, MAX))); } catch { /* storage blocked */ }
}

/** Newest first; repeating the latest entry only refreshes its time. */
export function addHistory(e: NewEntry) {
  const items = readHistory();
  const entry = { ...e, at: new Date().toISOString() } as HistoryEntry;
  if (items[0] && same(items[0], e)) items[0] = entry; else items.unshift(entry);
  write(items);
}

export function removeHistory(at: string) { write(readHistory().filter((x) => x.at !== at)); }
export function clearHistory() { write([]); }
