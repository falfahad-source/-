// Every in-app link goes through here. The server build uses real paths (/search?v=24:40);
// the static demo is one page, so the same places are hash routes (#v24-40). Pages read
// their parameters with readParams(), which understands both.
export const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

const q = (params: Record<string, string | number | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const link = {
  home: () => (DEMO ? "#home" : "/"),
  search: (query?: string) => (DEMO ? `#search${q({ q: query })}` : `/search${q({ q: query })}`),
  verse: (s: number, a: number) => (DEMO ? `#v${s}-${a}` : `/search?v=${s}:${a}`),
  history: () => (DEMO ? "#history" : "/history"),
  quran: (s?: number, a?: number) => (DEMO ? `#quran${s ? `-${s}` : ""}${a ? `-${a}` : ""}` : `/quran${q({ s, a })}`),
  // a mushaf page, optionally with an ayah selected on it
  mushafPage: (p: number, s?: number, a?: number) => (DEMO ? `#quran${q({ p, s, a })}` : `/quran${q({ p, s, a })}`),
  ai: (s?: number, a?: number) => (DEMO ? (s ? `#ai-v${s}-${a}` : "#ai") : `/ai-ijaz${s ? `?v=${s}:${a}` : ""}`),
};

/** The current page's parameters (v=“s:a”, q, s, a), from the query string or a demo hash route. */
export function readParams(): URLSearchParams {
  if (!DEMO) return new URLSearchParams(location.search);
  const h = location.hash;
  let m;
  if ((m = /^#(?:ai-)?v(\d{1,3})-(\d{1,3})$/.exec(h))) return new URLSearchParams({ v: `${m[1]}:${m[2]}` });
  if ((m = /^#quran-(\d{1,3})(?:-(\d{1,3}))?$/.exec(h))) return new URLSearchParams(m[2] ? { s: m[1], a: m[2] } : { s: m[1] });
  const i = h.indexOf("?");
  return new URLSearchParams(i >= 0 ? h.slice(i + 1) : "");
}

/** Change the address to `href` (from `link`) without reloading or adding a history entry. */
export function replaceUrl(href: string) {
  try { history.replaceState(null, "", href); } catch { /* not allowed in some frames */ }
}

/** Parse “s:a” as in ?v=24:40. */
export function verseParam(p: URLSearchParams): [number, number] | null {
  const m = /^(\d{1,3}):(\d{1,3})$/.exec(p.get("v") ?? "");
  return m ? [+m[1], +m[2]] : null;
}
