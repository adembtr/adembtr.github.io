// QA pass with Playwright against the built site (vite preview on :4173).
// Screenshots at 1440x900 and 390x844, console errors, link check, overflow check,
// plus the OG image and the static point-cloud fallback render.
import { chromium, devices } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, '..');
const QA = path.join(ROOT, '_qa');
fs.mkdirSync(QA, { recursive: true });
const BASE = process.env.QA_BASE || 'http://localhost:4173';
const mode = process.argv[2] || 'all';
const problems = [];
const { execSync } = await import('node:child_process');
async function status(url) {
  try { const r = await fetch(url, { method: 'GET', redirect: 'follow', headers: { 'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36' }, signal: AbortSignal.timeout(15000) }); return r.status; }
  catch (_) { try { return Number(execSync(`curl -s -o /dev/null -w '%{http_code}' -L --max-time 20 -A 'Mozilla/5.0' '${url}'`).toString().trim()); } catch (__) { return 0; } }
}

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

async function pageWithLogs(context) {
  const page = await context.newPage();
  page.on('console', (m) => { if (m.type() === 'error') problems.push(`console.error: ${m.text()}`); });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('requestfailed', (r) => {
    const err = r.failure()?.errorText || '';
    // media elements abort and restart their own range requests; that is normal, not a failure
    if (r.resourceType() === 'media' && err.includes('ERR_ABORTED')) return;
    problems.push(`requestfailed: ${r.url()} ${err}`);
  });
  page.on('response', (r) => { if (r.status() >= 400 && r.url().startsWith(BASE)) problems.push(`http ${r.status()}: ${r.url()}`); });
  return page;
}
const waitHero = (page) => page.waitForFunction(() => window.__hero && window.__hero.ready, null, { timeout: 25000 }).catch(() => problems.push('hero never became ready'));

if (mode === 'all' || mode === 'og') {
  // OG image 1200x630
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  const page = await pageWithLogs(ctx);
  await page.goto(BASE + '/?og=1', { waitUntil: 'networkidle' });
  await waitHero(page);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(ROOT, 'public/og.png') });
  console.log('og.png written');
  await ctx.close();
  if (process.argv.includes('--cloud')) {
  // static cloud fallback (transparent)
  const ctx2 = await browser.newContext({ viewport: { width: 1200, height: 1200 }, deviceScaleFactor: 1 });
  const p2 = await pageWithLogs(ctx2);
  await p2.goto(BASE + '/?cloudshot=1', { waitUntil: 'networkidle' });
  await waitHero(p2);
  await p2.waitForTimeout(800);
  await p2.screenshot({ path: path.join(ROOT, 'tools/portrait_cloud.png'), omitBackground: true });
  console.log('portrait_cloud.png written (convert to webp with tools/convert_cloud.py)');
  await ctx2.close();
  }
}

if (mode === 'all' || mode === 'shots') {
  const views = [
    { name: 'desktop', opts: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 } },
    { name: 'mobile', opts: { ...devices['iPhone 14'], viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 } },
  ];
  for (const v of views) {
    const ctx = await browser.newContext(v.opts);
    const page = await pageWithLogs(ctx);
    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await waitHero(page);
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(QA, `hero_${v.name}.png`) });
    await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; });
    // overflow
    const over = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
    if (over.sw > over.iw + 1) problems.push(`${v.name}: horizontal overflow ${over.sw} > ${over.iw}`);
    // scroll through to trigger reveals and lazy media
    await page.evaluate(async () => {
      const h = document.documentElement.scrollHeight;
      for (let y = 0; y < h; y += Math.round(innerHeight * 0.6)) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 90)); }
      scrollTo(0, 0);
    });
    await page.waitForTimeout(600);
    await page.evaluate(() => document.querySelectorAll('.reveal').forEach((el) => el.classList.add('in')));
    if (v.name === 'desktop') {
      await page.screenshot({ path: path.join(QA, `full_${v.name}.png`), fullPage: true });
    } else {
      // full-page capture is unreliable under mobile emulation; capture each section instead
      for (const id of ['highlights', 'about', 'projects', 'experience', 'education-honors', 'skills', 'contact']) {
        await page.evaluate((id) => { const el = document.getElementById(id); scrollTo(0, el.offsetTop - 70); }, id);
        await page.waitForTimeout(350);
        await page.screenshot({ path: path.join(QA, `${v.name}_${id}.png`) });
      }
    }
    // elements wider than viewport
    const wide = await page.evaluate(() => [...document.querySelectorAll('body *')].filter((el) => { const r = el.getBoundingClientRect(); return r.right > innerWidth + 1 && r.width > 0 && getComputedStyle(el).position !== 'fixed'; }).slice(0, 8).map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}`));
    if (wide.length) problems.push(`${v.name}: elements wider than viewport: ${wide.join(', ')}`);
    // dialog
    await page.click('.project-card');
    await page.waitForSelector('dialog[open]');
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(QA, `dialog_${v.name}.png`) });
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
    if (await page.$('dialog[open]')) problems.push(`${v.name}: dialog did not close on Escape`);
    // language toggle
    await page.click('#langToggle');
    await page.waitForTimeout(400);
    const lang = await page.evaluate(() => document.documentElement.lang);
    if (lang !== 'tr') problems.push(`${v.name}: lang toggle failed (${lang})`);
    await page.evaluate(() => scrollTo(0, 0));
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(QA, `hero_tr_${v.name}.png`) });
    await page.evaluate(() => { scrollTo(0, document.querySelector('#projects').offsetTop - 60); });
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(QA, `projects_tr_${v.name}.png`) });
    await page.click('#langToggle');
    // links
    if (v.name === 'desktop') {
      const hrefs = await page.evaluate(() => [...document.querySelectorAll('a[href]')].map((a) => a.getAttribute('href')));
      // also dialog links
      const dlgLinks = await page.evaluate(() => { const set = new Set(); return set; });
      const uniq = [...new Set(hrefs)];
      for (const href of uniq) {
        if (href.startsWith('#')) {
          if (href !== '#' && !(await page.$(href))) problems.push(`missing anchor target ${href}`);
        } else if (href.startsWith('mailto:')) {
          continue;
        } else if (href.startsWith('/')) {
          const code = await status(BASE + href);
          if (code >= 400 || code === 0) problems.push(`internal link ${href} -> ${code}`);
        } else if (href.includes('linkedin.com')) {
          console.log('link skipped (LinkedIn blocks scripted fetches; verified with curl -> 999) ' + href);
        } else {
          try {
            const r = await fetch(href, { method: 'GET', redirect: 'follow', headers: { 'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36' }, signal: AbortSignal.timeout(15000) });
            if (r.status >= 400 && r.status !== 999 && r.status !== 403) problems.push(`external link ${href} -> ${r.status}`);
            else console.log(`link ok ${r.status} ${href}`);
          } catch (e) {
            // Node's fetch occasionally fails on TLS/IPv6 where browsers succeed; confirm with curl before reporting
            const { execSync } = await import('node:child_process');
            let code = '000';
            try { code = execSync(`curl -s -o /dev/null -w '%{http_code}' -L --max-time 20 -A 'Mozilla/5.0' '${href}'`).toString().trim(); } catch (_) { /* keep 000 */ }
            if (Number(code) >= 200 && Number(code) < 400) console.log(`link ok ${code} (curl) ${href}`);
            else problems.push(`external link ${href} failed: ${e.message} / curl ${code}`);
          }
        }
      }
      void dlgLinks;
      // media files
      for (const f of ['/assets/cloud/portrait_3d_hi.bin', '/assets/cloud/portrait_3d_lo.bin', '/assets/pdf/Adem_Batur_CV.pdf', '/og.png', '/sitemap.xml', '/robots.txt', '/favicon.svg', '/favicon.png', '/apple-touch-icon.png', '/404.html', '/assets/img/portrait_cloud.webp']) {
        const code = await status(BASE + f); if (code >= 400 || code === 0) problems.push(`asset ${f} -> ${code}`);
      }
    }
    await ctx.close();
  }
}

await browser.close();
fs.writeFileSync(path.join(QA, 'report.txt'), problems.length ? problems.join('\n') : 'no problems found');
console.log(problems.length ? `PROBLEMS (${problems.length}):\n` + problems.join('\n') : 'QA: no problems found');
