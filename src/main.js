import './style.css';
import { UI, LINKS, PROJECTS, EXPERIENCE, EDUCATION, HONORS, SKILLS } from './content.js';
import { tileSVG } from './tiles.js';
import { initHero } from './hero.js';

// ------------------------------------------------------------------ i18n
let lang = 'en';
try {
  const stored = localStorage.getItem('lang');
  if (stored === 'tr' || stored === 'en') lang = stored;
} catch (_) { /* storage may be unavailable */ }

const t = (obj) => (obj && typeof obj === 'object' ? obj[lang] ?? obj.en ?? '' : obj ?? '');
const ui = (key) => UI[lang][key] ?? UI.en[key] ?? key;

function applyStatic() {
  document.documentElement.lang = lang;
  document.title = ui('meta.title');
  document.querySelector('meta[name="description"]')?.setAttribute('content', ui('meta.description'));
  document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = ui(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-attr]').forEach((el) => {
    el.dataset.i18nAttr.split(',').forEach((pair) => {
      const [attr, key] = pair.split(':').map((s) => s.trim());
      if (attr && key) el.setAttribute(attr, ui(key));
    });
  });
}

// ------------------------------------------------------------------ helpers
const $ = (sel, root = document) => root.querySelector(sel);
const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
};

const ICON_ARROW = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9"/></svg>';
const ICON_CLOSE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
const ICON_GH = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2.17c-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.19 1.76 1.19 1.03 1.76 2.7 1.25 3.35.96.1-.75.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.8 1.19 1.83 1.19 3.09 0 4.42-2.69 5.39-5.26 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z"/></svg>';

function videoEl(src, poster, { controls = false, className = '' } = {}) {
  const v = h('video', {
    class: className, muted: true, loop: true, playsinline: true, preload: 'none', poster,
    controls: controls || null, 'aria-label': null,
  });
  v.muted = true;
  v.dataset.src = src;
  return v;
}
function loadVideo(v) {
  if (v.dataset.loaded) return;
  v.dataset.loaded = '1';
  v.append(
    h('source', { src: `${v.dataset.src}.webm`, type: 'video/webm' }),
    h('source', { src: `${v.dataset.src}.mp4`, type: 'video/mp4' }),
  );
  v.load();
}
const videoIO = new IntersectionObserver((entries) => {
  for (const e of entries) {
    const v = e.target;
    if (e.isIntersecting) { loadVideo(v); v.play().catch(() => {}); }
    else v.pause();
  }
}, { rootMargin: '200px 0px' });

function coverNode(p, forDialog = false) {
  const c = p.cover;
  if (c.type === 'video') {
    const v = videoEl(c.src, c.poster, { className: 'cover-video' });
    videoIO.observe(v);
    return v;
  }
  if (c.type === 'image') {
    return h('img', { src: c.src, alt: '', loading: 'lazy', width: 640, height: 360 });
  }
  return h('div', { class: 'tile', html: tileSVG(c.tile, p.accent) });
}

// ------------------------------------------------------------------ projects grid
// display order and which cards take half the row (keeps the 12-column grid gap-free)
const ORDER = ['nuron', 'dotnote', 'ghost-cursor', 'arc-agi3', 'mathai', 'rag-pdf-qa', 'whisper-phone', 'servo-hand', 'library'];
const SPAN6 = new Set(['nuron', 'dotnote', 'ghost-cursor', 'arc-agi3', 'servo-hand', 'library']);
const ORDERED = [...PROJECTS].sort((a, b) => ORDER.indexOf(a.id) - ORDER.indexOf(b.id));

function renderProjects() {
  const grid = $('#projectGrid');
  grid.replaceChildren();
  ORDERED.forEach((p, i) => {
    const titleBtn = h('button', { type: 'button', class: 'card-title', 'aria-haspopup': 'dialog' }, t(p.title));
    const card = h('article', {
      class: `project-card reveal${p.featured ? ' featured' : ''}${SPAN6.has(p.id) ? ' span-6' : ''}`,
      style: `--pc-accent:${p.accent}`,
      'aria-label': t(p.title),
    },
      h('div', { class: 'cover', 'aria-hidden': 'true' },
        coverNode(p),
        h('span', { class: 'badge' }, p.cover.type === 'video' ? ui('projects.video') : p.cover.type === 'tile' ? ui('projects.illustration') : t(p.period)),
      ),
      h('div', { class: 'body' },
        h('h3', {}, titleBtn),
        h('p', { class: 'sub' }, t(p.subtitle)),
        h('div', { class: 'meta' }, p.stack.slice(0, p.featured ? 5 : 3).map((s) => h('span', { class: 'tag' }, s))),
      ),
      h('span', { class: 'open', 'aria-hidden': 'true', html: ICON_ARROW }),
    );
    const open = () => openProject(p, titleBtn);
    titleBtn.addEventListener('click', (e) => { e.stopPropagation(); open(); });
    card.addEventListener('click', open);
    card.style.transitionDelay = `${(i % 3) * 0.06}s`;
    grid.append(card);
  });
  observeReveals();
}

// ------------------------------------------------------------------ dialog
const dialog = $('#projectDialog');
const dialogInner = $('#dialogInner');
let lastFocus = null;

function mediaMain(p, m) {
  if (m.type === 'video') {
    const v = videoEl(m.src, m.poster, { controls: true });
    v.setAttribute('aria-label', t(m.alt));
    loadVideo(v);
    v.play().catch(() => {});
    return v;
  }
  if (m.type === 'image') return h('img', { src: m.src, alt: t(m.alt) });
  return h('div', { class: 'tile', html: tileSVG(m.tile, p.accent), role: 'img', 'aria-label': t(m.alt) });
}

function openProject(p, trigger) {
  lastFocus = trigger;
  dialog.style.setProperty('--pc-accent', p.accent);
  dialogInner.replaceChildren();

  const main = h('div', { class: 'dlg-media-main' });
  const caption = h('p', { class: 'dlg-caption' });
  const thumbs = h('div', { class: 'dlg-gallery', role: 'list' });
  let active = 0;
  function show(i) {
    active = i;
    const m = p.media[i];
    main.replaceChildren(mediaMain(p, m));
    caption.textContent = `${m.type === 'video' ? ui('projects.video') : m.type === 'tile' ? ui('projects.illustration') : ''}${m.type === 'image' ? '' : ' · '}${t(m.alt)}`;
    thumbs.querySelectorAll('.dlg-thumb').forEach((b, j) => b.classList.toggle('active', j === i));
  }
  if (p.media.length > 1) {
    p.media.forEach((m, i) => {
      const thumb = h('button', { type: 'button', class: 'dlg-thumb', role: 'listitem', 'aria-label': t(m.alt), onclick: () => show(i) });
      if (m.type === 'tile') thumb.innerHTML = tileSVG(m.tile, p.accent);
      else thumb.append(h('img', { src: m.poster || m.src, alt: '', loading: 'lazy' }));
      if (m.type === 'video') thumb.append(h('span', { class: 'play', 'aria-hidden': 'true' }, '▶'));
      thumbs.append(thumb);
    });
  }

  const links = h('div', { class: 'dlg-links' }, p.links.map((l) =>
    h('a', { class: 'btn btn-ghost btn-sm', href: l.url, target: '_blank', rel: 'noopener' },
      l.kind === 'code' ? h('span', { html: ICON_GH }) : null,
      l.label || (l.kind === 'code' ? ui('projects.code') : ui('projects.site')),
    )));

  dialogInner.append(
    h('div', { class: 'dlg-head' },
      h('div', {},
        h('h3', { id: 'dlgTitle' }, t(p.title)),
        h('p', { class: 'sub' }, t(p.subtitle)),
      ),
      h('button', { type: 'button', class: 'dlg-close', 'aria-label': ui('projects.close'), html: ICON_CLOSE, onclick: () => dialog.close() }),
    ),
    h('div', { class: 'dlg-body' },
      h('div', {}, main, caption),
      p.media.length > 1 ? thumbs : null,
      h('div', { class: 'dlg-cols' },
        h('div', {},
          h('p', { class: 'lead', style: 'margin-bottom:16px' }, t(p.summary)),
          h('ul', { class: 'dlg-bullets' }, t(p.bullets).map((b) => h('li', {}, b))),
        ),
        h('div', { class: 'dlg-facts' },
          h('div', { class: 'dlg-fact' }, h('span', { class: 'k' }, ui('projects.role')), t(p.role)),
          h('div', { class: 'dlg-fact' }, h('span', { class: 'k' }, ui('projects.period')), t(p.period)),
          h('div', { class: 'dlg-fact' }, h('span', { class: 'k' }, ui('projects.stack')), h('div', { class: 'meta', style: 'display:flex;flex-wrap:wrap;gap:6px;margin-top:4px' }, p.stack.map((s) => h('span', { class: 'tag' }, s)))),
          p.links.length ? h('div', { class: 'dlg-fact' }, h('span', { class: 'k' }, 'Links'), links) : null,
        ),
      ),
    ),
  );
  show(0);
  document.body.classList.add('no-scroll');
  dialog.showModal();
  dialogInner.scrollTop = 0;
  $('.dlg-close', dialog)?.focus();
}
dialog.addEventListener('close', () => {
  document.body.classList.remove('no-scroll');
  dialogInner.querySelectorAll('video').forEach((v) => v.pause());
  dialogInner.replaceChildren();
  lastFocus?.focus();
});
dialog.addEventListener('click', (e) => {
  const r = dialogInner.getBoundingClientRect();
  const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
  if (!inside) dialog.close();
});

// ------------------------------------------------------------------ lists
function renderTimeline(sel, items) {
  const ol = $(sel);
  ol.replaceChildren(...items.map((it) =>
    h('li', { class: 'tl-item reveal' },
      h('p', { class: 'tl-when' }, t(it.when)),
      h('h3', {}, t(it.title)),
      h('p', { class: 'tl-org' }, t(it.org)),
      t(it.text) ? h('p', { class: 'tl-text' }, t(it.text)) : null,
    )));
}
function renderSkills() {
  const root = $('#skillGroups');
  root.replaceChildren(...SKILLS.map((g) =>
    h('div', { class: 'skill-group reveal' },
      h('h3', {}, t(g.group)),
      h('ul', {}, g.items.map((s) => h('li', {}, typeof s === 'string' ? s : t(s)))),
    )));
}

// ------------------------------------------------------------------ reveal on scroll
const revealIO = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add('in'); revealIO.unobserve(e.target); }
}, { threshold: 0.12, rootMargin: '0px 0px -5% 0px' });
function observeReveals() {
  document.querySelectorAll('.reveal:not(.in)').forEach((el) => revealIO.observe(el));
}

// ------------------------------------------------------------------ render all
function renderAll() {
  applyStatic();
  renderProjects();
  renderTimeline('#expList', EXPERIENCE);
  renderTimeline('#eduList', EDUCATION);
  renderTimeline('#honorList', HONORS);
  renderSkills();
  observeReveals();
}
renderAll();

$('#langToggle').addEventListener('click', () => {
  lang = lang === 'en' ? 'tr' : 'en';
  try { localStorage.setItem('lang', lang); } catch (_) { /* ignore */ }
  const wasOpen = dialog.open;
  if (wasOpen) dialog.close();
  renderAll();
  document.querySelectorAll('.reveal').forEach((el) => el.classList.add('in'));
});

// ------------------------------------------------------------------ nav state
const nav = $('#siteNav');
const sections = ['about', 'projects', 'experience', 'contact'].map((id) => document.getElementById(id));
const navLinks = [...nav.querySelectorAll('nav a')];
function onScrollNav() {
  nav.classList.toggle('scrolled', scrollY > 24);
  let current = null;
  for (const s of sections) if (s && s.getBoundingClientRect().top <= innerHeight * 0.4) current = s.id;
  navLinks.forEach((a) => a.classList.toggle('active', a.getAttribute('href') === `#${current}`));
}
addEventListener('scroll', onScrollNav, { passive: true });
onScrollNav();
$('#year').textContent = String(new Date().getFullYear());

// ------------------------------------------------------------------ hero
// capture modes used by tools/qa.mjs to render the OG image and the static fallback
if (location.search.includes('og=1')) document.documentElement.classList.add('og');
if (location.search.includes('cloudshot=1')) document.documentElement.classList.add('cloudshot');
const heroCanvas = $('#heroCanvas');
const heroWrap = $('#heroCanvasWrap');
const heroFallback = $('#heroFallback');
const heroCopy = $('#heroCopy');
window.__hero = { ready: false };
initHero({
  canvas: heroCanvas,
  wrap: heroWrap,
  fallbackImg: heroFallback,
  onReady: () => { window.__hero.ready = true; },
  onNoWebGL: () => { $('#heroNoWebgl').hidden = false; $('#heroHint').hidden = true; window.__hero.ready = true; window.__hero.fallback = true; },
}).then((api) => { window.__hero.api = api; });

// fade the hero copy as the cloud disperses
addEventListener('scroll', () => {
  const k = Math.min(1, scrollY / (innerHeight * 0.6));
  heroCopy.style.opacity = String(1 - k * 0.9);
  heroCopy.style.transform = `translateY(${k * -24}px)`;
}, { passive: true });
