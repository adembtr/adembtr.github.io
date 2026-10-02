// Checks every external URL referenced in src/content.js and index.html.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const files = ['src/content.js', 'index.html', 'public/404.html', 'tools/cv.html'].map((f) => path.resolve(here, '..', f));
const urls = new Set();
for (const f of files) {
  const s = fs.readFileSync(f, 'utf8');
  for (const m of s.matchAll(/https?:\/\/[^\s"'<>)\]]+/g)) {
    const u = m[0].replace(/[.,;]+$/, '');
    if (/fonts\.g|schema\.org|sitemaps\.org|w3\.org|img\.shields|adembtr\.github\.io/.test(u)) continue;
    urls.add(u);
  }
}
let bad = 0;
for (const u of urls) {
  try {
    const r = await fetch(u, { redirect: 'follow', headers: { 'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36' }, signal: AbortSignal.timeout(20000) });
    const ok = r.status < 400 || r.status === 999 || r.status === 403;
    console.log(`${ok ? 'ok ' : 'BAD'} ${r.status} ${u}`);
    if (!ok) bad++;
  } catch (e) { console.log(`ERR ${u} ${e.message}`); bad++; }
}
console.log(bad ? `${bad} bad links` : 'all links ok');
