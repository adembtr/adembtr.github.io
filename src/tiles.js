// Decorative SVG tiles for projects that have no screenshots. They are illustrations, not screenshots,
// and the UI labels them as such.
const esc = (s) => String(s);

function frame(accent, inner) {
  return `<svg viewBox="0 0 640 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true" focusable="false">
  <defs>
    <linearGradient id="g${accent.slice(1)}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#141a2b"/><stop offset="1" stop-color="#0b0e18"/>
    </linearGradient>
    <radialGradient id="r${accent.slice(1)}" cx="0.8" cy="0.1" r="0.9">
      <stop offset="0" stop-color="${accent}" stop-opacity="0.28"/><stop offset="1" stop-color="${accent}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="p${accent.slice(1)}" width="24" height="24" patternUnits="userSpaceOnUse">
      <circle cx="1" cy="1" r="1" fill="rgba(255,255,255,0.10)"/>
    </pattern>
  </defs>
  <rect width="640" height="360" fill="url(#g${accent.slice(1)})"/>
  <rect width="640" height="360" fill="url(#p${accent.slice(1)})"/>
  <rect width="640" height="360" fill="url(#r${accent.slice(1)})"/>
  ${inner}
</svg>`;
}

export function tileSVG(kind, accent) {
  const a = esc(accent);
  const stroke = `stroke="${a}" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"`;
  const faint = `stroke="rgba(255,255,255,0.35)" fill="none" stroke-width="2" stroke-linecap="round"`;
  switch (kind) {
    case 'voice':
      return frame(a, `
        <circle cx="120" cy="180" r="10" fill="${a}"/>
        <path d="M150 150 a40 40 0 0 1 0 60 M175 125 a75 75 0 0 1 0 110 M200 100 a110 110 0 0 1 0 160" ${stroke} opacity="0.9"/>
        <path d="M330 180 h40" ${faint}/><path d="M362 172 l8 8 -8 8" ${faint}/>
        <rect x="400" y="80" width="150" height="86" rx="8" ${faint}/>
        <rect x="400" y="190" width="150" height="86" rx="8" ${faint}/>
        <rect x="440" y="120" width="70" height="8" rx="4" fill="${a}" opacity="0.7"/>
        <rect x="440" y="230" width="90" height="8" rx="4" fill="${a}" opacity="0.5"/>
        <path d="M250 136 h50 v88 h-50 z" ${faint}/><path d="M262 160 h26 M262 180 h26 M262 200 h16" ${faint}/>
        <text x="60" y="320" font-family="JetBrains Mono, monospace" font-size="14" fill="rgba(255,255,255,0.55)">voice → plan → act</text>`);
    case 'math':
      return frame(a, `
        <g font-family="Fraunces, Georgia, serif" font-size="64" fill="rgba(255,255,255,0.92)">
          <text x="70" y="200">7 + 5</text><text x="330" y="200" fill="${a}">= 12</text>
        </g>
        ${[0, 1, 2, 3, 4].map((i) => `<path d="M${90 + i * 48} 230 C ${120 + i * 40} 290, ${300 + i * 20} 250, ${370 + i * 36} 230" ${faint} opacity="${0.25 + i * 0.1}"/>`).join('')}
        <text x="60" y="320" font-family="JetBrains Mono, monospace" font-size="14" fill="rgba(255,255,255,0.55)">0.84M params · scratchpad · curriculum</text>`);
    case 'docs':
      return frame(a, `
        <rect x="90" y="70" width="170" height="220" rx="8" ${faint}/>
        <rect x="120" y="100" width="170" height="220" rx="8" ${faint} fill="#0e1220"/>
        <rect x="150" y="130" width="170" height="220" rx="8" fill="#141a2b" stroke="rgba(255,255,255,0.5)" stroke-width="2"/>
        ${[0, 1, 2, 3, 4, 5, 6].map((i) => `<rect x="170" y="${155 + i * 24}" width="${i === 3 ? 130 : 110 - (i % 3) * 14}" height="7" rx="3.5" fill="${i === 3 ? a : 'rgba(255,255,255,0.3)'}"/>`).join('')}
        <path d="M340 230 h60" ${faint}/><path d="M392 222 l8 8 -8 8" ${faint}/>
        <rect x="420" y="190" width="150" height="80" rx="10" ${stroke}/>
        <text x="440" y="226" font-family="JetBrains Mono, monospace" font-size="14" fill="rgba(255,255,255,0.8)">answer</text>
        <text x="440" y="252" font-family="JetBrains Mono, monospace" font-size="12" fill="${a}">source · p. 12</text>`);
    case 'mic':
      return frame(a, `
        <rect x="80" y="90" width="90" height="180" rx="16" ${faint}/>
        <circle cx="125" cy="245" r="8" fill="${a}"/>
        ${Array.from({ length: 22 }, (_, i) => {
          const h = 10 + 60 * Math.abs(Math.sin(i * 0.9)) * (i % 5 === 0 ? 1 : 0.65);
          return `<rect x="${210 + i * 12}" y="${180 - h / 2}" width="5" height="${h}" rx="2.5" fill="${a}" opacity="${0.5 + 0.5 * Math.abs(Math.sin(i))}"/>`;
        }).join('')}
        <rect x="490" y="110" width="110" height="80" rx="6" ${faint}/>
        <path d="M520 215 h50 M545 190 v25" ${faint}/>
        <text x="505" y="155" font-family="JetBrains Mono, monospace" font-size="12" fill="rgba(255,255,255,0.8)">yazıyor_</text>`);
    case 'hand':
      return frame(a, `
        ${[0, 1, 2, 3].map((i) => {
          const h = [150, 190, 180, 140][i];
          const x = 150 + i * 90;
          return `<rect x="${x}" y="${300 - h}" width="48" height="${h}" rx="24" ${faint} fill="rgba(255,255,255,0.03)"/>
                  <circle cx="${x + 24}" cy="300" r="14" fill="${a}" opacity="0.9"/>
                  <path d="M${x + 24} ${300 - h + 28} v${h * 0.35}" ${stroke} opacity="0.7"/>`;
        }).join('')}
        <path d="M130 330 h380" ${faint}/>
        <text x="60" y="60" font-family="JetBrains Mono, monospace" font-size="14" fill="rgba(255,255,255,0.55)">4 × servo · interpolated poses</text>`);
    case 'db':
    default:
      return frame(a, `
        <g ${faint}>
          <rect x="70" y="80" width="170" height="90" rx="8"/><rect x="400" y="80" width="170" height="90" rx="8"/><rect x="235" y="220" width="170" height="90" rx="8"/>
          <path d="M240 125 h160 M155 170 v50 h80 M485 170 v50 h-80"/>
        </g>
        ${[[80, 100], [80, 124], [80, 148], [410, 100], [410, 124], [410, 148], [245, 240], [245, 264], [245, 288]].map(([x, y], i) => `<rect x="${x + 10}" y="${y}" width="${90 - (i % 3) * 20}" height="7" rx="3.5" fill="${i % 3 === 0 ? a : 'rgba(255,255,255,0.3)'}"/>`).join('')}
        <text x="70" y="340" font-family="JetBrains Mono, monospace" font-size="14" fill="rgba(255,255,255,0.55)">books · members · loans · triggers</text>`);
  }
}
