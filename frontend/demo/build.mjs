// Build the static demo page: the real AFAQ page bundled with its data, one HTML body.
//   (backend) python -m app.demo_export ../frontend/demo/data.json
//   (frontend) node demo/build.mjs demo/afaq-demo.html
// Runs python in ../backend for the AI section's test-mode data.
// Needs the KFGQPC font at public/fonts/kfgqpc_hafs_v30.ttf (not in git).
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = process.argv[2] ?? join(here, "afaq-demo.html");
const bundle = execFileSync("npx", ["--yes", "esbuild@0.24.0", join(here, "entry.tsx"), "--bundle", "--minify",
  "--format=iife", "--jsx=automatic", "--target=es2020", "--log-level=warning",
  "--define:process.env.NEXT_PUBLIC_API_BASE=\"https://afaq.demo\"", "--define:process.env.NEXT_PUBLIC_DEMO=\"1\"",
  "--define:process.env.NODE_ENV=\"production\""], { cwd: join(here, ".."), maxBuffer: 64 << 20 }).toString();
// the fonts are embedded, so the page renders the same offline
const fontsDir = join(here, "..", "public", "fonts");
const embed = (text) => text.replace(/url\("\/fonts\/([\w.-]+\.(ttf|woff2))"\)/g, (_, file, ext) =>
  `url(data:font/${ext};base64,${readFileSync(join(fontsDir, file)).toString("base64")})`);
const css = embed(readFileSync(join(here, "..", "app", "fonts.css"), "utf8") + readFileSync(join(here, "..", "app", "globals.css"), "utf8"));
const data = readFileSync(join(here, "data.json"), "utf8").replace(/<\//g, "<\\/");
// «الذكاء الاصطناعي في الإعجاز العلمي» in test mode: prompt, disclaimer and report template from the backend
const ai = execFileSync("python", ["-m", "app.ai_research.demo_data"], { cwd: join(here, "..", "..", "backend") })
  .toString().replace(/<\//g, "<\\/");
const html = `<title>آفاق</title>
<link rel="icon" href="data:image/svg+xml;base64,${readFileSync(join(here, "..", "app", "icon.svg")).toString("base64")}">
<style>${css}</style>
<div id="root" dir="rtl" lang="ar"></div>
<script type="application/json" id="afaq-data">${data}</script>
<script type="application/json" id="afaq-ai">${ai}</script>
<script>${bundle.replace(/<\/script/gi, "<\\/script")}</script>
`;
writeFileSync(out, html);
console.log(`${out}: ${(html.length / 1e6).toFixed(2)} MB (chars)`);
