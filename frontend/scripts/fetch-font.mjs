// The KFGQPC Hafs font is not in git (public repository). On a host, QURAN_FONT_URL is a
// direct download link of kfgqpc_hafs_v30.ttf, fetched here before the build. A Dropbox
// share link (?dl=0) or a Google Drive "view" link is turned into a direct download.
import { existsSync, mkdirSync, writeFileSync } from "node:fs";

const dest = new URL("../public/fonts/kfgqpc_hafs_v30.ttf", import.meta.url);
let url = (process.env.QURAN_FONT_URL || "").trim();
if (existsSync(dest)) {
  console.log("[font] already present");
} else if (!url) {
  console.warn("[font] QURAN_FONT_URL not set: the Quran text will use a fallback font");
} else {
  if (url.includes("dropbox.com")) url = url.replace(/([?&])dl=0/, "$1dl=1").replace(/^(?!.*[?&](dl|raw)=1)(.*)$/, (m) => m + (m.includes("?") ? "&" : "?") + "dl=1");
  const drive = url.match(/drive\.google\.com\/(?:file\/d\/|open\?id=|uc\?(?:.*&)?id=)([\w-]{20,})/);
  if (drive) url = `https://drive.usercontent.google.com/download?id=${drive[1]}&export=download&confirm=t`;
  const res = await fetch(url, { redirect: "follow" });
  const buf = Buffer.from(await res.arrayBuffer());
  // a TrueType file starts with 00 01 00 00 (or "true"); anything else is a web page, not the font
  const ok = res.ok && buf.length > 50_000 && (buf.readUInt32BE(0) === 0x00010000 || buf.toString("latin1", 0, 4) === "true");
  if (!ok) {
    console.warn(`[font] the link did not return the font (HTTP ${res.status}, ${buf.length} bytes): the Quran text will use a fallback font`);
  } else {
    mkdirSync(new URL("../public/fonts/", import.meta.url), { recursive: true });
    writeFileSync(dest, buf);
    console.log(`[font] downloaded ${(buf.length / 1024).toFixed(0)} KB`);
  }
}
