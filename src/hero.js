// Point-cloud portrait hero. Three.js r170, one Points object with a custom shader.
// The point cloud is produced offline by tools/make_pointcloud.py (segmentation + Depth Anything V2).
import * as THREE from 'three';

const VERT = /* glsl */ `
  attribute float aSeed;
  uniform float uTime;
  uniform float uScatter;
  uniform float uReveal;
  uniform float uSize;
  uniform float uPixelRatio;
  varying vec3 vColor;
  varying float vShimmer;
  varying float vSeed;
  varying float vScatter;
  varying float vFacing;

  float hash(float n) { return fract(sin(n) * 43758.5453123); }

  void main() {
    vec3 p = position;
    float t = uTime;
    // gentle breathing of the whole cloud
    p.x += 0.0035 * sin(t * 0.9 + aSeed * 6.2831);
    p.y += 0.0035 * cos(t * 0.7 + aSeed * 12.566);
    p.z += 0.0060 * sin(t * 0.5 + aSeed * 3.0);

    // scatter: every point flies away along its own direction, faster for some
    float h1 = hash(aSeed * 3.17), h2 = hash(aSeed * 7.71), h3 = hash(aSeed * 11.3);
    vec3 dir = normalize(vec3(p.x * 0.9, p.y * 0.5 + 0.25, 0.9) + (vec3(h1, h2, h3) - 0.5) * 1.8);
    float s = uScatter * (0.55 + 0.9 * h2);
    s = s * s * (3.0 - 2.0 * s) * uScatter; // ease
    p += dir * s * 2.6;
    p.y += s * 0.35;
    p.x += sin(t * 0.8 + aSeed * 20.0) * s * 0.15;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    // outward normal in view space -> back-face culling and soft shading of the solid head
    vec3 nv = normalize(normalMatrix * normal);
    vFacing = dot(nv, normalize(-mv.xyz));

    vShimmer = 0.9 + 0.22 * sin(t * 1.7 + aSeed * 41.0) * (0.3 + 0.7 * h3);
    vSeed = aSeed;
    vScatter = uScatter;
    vColor = color;

    float size = uSize * (0.85 + 0.5 * h1) * (1.0 + s * 1.2);
    gl_PointSize = size * uPixelRatio * (3.2 / -mv.z);
  }
`;

const FRAG = /* glsl */ `
  uniform float uReveal;
  varying vec3 vColor;
  varying float vShimmer;
  varying float vSeed;
  varying float vScatter;
  varying float vFacing;

  float hash(float n) { return fract(sin(n) * 43758.5453123); }

  void main() {
    vec2 c = gl_PointCoord - 0.5;
    float d = dot(c, c);
    if (d > 0.25) discard;
    if (vScatter < 0.6 && vFacing < -0.06) discard;   // points on the far side of the head
    // dithered reveal / fade, which keeps the depth buffer honest (no sorting needed)
    float gate = hash(vSeed * 1.73);
    if (gate > uReveal) discard;
    float fade = 1.0 - smoothstep(0.35, 1.0, vScatter);
    if (hash(vSeed * 5.31) > fade) discard;
    float shade = mix(0.66, 1.0, sqrt(clamp(vFacing, 0.0, 1.0)));
    vec3 col = vColor * vShimmer * mix(shade, 1.0, vScatter);
    // tiny warm glint on scattered particles
    col = mix(col, vec3(1.0, 0.86, 0.55), vScatter * 0.35 * hash(vSeed * 9.9));
    gl_FragColor = vec4(col, 1.0);
  }
`;

function hasWebGL() {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch (_) {
    return false;
  }
}

function parseCloud(buf) {
  const dv = new DataView(buf);
  const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
  if (magic !== 'ABP2') throw new Error('bad point cloud file');
  const count = dv.getUint32(4, true);
  const frontCount = dv.getUint32(8, true);
  const posOffset = 16;
  const colOffset = posOffset + count * 6;
  const nrmOffset = colOffset + count * 3;
  const i16 = new Int16Array(buf.slice(posOffset, colOffset));
  const rgb = new Uint8Array(buf.slice(colOffset, nrmOffset));
  const nrm = new Int8Array(buf.slice(nrmOffset, nrmOffset + count * 3));
  const pos = new Float32Array(count * 3);
  for (let i = 0; i < count * 3; i++) pos[i] = i16[i] / 32767;
  return { count, frontCount, pos, rgb, nrm };
}

export async function initHero({ canvas, wrap, fallbackImg, onReady, onNoWebGL }) {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const showFallback = () => { fallbackImg.src = fallbackImg.dataset.src; fallbackImg.hidden = false; };
  if (!hasWebGL()) {
    showFallback();
    canvas.remove();
    onNoWebGL?.();
    return null;
  }

  const small = innerWidth < 760;
  const lowEnd = (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory && navigator.deviceMemory <= 4);
  const useLOD = small || lowEnd;
  const url = useLOD ? '/assets/cloud/portrait_3d_lo.bin' : '/assets/cloud/portrait_3d_hi.bin';

  let data;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(res.status);
    data = parseCloud(await res.arrayBuffer());
  } catch (e) {
    console.warn('point cloud unavailable', e);
    showFallback();
    canvas.remove();
    onNoWebGL?.();
    return null;
  }

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: 'high-performance' });
  const maxDPR = useLOD ? 1.5 : 2;
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, maxDPR));
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 20);
  const group = new THREE.Group();
  scene.add(group);

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(data.pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(data.rgb, 3, true));
  geo.setAttribute('normal', new THREE.BufferAttribute(data.nrm, 3, true));
  const seeds = new Float32Array(data.count);
  for (let i = 0; i < data.count; i++) seeds[i] = (i * 0.618033988749895) % 1;
  geo.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1));
  geo.computeBoundingSphere();

  const uniforms = {
    uTime: { value: 0 },
    uScatter: { value: 1 },
    uReveal: { value: 0 },
    uSize: { value: 2.4 },
    uPixelRatio: { value: renderer.getPixelRatio() },
  };
  const mat = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: VERT,
    fragmentShader: FRAG,
    vertexColors: true,
    transparent: false,
    depthWrite: true,
    depthTest: true,
  });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  group.add(points);

  // ------------------------------------------------------------ layout
  function layout() {
    const w = wrap.clientWidth, h = wrap.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // fit the 2-unit-wide bust: height-fit on landscape, width-fit on portrait
    const vfov = THREE.MathUtils.degToRad(camera.fov);
    const distH = 1.42 / Math.tan(vfov / 2);
    const distW = (1.12 / camera.aspect) / Math.tan(vfov / 2);
    const dist = Math.max(distH, distW);
    camera.position.set(0, 0, dist);
    // raise the bust so the name sits in its dissolving lower edge; more on tall screens
    const portrait = camera.aspect < 0.9;
    group.position.y = portrait ? 0.62 : 0.32;
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    uniforms.uPixelRatio.value = renderer.getPixelRatio();
    // point size from coverage: the bust (2 x 2.2 units, ~55% filled) should be tiled by its points
    const dpr = renderer.getPixelRatio();
    const pxPerUnit = (h * dpr) / (2 * dist * Math.tan(vfov / 2));
    const bustArea = 2 * pxPerUnit * 2.2 * pxPerUnit * 0.55;
    const wanted = 1.3 * Math.sqrt(bustArea / (data.frontCount * 0.6)); // device px per point (front sheet, arc-length sampled)
    uniforms.uSize.value = THREE.MathUtils.clamp(wanted / (dpr * (3.2 / dist) * 1.1), 1.2, 7);
  }
  layout();
  new ResizeObserver(layout).observe(wrap);

  // ------------------------------------------------------------ interaction
  const target = { x: 0, y: 0 };
  const cur = { x: 0, y: 0 };
  let lastInput = performance.now();
  const MAX_Y = THREE.MathUtils.degToRad(50), MAX_X = THREE.MathUtils.degToRad(12), MAX_TOTAL = THREE.MathUtils.degToRad(62);
  let dragYaw = 0, dragging = false, dragStartX = 0, dragStartYaw = 0;
  function onPointer(x, y) {
    target.x = (x / innerWidth) * 2 - 1;
    target.y = (y / innerHeight) * 2 - 1;
    lastInput = performance.now();
    if (reduced) requestRender();
  }
  addEventListener('pointermove', (e) => {
    if (e.pointerType === 'touch') return;
    onPointer(e.clientX, e.clientY);
    if (dragging) dragYaw = dragStartYaw + ((e.clientX - dragStartX) / innerWidth) * 2.4;
  }, { passive: true });
  wrap.addEventListener('pointerdown', (e) => { if (e.pointerType === 'touch') return; dragging = true; dragStartX = e.clientX; dragStartYaw = dragYaw; });
  addEventListener('pointerup', () => { dragging = false; });
  // touch: a horizontal swipe on the hero turns the head; vertical scrolling is untouched (touch-action: pan-y)
  wrap.addEventListener('touchstart', (e) => { const t = e.touches[0]; if (t) { dragStartX = t.clientX; dragStartYaw = dragYaw; lastInput = performance.now(); } }, { passive: true });
  wrap.addEventListener('touchmove', (e) => {
    const t = e.touches[0];
    if (!t) return;
    dragYaw = dragStartYaw + ((t.clientX - dragStartX) / innerWidth) * 2.4;
    lastInput = performance.now();
    if (reduced) requestRender();
  }, { passive: true });

  let scrollScatter = 0;
  function onScroll() {
    const h = innerHeight * 0.8;
    scrollScatter = THREE.MathUtils.clamp(scrollY / h, 0, 1);
    if (reduced) requestRender();
  }
  addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // ------------------------------------------------------------ loop
  const t0 = performance.now();
  let introScatter = 1;
  let visible = true;
  let running = false;
  let pendingRender = false;
  const clock = new THREE.Clock();

  function frame(now) {
    const t = (now - t0) / 1000;
    const dt = Math.min(clock.getDelta(), 0.05);
    // intro: fly in from scattered, reveal with dither
    introScatter = reduced ? 0 : Math.max(0, 1 - THREE.MathUtils.smoothstep(t, 0.15, 2.3));
    uniforms.uReveal.value = reduced ? 1 : Math.min(1, t / 1.4);
    const scatterTarget = Math.max(introScatter, scrollScatter);
    uniforms.uScatter.value += (scatterTarget - uniforms.uScatter.value) * Math.min(1, dt * 6);
    uniforms.uTime.value = t;

    // slow auto-sway when the pointer has been still for a while; the drag offset eases back
    const idle = reduced ? 0 : THREE.MathUtils.clamp((now - lastInput - 2000) / 3000, 0, 1);
    const swayY = Math.sin(t * 0.26) * 0.35 * idle;
    const swayX = Math.cos(t * 0.19) * 0.05 * idle;
    if (!dragging) dragYaw *= Math.max(0, 1 - dt * 0.35);
    const ty = THREE.MathUtils.clamp(THREE.MathUtils.clamp(target.x * MAX_Y, -MAX_Y, MAX_Y) * (1 - idle) + swayY + dragYaw, -MAX_TOTAL, MAX_TOTAL);
    const tx = THREE.MathUtils.clamp(target.y * MAX_X, -MAX_X, MAX_X) * (1 - idle * 0.6) + swayX;
    cur.x += (tx - cur.x) * Math.min(1, dt * 3.2);
    cur.y += (ty - cur.y) * Math.min(1, dt * 3.2);
    group.rotation.set(cur.x, cur.y, 0);
    group.position.y += Math.sin(t * 0.6) * 0.0004 * (reduced ? 0 : 1);

    renderer.render(scene, camera);
    if (t > 2.4 && !heroReady) { heroReady = true; onReady?.(); }
  }
  let heroReady = false;

  function loop(now) {
    if (!running) return;
    frame(now);
    requestAnimationFrame(loop);
  }
  function start() { if (running) return; running = true; clock.getDelta(); requestAnimationFrame(loop); }
  function stop() { running = false; }
  function requestRender() {
    if (pendingRender) return;
    pendingRender = true;
    requestAnimationFrame((now) => { pendingRender = false; frame(now); });
  }

  if (reduced) {
    // static portrait, re-rendered only on input
    uniforms.uScatter.value = 0;
    uniforms.uReveal.value = 1;
    requestRender();
    heroReady = true;
    onReady?.();
  } else {
    const io = new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
      if (visible && !document.hidden) start(); else stop();
    }, { threshold: 0.01 });
    io.observe(wrap);
    document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); else if (visible) start(); });
    start();
  }

  return {
    renderer, scene, camera, uniforms,
    setScatter(v) { scrollScatter = v; requestRender(); },
    snapshot() { frame(performance.now()); return renderer.domElement.toDataURL('image/png'); },
  };
}
