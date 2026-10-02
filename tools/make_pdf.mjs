// HTML -> PDF for the downloadable CV (Playwright, Chromium).
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, '../public/assets/pdf/Adem_Batur_CV.pdf');
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto('file://' + path.join(here, 'cv.html'), { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready);
await page.pdf({ path: out, format: 'A4', printBackground: true, preferCSSPageSize: true });
// how many pages did we get?
const pages = await page.evaluate(() => Math.ceil(document.documentElement.scrollHeight / (297 * 3.7795)));
console.log('pdf written', out, 'approx pages:', pages, 'height px:', await page.evaluate(() => document.documentElement.scrollHeight));
await browser.close();
