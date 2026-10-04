"use client";

import { useState } from "react";
import { ar } from "./common";
import { link } from "./links";

/** Copy the verse with its reference, or share (or copy) a link that opens it. */
export default function ShareVerse({ s, a, surah, text }: { s: number; a: number; surah: string; text: string }) {
  const [done, setDone] = useState<string | null>(null);
  const url = () => new URL(link.verse(s, a), location.href).href;
  const ref = `[سورة ${surah}: ${ar(a)}]`;

  async function copy(value: string, msg: string) {
    try { await navigator.clipboard.writeText(value); setDone(msg); } catch { setDone("تعذّر النسخ؛ انسخه يدويًا."); }
    setTimeout(() => setDone(null), 2500);
  }
  async function share() {
    if (navigator.share) {
      try { await navigator.share({ title: `سورة ${surah}، الآية ${ar(a)}`, text: `${text} ${ref}`, url: url() }); return; }
      catch (e) { if ((e as Error).name === "AbortError") return; }
    }
    copy(url(), "نُسخ رابط الآية.");
  }

  return (
    <div className="share">
      <button type="button" className="btn-ghost" onClick={() => copy(`${text} ${ref}`, "نُسخ نص الآية.")}>نسخ نص الآية</button>
      <button type="button" className="btn-ghost" onClick={share}>مشاركة رابط الآية</button>
      <span className="note" role="status">{done}</span>
    </div>
  );
}
