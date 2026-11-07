// Springfield commuting flows: a space-time cube of LODES flows, 2002-2024.
// Style and structure follow the European Spatiotemporal Geography atlas (three.js, terrain slice + time stack).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';

const V = 1;
const TEX_SCALE = 2;
const MESH_STEP = 2;
const NSEG = 14;                       // segments per arc
const STACK_TOP_N = 300;               // flows per ghost year layer (largest first)
const DIV = { metro: 1, nation: 20 };  // km per world unit
const RELIEF_K = { metro: 1, nation: 4 };
const SEGCOL = { S000: 2, SE01: 3, SE02: 4, SE03: 5, SI01: 6, SI02: 7, SI03: 8, SA01: 9, SA02: 10, SA03: 11 };
const NF = 12;                          // numbers per flow record
const PERIODS = [[2007, 2009, 'Great Recession'], [2010, 2010, 'Federal jobs enter JT00'], [2012, 2012, 'LODES age frame changes'],
  [2020, 2021, 'COVID-19 pandemic']];
const CAT = {
  light: { w: '#2a78d6', i: '#eb6834', o: '#1baf7a', series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'] },
  dark: { w: '#3987e5', i: '#d95926', o: '#199e70', series: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'] },
};
// diverging blue <-> red with a grey midpoint: new, intensifying, persistent, declining, fading
const TREND = {
  light: ['#1c5cab', '#86b6ef', '#b9b8b2', '#f0a3a2', '#b8312f'],
  dark: ['#5598e7', '#86b6ef', '#6b6a64', '#f0a3a2', '#e66767'],
  labels: ['New', 'Intensifying', 'Persistent', 'Declining', 'Fading'],
};
const SEQ = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'];

const $ = (id) => document.getElementById(id);
const fmt = (v) => v == null || Number.isNaN(v) ? '–' : Math.round(v).toLocaleString('en-US');
const pct = (v, d = 1) => v == null || Number.isNaN(v) ? '–' : (100 * v).toFixed(d) + '%';

const state = {
  scale: 'metro', view: 'cube', jt: 'JT02', dir: new Set(['w', 'i', 'o']), colour: 'dir', seg: 'S000', minFlow: 10,
  surface: 'community', relief: 12, stack: true, labels: true, theme: 'light', year: 2024, sel: null, playing: false,
};

let app, base, flows = {}, renderer, scene, camera, controls, raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
let world, slice, terrain, terrainTex, texCanvas, texCtx, reliefCanvas, heights, gridW, gridH, meta, layers = [], axisGroup;
const labelEls = [];
const lineMats = [];

// ---------------------------------------------------------------- loading
async function getJson(u) { const r = await fetch(u); if (!r.ok) throw new Error(u); return r.json(); }
function loadImage(u) { return new Promise((ok, no) => { const im = new Image(); im.onload = () => ok(im); im.onerror = no; im.src = u; }); }

async function init() {
  const saved = (() => { try { return localStorage.getItem('sf-theme'); } catch { return null; } })();
  state.theme = saved || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.dataset.theme = state.theme;
  [app, base, flows.JT02] = await Promise.all([getJson(`data/app.json?v=${V}`), getJson(`data/basemap.json?v=${V}`), getJson(`data/flows_JT02.json?v=${V}`)]);
  base.img = {};
  [base.img.metro, base.img.nation] = await Promise.all([loadImage(`data/terrain_metro.png?v=${V}`), loadImage(`data/terrain_nation.png?v=${V}`)]);
  app.nodeIdx = Object.fromEntries(app.nodes.map((n, i) => [n.id, i]));
  state.year = app.years[app.years.length - 1];
  readHash();
  if (state.jt === 'JT00') await ensureFlows('JT00');
  buildRenderer();
  buildUI();
  buildScale();
  renderCharts();
  renderMethods();
  $('loading').classList.add('done');
  animate();
}

async function ensureFlows(jt) {
  if (!flows[jt]) { $('loading').classList.remove('done'); flows[jt] = await getJson(`data/flows_${jt}.json?v=${V}`); $('loading').classList.add('done'); }
}

// deep links: #scale=nation&view=map&year=2010&jt=JT00&surface=density&colour=trend&tract=29077002200
function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  for (const k of ['scale', 'view', 'jt', 'surface', 'colour', 'seg']) if (h.get(k)) state[k] = h.get(k);
  if (h.get('year')) state.year = +h.get('year');
  if (h.get('tract') && app.tracts[h.get('tract')]) state.sel = h.get('tract');
  if (h.get('stack') === '0') state.stack = false;
}
function writeHash() {
  const h = new URLSearchParams({ scale: state.scale, view: state.view, year: state.year, jt: state.jt, surface: state.surface, colour: state.colour });
  if (state.sel) h.set('tract', state.sel);
  history.replaceState(null, '', '#' + h.toString());
}

// ---------------------------------------------------------------- renderer
function buildRenderer() {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight);
  $('scene').appendChild(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(38, innerWidth / innerHeight, 1, 20000);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8576, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.5);
  sun.position.set(-1, 2, 1);
  scene.add(sun);
  addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
    lineMats.forEach((m) => m.resolution.set(innerWidth, innerHeight));
  });
  renderer.domElement.addEventListener('pointermove', onHover);
  renderer.domElement.addEventListener('pointerleave', () => { $('tooltip').hidden = true; });
  let down;
  renderer.domElement.addEventListener('pointerdown', (e) => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener('pointerup', (e) => { if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 5) onClick(e); });
}

// ---------------------------------------------------------------- geometry helpers
const sc = () => base.meta[state.scale];
const div = () => DIV[state.scale];
function frame() { const [x0, y0, x1, y1] = sc().extent; return { x0: x0 / div(), x1: x1 / div(), z0: -y1 / div(), z1: -y0 / div() }; }
function H() { const f = frame(); return 0.8 * Math.max(f.x1 - f.x0, f.z1 - f.z0); }
function yOf(year) { return state.view === 'cube' && state.stack ? (year - app.years[0]) / (app.years.length - 1) * H() : 0; }
function nodeXY(i) {
  const n = app.nodes[i]; const p = state.scale === 'metro' ? n.m : n.n;
  if (!p) return null;
  return [p[0] / div(), -p[1] / div()];
}
function clampToFrame(x, z) {      // pull a far node onto the frame edge, along the ray from the frame centre
  const f = frame(); const cx = (f.x0 + f.x1) / 2, cz = (f.z0 + f.z1) / 2;
  const dx = x - cx, dz = z - cz;
  let t = 1;
  if (x > f.x1) t = Math.min(t, (f.x1 - cx) / dx); if (x < f.x0) t = Math.min(t, (f.x0 - cx) / dx);
  if (z > f.z1) t = Math.min(t, (f.z1 - cz) / dz); if (z < f.z0) t = Math.min(t, (f.z0 - cz) / dz);
  return [cx + dx * t, cz + dz * t, t < 1];
}
function reliefScale() { return state.relief * RELIEF_K[state.scale] / 1000 / div(); }
function heightAt(x, z) {        // world x,z -> terrain surface height (relative to slice)
  const s = sc(); const kx = (x * div() - s.extent[0]) / s.kmpx, ky = (s.extent[3] + z * div()) / s.kmpx;
  const i = Math.max(0, Math.min(gridW - 1, Math.round(kx))), j = Math.max(0, Math.min(gridH - 1, Math.round(ky)));
  return Math.max(0, heights[j * gridW + i] - s.elevMin) * reliefScale();
}
function maxTerrain() { return (sc().elevMax - sc().elevMin) * reliefScale(); }

// ---------------------------------------------------------------- scale build: terrain, texture, stack
function buildScale() {
  if (world) { scene.remove(world); world.traverse((o) => { o.geometry?.dispose?.(); }); }
  world = new THREE.Group(); scene.add(world);
  meta = sc();
  const img = base.img[state.scale];
  [gridW, gridH] = meta.size;
  const c = document.createElement('canvas'); c.width = gridW; c.height = gridH;
  const cx = c.getContext('2d'); cx.drawImage(img, 0, 0);
  const px = cx.getImageData(0, 0, gridW, gridH).data;
  heights = new Float32Array(gridW * gridH);
  const land = new Uint8Array(gridW * gridH);
  for (let k = 0; k < gridW * gridH; k++) {
    heights[k] = Math.max(meta.elevMin, px[k * 4] * 256 + px[k * 4 + 1] - base.meta.elevOffset);
    land[k] = px[k * 4 + 2] > 0 ? 1 : 0;
  }
  base.land = land;
  buildRelief();
  texCanvas = document.createElement('canvas'); texCanvas.width = gridW * TEX_SCALE; texCanvas.height = gridH * TEX_SCALE;
  texCtx = texCanvas.getContext('2d');
  terrainTex = new THREE.CanvasTexture(texCanvas);
  terrainTex.colorSpace = THREE.SRGBColorSpace;
  terrainTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  slice = new THREE.Group();
  terrain = new THREE.Mesh(buildTerrainGeometry(), new THREE.MeshLambertMaterial({ map: terrainTex }));
  slice.add(terrain);
  world.add(slice);
  axisGroup = new THREE.Group(); world.add(axisGroup);
  buildLabels();
  frameCamera();
  refresh(true);
}

function buildTerrainGeometry() {
  const f = frame();
  const nx = Math.floor((gridW - 1) / MESH_STEP), nz = Math.floor((gridH - 1) / MESH_STEP);
  const g = new THREE.PlaneGeometry(f.x1 - f.x0, f.z1 - f.z0, nx, nz);
  g.rotateX(-Math.PI / 2);
  g.translate((f.x0 + f.x1) / 2, 0, (f.z0 + f.z1) / 2);
  setTerrainHeights(g);
  return g;
}
function setTerrainHeights(g = terrain.geometry) {
  const pos = g.attributes.position;
  for (let k = 0; k < pos.count; k++) pos.setY(k, heightAt(pos.getX(k), pos.getZ(k)));
  pos.needsUpdate = true; g.computeVertexNormals(); g.computeBoundingSphere();
}

function buildRelief() {       // hypsometric tint x hillshade, computed once per scale and theme
  reliefCanvas = document.createElement('canvas'); reliefCanvas.width = gridW; reliefCanvas.height = gridH;
  const cx = reliefCanvas.getContext('2d'); const im = cx.createImageData(gridW, gridH); const d = im.data;
  const dark = state.theme === 'dark';
  const lo = meta.elevMin, hi = state.scale === 'metro' ? meta.elevMax : 3000;
  const tints = dark ? [[46, 52, 50], [58, 62, 54], [72, 70, 60], [88, 82, 70]] : [[214, 222, 204], [226, 224, 200], [222, 210, 184], [206, 190, 166]];
  const water = dark ? [24, 28, 32] : [226, 232, 234];
  const zf = state.scale === 'metro' ? 6 : 1.2;
  for (let j = 0; j < gridH; j++) for (let i = 0; i < gridW; i++) {
    const k = j * gridW + i;
    if (!base.land[k]) { d.set([...water, 255], k * 4); continue; }
    const h = heights[k];
    const dx = (heights[j * gridW + Math.min(gridW - 1, i + 1)] - heights[j * gridW + Math.max(0, i - 1)]) / (2 * meta.kmpx * 1000) * zf;
    const dy = (heights[Math.min(gridH - 1, j + 1) * gridW + i] - heights[Math.max(0, j - 1) * gridW + i]) / (2 * meta.kmpx * 1000) * zf;
    const shade = Math.max(0, Math.min(1.25, (1 + dx * 0.7 - dy * 0.7) / Math.sqrt(1 + dx * dx + dy * dy)));
    const t = Math.max(0, Math.min(0.999, (h - lo) / (hi - lo))) * (tints.length - 1);
    const a = tints[Math.floor(t)], b = tints[Math.min(tints.length - 1, Math.floor(t) + 1)], f = t - Math.floor(t);
    for (let q = 0; q < 3; q++) d[k * 4 + q] = Math.min(255, (a[q] + (b[q] - a[q]) * f) * (0.55 + 0.45 * shade));
    d[k * 4 + 3] = 255;
  }
  cx.putImageData(im, 0, 0);
}

// ---------------------------------------------------------------- slice texture (per year)
function kmToTex(x, y) { const s = meta; return [(x - s.extent[0]) / s.kmpx * TEX_SCALE, (s.extent[3] - y) / s.kmpx * TEX_SCALE]; }
function pathRings(ctx, rings) { ctx.beginPath(); for (const r of rings) { r.forEach(([x, y], k) => { const [u, v] = kmToTex(x, y); k ? ctx.lineTo(u, v) : ctx.moveTo(u, v); }); ctx.closePath(); } }
function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

function tractFill(id) {
  const yi = state.year - app.years[0];
  if (state.surface === 'community') {
    const c = app.community[state.jt]?.years?.[state.year]?.[id];
    if (c == null) return null;
    const slot = app.community[state.jt].colours[c];
    return CAT[state.theme].series[slot % 8];
  }
  if (state.surface === 'density') {
    const s = app.tractSeries[state.jt][id]; if (!s || s.jobs[yi] == null) return null;
    const d = s.jobs[yi] / app.tracts[id].acres;
    const k = d <= 0 ? -1 : Math.min(SEQ.length - 1, Math.floor((Math.log10(d) + 1.5) / 3 * SEQ.length));
    return k < 0 ? null : SEQ[Math.max(0, k)];
  }
  if (state.surface === 'centre') {
    const cs = app.centres[state.jt]?.[state.year] || [];
    return cs.includes(id) ? cssVar('--accent') : null;
  }
  return null;
}

function drawSlice() {
  const ctx = texCtx; const W = texCanvas.width, Hh = texCanvas.height;
  ctx.globalAlpha = 1; ctx.drawImage(reliefCanvas, 0, 0, W, Hh);
  const ink = state.theme === 'dark' ? '232,230,225' : '34,38,42';
  if (state.scale === 'metro') {
    for (const t of base.geo.metro.tracts) {
      const f = tractFill(t.id);
      if (f) { ctx.globalAlpha = state.surface === 'centre' ? 0.55 : 0.5; ctx.fillStyle = f; pathRings(ctx, t.rings); ctx.fill(); }
    }
    ctx.globalAlpha = 1; ctx.lineWidth = 0.8 * TEX_SCALE; ctx.strokeStyle = `rgba(${ink},0.28)`;
    for (const t of base.geo.metro.tracts) { pathRings(ctx, t.rings); ctx.stroke(); }
    if (state.sel) {
      const t = base.geo.metro.tracts.find((q) => q.id === state.sel);
      if (t) { ctx.lineWidth = 2.5 * TEX_SCALE; ctx.strokeStyle = cssVar('--accent'); pathRings(ctx, t.rings); ctx.stroke(); }
    }
    for (const c of base.geo.metro.counties) {
      ctx.lineWidth = (c.msa ? 1.8 : 1.1) * TEX_SCALE; ctx.strokeStyle = `rgba(${ink},${c.msa ? 0.7 : 0.4})`;
      pathRings(ctx, c.rings); ctx.stroke();
    }
  } else {
    ctx.lineWidth = 1.2 * TEX_SCALE; ctx.strokeStyle = `rgba(${ink},0.45)`;
    for (const s of base.geo.nation.states) { pathRings(ctx, s.rings); ctx.stroke(); }
  }
  terrainTex.needsUpdate = true;
}

// ---------------------------------------------------------------- flows
function flowRecords(year) {
  const scale = state.scale;
  const arr = flows[state.jt]?.[scale]?.[year];
  return arr || [];
}
function dirOf(o, d) { const a = app.nodes[o].msa, b = app.nodes[d].msa; return a && b ? 'w' : b ? 'i' : 'o'; }
function trendOf(o, d) { const t = app.trend[state.jt]?.[state.scale]?.[`${o}-${d}`]; return t == null ? 2 : t; }

function selectFlows(year, limit) {
  const arr = flowRecords(year); const col = SEGCOL[state.seg]; const out = [];
  const selIdx = state.sel ? app.nodeIdx[state.sel] : null;
  for (let k = 0; k < arr.length; k += NF) {
    const o = arr[k], d = arr[k + 1], v = arr[k + col];
    if (v < state.minFlow || o === d) continue;
    const dr = dirOf(o, d);
    if (!state.dir.has(dr)) continue;
    if (selIdx != null && o !== selIdx && d !== selIdx) continue;
    out.push([o, d, v, dr]);
  }
  out.sort((a, b) => b[2] - a[2]);
  return limit ? out.slice(0, limit) : out;
}

function colourOf(o, d, dr) {
  if (state.colour === 'trend') return TREND[state.theme][trendOf(o, d)];
  return CAT[state.theme][dr];
}

function widthBucket(v) { return v >= 250 ? 2 : v >= 50 ? 1 : 0; }

function arcPoints(a, b, y0, hmax, onTerrain) {
  const dx = b[0] - a[0], dz = b[1] - a[1], L = Math.hypot(dx, dz);
  const h = Math.min(hmax, 0.22 * L + 0.4);
  const pts = [];
  for (let s = 0; s <= NSEG; s++) {
    const t = s / NSEG, x = a[0] + dx * t, z = a[1] + dz * t;
    const base_ = onTerrain ? Math.max(heightAt(a[0], a[1]) * (1 - t) + heightAt(b[0], b[1]) * t, 0) : 0;
    pts.push(x, y0 + base_ + 4 * h * t * (1 - t) + 0.15, z);
  }
  return pts;
}

function makeLineMat(width, opacity) {
  const m = new LineMaterial({ linewidth: width, vertexColors: true, transparent: true, opacity, depthWrite: false, worldUnits: false });
  m.resolution.set(innerWidth, innerHeight); lineMats.push(m); return m;
}

function buildLayer(year, active) {
  const g = new THREE.Group(); g.userData.year = year;
  const recs = selectFlows(year, active ? 0 : (state.sel ? 0 : STACK_TOP_N));
  const y0 = yOf(year);
  const gap = H() / (app.years.length - 1);
  const onTerrain = active;
  const hmax = state.view === 'cube' && state.stack ? (active ? 1.2 * gap : 0.45 * gap) : 60 / div() * (state.scale === 'metro' ? 0.5 : 6);
  const buckets = [[], [], []], cols = [[], [], []];
  const col = new THREE.Color();
  for (const [o, d, v, dr] of recs) {
    let a = nodeXY(o), b = nodeXY(d); if (!a || !b) continue;
    const ca = clampToFrame(a[0], a[1]), cb = clampToFrame(b[0], b[1]);
    if (!active && !state.sel && (ca[2] || cb[2])) continue;   // off-frame flows only on the active slice
    a = ca; b = cb;
    const pts = arcPoints(a, b, y0 + (active ? 0 : 0), hmax, onTerrain);
    const bk = widthBucket(v);
    col.set(colourOf(o, d, dr));
    for (let s = 0; s < NSEG; s++) {
      buckets[bk].push(...pts.slice(s * 3, s * 3 + 6));
      cols[bk].push(col.r, col.g, col.b, col.r, col.g, col.b);
    }
  }
  const widths = [1.1, 2.2, 3.6];
  const dim = active ? 1 : (state.sel ? 0.6 : 0.16);
  buckets.forEach((pos, bk) => {
    if (!pos.length) return;
    const geo = new LineSegmentsGeometry(); geo.setPositions(pos); geo.setColors(cols[bk]);
    const line = new LineSegments2(geo, makeLineMat(widths[bk] * (active ? 1 : 0.8), dim * (active ? 0.9 : 1)));
    line.renderOrder = active ? 3 : 1;
    g.add(line);
  });
  // ghost plane for year layers in the stack
  if (!active && state.view === 'cube' && state.stack) {
    if (state.surface === 'community' || state.surface === 'centre') g.add(layerPoints(year, y0));
    const f = frame();
    const plane = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(f.x0, y0, f.z0), new THREE.Vector3(f.x1, y0, f.z0), new THREE.Vector3(f.x1, y0, f.z1), new THREE.Vector3(f.x0, y0, f.z1)]),
    new THREE.LineBasicMaterial({ color: state.theme === 'dark' ? 0x5a5f63 : 0xb5b3ad, transparent: true, opacity: app.shocks.includes(year) ? 0.9 : 0.35 }));
    g.add(plane);
  }
  return g;
}

function layerPoints(year, y0) {      // tract centroids coloured by community (or centre membership), per year
  if (state.scale !== 'metro') return new THREE.Group();
  const pos = [], cols = []; const col = new THREE.Color();
  for (const [id, t] of Object.entries(app.tracts)) {
    const p = nodeXY(t.i); if (!p) continue;
    let c = null;
    if (state.surface === 'community') {
      const cid = app.community[state.jt]?.years?.[year]?.[id];
      if (cid != null) c = CAT[state.theme].series[app.community[state.jt].colours[cid] % 8];
    } else if ((app.centres[state.jt]?.[year] || []).includes(id)) c = cssVar('--accent');
    if (!c) continue;
    pos.push(p[0], y0 + 0.05, p[1]); col.set(c); cols.push(col.r, col.g, col.b);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
  return new THREE.Points(g, new THREE.PointsMaterial({ size: state.surface === 'centre' ? 6 : 4, sizeAttenuation: false, vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false }));
}

function rebuildLayers() {
  for (const l of layers) { world.remove(l); l.traverse((o) => { o.geometry?.dispose?.(); o.material?.dispose?.(); }); }
  lineMats.length = 0; layers = [];
  if (state.view === 'cube' && state.stack) {
    for (const y of app.years) if (y !== state.year && yearValid(y)) { const l = buildLayer(y, false); layers.push(l); world.add(l); }
  }
  if (yearValid(state.year)) { const a = buildLayer(state.year, true); layers.push(a); world.add(a); }
  buildAxis();
}
function yearValid(y) { return !(state.jt === 'JT00' && y < 2010); }

// ---------------------------------------------------------------- time axis & labels
function buildAxis() {
  world.remove(axisGroup); axisGroup = new THREE.Group(); world.add(axisGroup);
  for (const el of labelEls.filter((e) => e.kind === 'axis')) el.el.remove();
  for (let k = labelEls.length - 1; k >= 0; k--) if (labelEls[k].kind === 'axis') labelEls.splice(k, 1);
  if (!(state.view === 'cube' && state.stack)) return;
  const f = frame();
  const pole = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(f.x1, 0, f.z1), new THREE.Vector3(f.x1, H(), f.z1)]),
    new THREE.LineBasicMaterial({ color: state.theme === 'dark' ? 0x8a9096 : 0x6b7177 }));
  axisGroup.add(pole);
  for (const y of app.years) {
    const major = y % 5 === 0 || app.shocks.includes(y) || y === state.year || y === app.years[0] || y === app.years.at(-1);
    if (!major) continue;
    const el = document.createElement('div');
    el.className = 'axis-label' + (y === state.year ? ' now' : app.shocks.includes(y) ? ' shock' : '');
    el.textContent = y; $('labels').appendChild(el);
    labelEls.push({ kind: 'axis', el, pos: new THREE.Vector3(f.x1, yOf(y), f.z1) });
  }
}

function buildLabels() {
  for (const e of labelEls) e.el.remove(); labelEls.length = 0;
  for (const p of app.places[state.scale]) {
    const el = document.createElement('div'); el.className = 'place-label city'; el.textContent = p.name;
    $('labels').appendChild(el);
    labelEls.push({ kind: 'place', el, xy: [p.xy[0] / div(), -p.xy[1] / div()] });
  }
}

function updateLabels() {
  const w = innerWidth, h = innerHeight; const v = new THREE.Vector3();
  const sy = slice.position.y;
  for (const L of labelEls) {
    if (L.kind === 'place') {
      if (!state.labels) { L.el.style.display = 'none'; continue; }
      v.set(L.xy[0], sy + heightAt(L.xy[0], L.xy[1]) + 0.3, L.xy[1]);
    } else v.copy(L.pos);
    v.project(camera);
    if (v.z > 1 || v.x < -1.1 || v.x > 1.1 || v.y < -1.1 || v.y > 1.1) { L.el.style.display = 'none'; continue; }
    L.el.style.display = '';
    L.el.style.transform = `translate(${(v.x + 1) / 2 * w}px, ${(1 - v.y) / 2 * h}px) translate(0, -50%)`;
  }
}

function frameCamera() {
  const f = frame(); const cx = (f.x0 + f.x1) / 2, cz = (f.z0 + f.z1) / 2, span = Math.max(f.x1 - f.x0, f.z1 - f.z0);
  if (state.view === 'cube' && state.stack) {
    controls.target.set(cx + span * 0.1, H() * 0.42, cz);
    camera.position.set(cx + span * 1.3, H() * 2.0, cz + span * 1.8);
  } else {
    controls.target.set(cx, 0, cz);
    camera.position.set(cx, span * 1.25, cz + span * 0.35);
  }
  camera.near = span / 200; camera.far = span * 20; camera.updateProjectionMatrix();
  controls.update();
}

// ---------------------------------------------------------------- refresh
function refresh(full) {
  slice.position.y = yOf(state.year);
  drawSlice();
  rebuildLayers();
  updateHeader();
  updateLegend();
  updateTimeline();
  if (full) renderCharts(); else markCharts();
  if (state.sel) renderSelection();
  writeHash();
}

function updateHeader() {
  $('year').textContent = state.year;
  const p = PERIODS.find(([a, b]) => state.year >= a && state.year <= b);
  $('period').textContent = p ? p[2] : '';
  const I = app.indicators[state.jt]; const k = state.year - app.years[0];
  $('span').textContent = state.jt === 'JT02' ? 'Private jobs (JT02)' : 'All jobs (JT00)';
  const tiles = [
    ['Jobs in the metro', fmt(I.jobs[k])],
    ['Live & work in metro', fmt(I.live_work[k])],
    ['In-commuters', fmt((I.in_mo[k] ?? 0) + (I.in_oos[k] ?? 0)), `${fmt(I.in_oos[k])} from other states`],
    ['Out-commuters', fmt((I.out_mo[k] ?? 0) + (I.out_oos[k] ?? 0)), `${fmt(I.out_oos[k])} to other states`],
    ['Median commute (within metro)', I.med_mi[k] == null ? '–' : I.med_mi[k].toFixed(1) + ' mi'],
    ['Distance-decay β', I.beta[k] == null ? '–' : I.beta[k].toFixed(2)],
  ];
  $('stats').innerHTML = tiles.map(([l, v, s]) => `<div class="stat"><b>${v}</b><span>${l}${s ? '<br>' + s : ''}</span></div>`).join('');
  if (!yearValid(state.year)) $('span').textContent += ' · not available before 2010';
}

function updateLegend() {
  const L = $('legend'); let h = '';
  if (state.colour === 'dir') {
    h += [['w', 'Within metro'], ['i', 'Into metro'], ['o', 'Out of metro']].map(([k, l]) => `<span><i style="background:${CAT[state.theme][k]}"></i>${l}</span>`).join('');
  } else {
    h += TREND.labels.map((l, k) => `<span><i style="background:${TREND[state.theme][k]}"></i>${l}</span>`).join('');
  }
  h += `<span style="color:var(--muted)">Line width: ≥10 · ≥50 · ≥250 workers</span>`;
  if (state.scale === 'metro') {
    if (state.surface === 'community') {
      const C = app.community[state.jt]; const ids = [...new Set(Object.values(C.years[state.year] || {}))].sort((a, b) => a - b);
      h += `<span style="flex-basis:100%;color:var(--muted)">Commuting communities, ${state.year}</span>`;
      h += ids.map((c) => `<span><i class="box" style="background:${CAT[state.theme].series[C.colours[c] % 8]}"></i>${C.labels[c] || 'Community ' + c}</span>`).join('');
    } else if (state.surface === 'density') {
      h += `<div class="ramp"><span style="color:var(--muted)">0.03</span>${SEQ.map((c) => `<b style="background:${c}"></b>`).join('')}<span style="color:var(--muted)">30+ jobs/acre</span></div>`;
    } else if (state.surface === 'centre') {
      h += `<span><i class="box" style="background:var(--accent)"></i>Job centre tract (LISA High-High, persistent)</span>`;
    }
  }
  L.innerHTML = h;
}

// ---------------------------------------------------------------- hover / click
function slicePoint(e) {
  pointer.set(e.clientX / innerWidth * 2 - 1, -e.clientY / innerHeight * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObject(terrain)[0];
  if (!hit) return null;
  return [hit.point.x * div(), -hit.point.z * div()];
}
function pip(x, y, ring) { let c = false; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const [xi, yi] = ring[i], [xj, yj] = ring[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; }
function tractAt(km) { if (!km || state.scale !== 'metro') return null; return base.geo.metro.tracts.find((t) => t.rings.some((r) => pip(km[0], km[1], r)))?.id; }
function nodeNear(km) {
  if (!km) return null; let best = null, bd = state.scale === 'metro' ? 6 : 60;
  app.nodes.forEach((n, i) => { const p = state.scale === 'metro' ? n.m : n.n; if (!p || n.kind === 't') return; const d = Math.hypot(p[0] - km[0], p[1] - km[1]); if (d < bd) { bd = d; best = i; } });
  return best;
}
function nodeFlowSums(i) {
  const arr = flowRecords(state.year); let inn = 0, out = 0;
  for (let k = 0; k < arr.length; k += NF) { if (arr[k + 1] === i) inn += arr[k + 2]; if (arr[k] === i) out += arr[k + 2]; }
  return [inn, out];
}
function onHover(e) {
  const km = slicePoint(e); const tip = $('tooltip');
  const t = tractAt(km);
  let html = null;
  if (t) {
    const s = app.tractSeries[state.jt][t]; const k = state.year - app.years[0]; const T = app.tracts[t];
    const cid = app.community[state.jt]?.years?.[state.year]?.[t];
    html = `<b>Tract ${t.slice(5, 9)}.${t.slice(9)}</b><span>${T.county} County</span><br>Jobs ${fmt(s?.jobs[k])} · resident workers ${fmt(s?.res[k])}<br>` +
      `<span>${(s?.jobs[k] / T.acres || 0).toFixed(2)} jobs/acre${cid != null ? ' · ' + (app.community[state.jt].labels[cid] || 'community ' + cid) : ''}</span>`;
  } else {
    const n = nodeNear(km);
    if (n != null) {
      const N = app.nodes[n]; const [inn, out] = nodeFlowSums(n);
      html = `<b>${N.name}</b><span>${N.st}${N.msa ? ' · metro county' : ''}</span><br>${state.year}: ${fmt(out)} commute to, ${fmt(inn)} commute from<br><span>(flows ≥10 workers shown)</span>`;
    }
  }
  if (!html) { tip.hidden = true; return; }
  tip.innerHTML = html; tip.hidden = false;
  tip.style.transform = `translate(${Math.min(e.clientX + 14, innerWidth - 290)}px, ${e.clientY + 14}px)`;
}
function onClick(e) {
  const t = tractAt(slicePoint(e));
  state.sel = t && t !== state.sel ? t : null;
  $('selection').hidden = !state.sel;
  refresh(false);
}
$('selClose').onclick = () => { state.sel = null; $('selection').hidden = true; refresh(false); };

function renderSelection() {
  const t = state.sel; const s = app.tractSeries[state.jt][t]; const T = app.tracts[t];
  $('selName').textContent = `Tract ${t.slice(5, 9)}.${t.slice(9)} · ${T.county} County`;
  const recs = selectFlows(state.year, 0); const i = app.nodeIdx[t];
  const top = recs.filter((r) => r[0] === i).slice(0, 3).map((r) => `${app.nodes[r[1]].name} ${fmt(r[2])}`);
  const topIn = recs.filter((r) => r[1] === i).slice(0, 3).map((r) => `${app.nodes[r[0]].name} ${fmt(r[2])}`);
  $('selMeta').innerHTML = `Residents work in: ${top.join(', ') || '–'}<br>Jobs filled from: ${topIn.join(', ') || '–'}`;
  lineChart($('selChart'), { title: 'Jobs and resident workers', series: [
    { name: 'Jobs', v: s.jobs }, { name: 'Resident workers', v: s.res }] , fmtY: fmt });
}

// ---------------------------------------------------------------- charts (SVG, crosshair + tooltip)
function lineChart(el, o) {
  const W = 294, Hc = o.h || 112, m = { l: 34, r: 8, t: 6, b: 16 };
  const yrs = app.years; const series = o.series.filter((s) => s.v.some((x) => x != null));
  const all = series.flatMap((s) => s.v.filter((x) => x != null));
  let y0 = o.min ?? Math.min(...all), y1 = o.max ?? Math.max(...all);
  if (o.min == null) y0 = Math.max(0, y0 - (y1 - y0) * 0.15) === 0 && y0 >= 0 && o.zero ? 0 : y0 - (y1 - y0) * 0.1;
  y1 += (y1 - y0) * 0.08;
  const X = (y) => m.l + (y - yrs[0]) / (yrs.length - 1) * (W - m.l - m.r), Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * (Hc - m.t - m.b);
  const cols = CAT[state.theme].series;
  const ticks = niceTicks(y0, y1, 4);
  let svg = `<svg viewBox="0 0 ${W} ${Hc}" role="img" aria-label="${o.title}">`;
  svg += ticks.map((t) => `<line class="gl" x1="${m.l}" x2="${W - m.r}" y1="${Y(t)}" y2="${Y(t)}"/><text x="${m.l - 4}" y="${Y(t) + 3}" text-anchor="end">${(o.fmtTick || o.fmtY)(t)}</text>`).join('');
  svg += app.shocks.map((y) => `<line class="shock" x1="${X(y)}" x2="${X(y)}" y1="${m.t}" y2="${Hc - m.b}"/>`).join('');
  svg += [2002, 2010, 2020, 2024].map((y) => `<text x="${X(y)}" y="${Hc - 3}" text-anchor="middle">${y}</text>`).join('');
  series.forEach((s, k) => {
    let d = '', pen = false;
    s.v.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? 'L' : 'M'}${X(yrs[i]).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; });
    svg += `<path d="${d}" fill="none" stroke="${s.c || cols[k]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  });
  svg += `<line class="yr" x1="${X(state.year)}" x2="${X(state.year)}" y1="${m.t}" y2="${Hc - m.b}"/>`;
  svg += `<line class="xh" x1="0" x2="0" y1="${m.t}" y2="${Hc - m.b}" visibility="hidden"/>`;
  svg += `<rect x="${m.l}" y="0" width="${W - m.l - m.r}" height="${Hc}" fill="transparent"/></svg>`;
  const legend = series.length > 1 ? `<div class="legend" style="margin-top:2px">${series.map((s, k) => `<span><i style="background:${s.c || cols[k]}"></i>${s.name}</span>`).join('')}</div>` : '';
  el.innerHTML = `<div class="ttl">${o.title}</div>${o.sub ? `<div class="sub">${o.sub}</div>` : ''}${svg}${legend}`;
  const sv = el.querySelector('svg'), xh = sv.querySelector('.xh');
  let tip = el.querySelector('.ctip');
  sv.addEventListener('pointermove', (e) => {
    const r = sv.getBoundingClientRect(); const px = (e.clientX - r.left) / r.width * W;
    const yi = Math.max(0, Math.min(yrs.length - 1, Math.round((px - m.l) / (W - m.l - m.r) * (yrs.length - 1))));
    xh.setAttribute('x1', X(yrs[yi])); xh.setAttribute('x2', X(yrs[yi])); xh.setAttribute('visibility', 'visible');
    if (!tip) { tip = document.createElement('div'); tip.className = 'ctip'; el.appendChild(tip); }
    tip.innerHTML = `<b>${yrs[yi]}</b>` + series.map((s, k) => `<br><i style="background:${s.c || cols[k]}"></i>${s.name}: ${s.v[yi] == null ? '–' : o.fmtY(s.v[yi])}`).join('');
    tip.style.left = Math.min(r.width - 150, (X(yrs[yi]) / W) * r.width + 8) + 'px'; tip.style.top = '18px'; tip.hidden = false;
  });
  sv.addEventListener('pointerleave', () => { xh.setAttribute('visibility', 'hidden'); if (tip) tip.hidden = true; });
  sv.addEventListener('click', (e) => { const r = sv.getBoundingClientRect(); const px = (e.clientX - r.left) / r.width * W;
    setYear(yrs[Math.max(0, Math.min(yrs.length - 1, Math.round((px - m.l) / (W - m.l - m.r) * (yrs.length - 1))))]); });
}
function niceTicks(a, b, n) { const st = Math.pow(10, Math.floor(Math.log10((b - a) / n))); const s = [1, 2, 2.5, 5, 10].map((k) => k * st).find((k) => (b - a) / k <= n) || st * 10; const out = []; for (let t = Math.ceil(a / s) * s; t <= b + 1e-9; t += s) out.push(+t.toFixed(10)); return out; }

function renderCharts() {
  const I = app.indicators[state.jt]; const k1 = (a) => a.map((v) => v == null ? null : v / 1000);
  const box = $('charts'); box.innerHTML = '';
  const add = (o) => { const d = document.createElement('div'); d.className = 'chart'; box.appendChild(d); lineChart(d, o); };
  add({ title: 'Commuters (thousands)', series: [
    { name: 'Live & work in metro', v: k1(I.live_work) }, { name: 'In from rest of MO', v: k1(I.in_mo) },
    { name: 'Out to rest of MO', v: k1(I.out_mo) }, { name: 'In from other states', v: k1(I.in_oos) }, { name: 'Out to other states', v: k1(I.out_oos) }],
    fmtY: (v) => v.toFixed(1), fmtTick: (v) => v.toFixed(0), h: 130 });
  add({ title: `Where ${app.coreName} County jobs' workers live`, series: [
    { name: app.coreName, v: I.core_share }, { name: 'Suburban metro', v: I.sub_share }, { name: 'Outer MO', v: I.outer_share }, { name: 'Other states', v: I.oos_share }],
    fmtY: (v) => pct(v), fmtTick: (v) => pct(v, 0), min: 0, max: 0.75 });
  add({ title: 'Median commute within the metro (miles)', series: [{ name: 'Median', v: I.med_mi }], fmtY: (v) => v.toFixed(1) });
  add({ title: 'Distance-decay exponent β', sub: 'Poisson gravity among tracts; lower = distance matters less', series: [{ name: 'β', v: I.beta }], fmtY: (v) => v.toFixed(3) });
  add({ title: 'Job concentration', series: [{ name: 'Top-5 tracts', v: I.top5 }, { name: 'Top-10 tracts', v: I.top10 }, { name: 'In job centres', v: I.centre_share }],
    fmtY: (v) => pct(v), fmtTick: (v) => pct(v, 0) });
  add({ title: 'Commuting communities', sub: 'Leiden partitions of the tract flow network', series: [{ name: 'Communities', v: I.n_comm }], fmtY: (v) => v.toFixed(0) });
  renderTable();
}
function markCharts() { renderCharts(); }

function renderTable() {
  const I = app.indicators[state.jt];
  const cols = [['jobs', 'Jobs', fmt], ['in_mo', 'In MO', fmt], ['in_oos', 'In oth.', fmt], ['out_mo', 'Out MO', fmt], ['out_oos', 'Out oth.', fmt], ['med_mi', 'Med mi', (v) => v?.toFixed(1) ?? '–']];
  $('tableView').innerHTML = `<table class="tv"><tr><th>Year</th>${cols.map((c) => `<th>${c[1]}</th>`).join('')}</tr>` +
    app.years.map((y, k) => `<tr><td>${y}</td>${cols.map(([key, , f]) => `<td>${f(I[key][k])}</td>`).join('')}</tr>`).join('') + '</table>';
}
function renderMethods() { $('methods').innerHTML = app.methods.map((p) => `<p class="note">${p}</p>`).join(''); }

// ---------------------------------------------------------------- UI & timeline
function seg(id, key, onChange, multi) {
  const el = $(id);
  el.querySelectorAll('button').forEach((b) => {
    if (!multi) b.classList.toggle('on', b.dataset.v === state[key]);
    b.onclick = async () => {
      if (multi) { const s = state[key]; s.has(b.dataset.v) ? s.delete(b.dataset.v) : s.add(b.dataset.v); b.classList.toggle('on'); }
      else { state[key] = b.dataset.v; el.querySelectorAll('button').forEach((q) => q.classList.toggle('on', q === b)); }
      await onChange();
    };
  });
}
function buildUI() {
  $('seg').value = state.seg; $('surface').value = state.surface; $('stack').checked = state.stack;
  $('selection').hidden = !state.sel;
  seg('scale', 'scale', () => { state.sel = null; $('selection').hidden = true; buildScale(); });
  seg('view', 'view', () => { frameCamera(); refresh(false); });
  seg('jt', 'jt', async () => { await ensureFlows(state.jt); if (!yearValid(state.year)) state.year = 2010; refresh(true); });
  seg('dir', 'dir', () => refresh(false), true);
  seg('colour', 'colour', () => refresh(false));
  seg('theme', 'theme', () => { document.documentElement.dataset.theme = state.theme; try { localStorage.setItem('sf-theme', state.theme); } catch {} buildRelief(); refresh(true); });
  $('seg').onchange = (e) => { state.seg = e.target.value; refresh(false); };
  $('surface').onchange = (e) => { state.surface = e.target.value; refresh(false); };
  let tm;
  $('minFlow').oninput = (e) => { state.minFlow = +e.target.value; $('minVal').textContent = state.minFlow; clearTimeout(tm); tm = setTimeout(() => refresh(false), 120); };
  $('relief').oninput = (e) => { state.relief = +e.target.value; $('reliefVal').textContent = '×' + state.relief; setTerrainHeights(); clearTimeout(tm); tm = setTimeout(() => refresh(false), 150); };
  $('stack').onchange = (e) => { state.stack = e.target.checked; frameCamera(); refresh(false); };
  $('labelsToggle').onchange = (e) => { state.labels = e.target.checked; };
  $('panelToggle').onclick = () => { const p = $('panel'); p.classList.toggle('collapsed'); $('panelToggle').setAttribute('aria-expanded', !p.classList.contains('collapsed')); };
  // timeline
  const ticks = $('ticks');
  app.years.forEach((y) => {
    const t = document.createElement('div'); t.className = 'tick' + (app.shocks.includes(y) ? ' shock' : ''); t.style.left = xPct(y) + '%'; ticks.appendChild(t);
    if (y % 5 === 0 || y === app.years[0] || y === app.years.at(-1) || app.shocks.includes(y)) {
      const l = document.createElement('div'); l.className = 'tick-label' + (y % 10 === 0 || y === 2002 || y === 2024 ? ' major' : ''); l.style.left = xPct(y) + '%'; l.textContent = y; ticks.appendChild(l);
    }
  });
  const track = $('track');
  const fromEvent = (e) => { const r = track.getBoundingClientRect(); return app.years[0] + Math.round((e.clientX - r.left) / r.width * (app.years.length - 1)); };
  let drag = false;
  track.addEventListener('pointerdown', (e) => { drag = true; track.setPointerCapture(e.pointerId); setYear(fromEvent(e)); });
  track.addEventListener('pointermove', (e) => { if (drag) setYear(fromEvent(e)); });
  track.addEventListener('pointerup', () => { drag = false; });
  addEventListener('keydown', (e) => {
    if (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowRight') setYear(state.year + 1);
    if (e.key === 'ArrowLeft') setYear(state.year - 1);
    if (e.key === ' ') { e.preventDefault(); togglePlay(); }
  });
  $('play').onclick = togglePlay;
}
function xPct(y) { return (y - app.years[0]) / (app.years.length - 1) * 100; }
function setYear(y) {
  y = Math.max(app.years[0], Math.min(app.years.at(-1), y));
  if (state.jt === 'JT00') y = Math.max(2010, y);
  if (y === state.year) return;
  state.year = y; refresh(false);
}
function updateTimeline() { $('thumb').style.left = xPct(state.year) + '%'; $('thumbLabel').textContent = state.year; }
let playTimer;
function togglePlay() {
  state.playing = !state.playing;
  $('playIcon').innerHTML = state.playing ? '<path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor"/>' : '<path d="M8 5v14l11-7z" fill="currentColor"/>';
  clearInterval(playTimer);
  if (state.playing) playTimer = setInterval(() => { setYear(state.year >= app.years.at(-1) ? (state.jt === 'JT00' ? 2010 : app.years[0]) : state.year + 1); }, 1100);
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
  updateLabels();
}

init().catch((e) => { $('loadingText').textContent = 'Could not load data: ' + e.message; console.error(e); });
