// Build the static demo page: the real AFAQ page bundled with its data, one HTML body.
//   (backend) python -m app.demo_export ../frontend/demo/data.json
//   (frontend) node demo/build.mjs demo/afaq-demo.html
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
const font = readFileSync(join(here, "..", "public", "fonts", "kfgqpc_hafs_v30.ttf")).toString("base64");
const css = readFileSync(join(here, "..", "app", "globals.css"), "utf8")
  .replace('url("/fonts/kfgqpc_hafs_v30.ttf")', `url(data:font/ttf;base64,${font})`);
const data = readFileSync(join(here, "data.json"), "utf8").replace(/<\//g, "<\\/");
const html = `<title>آفاق</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600&family=Noto+Naskh+Arabic:wght@400;600&family=Reem+Kufi:wght@500;700&display=swap">
<style>${css}</style>
<div id="root" dir="rtl" lang="ar"></div>
<script type="application/json" id="afaq-data">${data}</script>
<script>${bundle.replace(/<\/script/gi, "<\\/script")}</script>
`;
writeFileSync(out, html);
console.log(`${out}: ${(html.length / 1e6).toFixed(2)} MB (chars)`);
