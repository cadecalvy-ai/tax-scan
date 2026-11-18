'use strict';
/* tax scanner. launch film — one canvas, everything a pure function of time.
   seek(t, tf): t = (sub)frame time for motion, tf = frame time for counters/typing. */

const W = 1440, H = 1440, CX = 720, CY = 720;
const { P, BEAT, g, T, DUR } = window.TIMING;      // every time in the film lives in timing.js
const MID = DUR / 2;

/* ───────── copy (edit here) ───────── */
const COPY = {
  name: 'tax scanner',
  tagline: 'opportunities found overnight',
  line1: 'you log off at 6',
  line2: "tax scanner doesn't",
  ask: 'Ask tax scanner',
  job: ['take these 10 tax returns,', 'find the financial services opportunities'],
  counter: 'signals found',
  lit: 200,
  mailTo: 'dana@hollis.example',
  mailSubject: 'a quick idea from your 2025 return',
  mailBody: ['hi dana, your 2025 return shows $18,400 in', 'taxable interest. worth a quick call?'],
  drafts: 5,
  sleep: 'while you sleep',
  clock: ['11:42 PM', '3:17 AM', '5:02 AM', '6:59 AM'],
  results: ['$3 million in business found', '4 tax advantages', '5 emails to clients drafted'],
  island: '5 emails drafted',
  date: 'Wednesday, November 18',
  notifs: [['5 emails to clients drafted', 'now'], ['4 tax advantages', '2h ago'], ['$3 million in business found', '4h ago']],
  calTitle: 'This week', calCount: '10 meetings',
  meetings: [['Hollis', 0, 1.0], ['Okafor', 2, 0.1], ['Moreno', 3, 1.9], ['Castillo', 1, 2.5], ['Tanaka', 4, 3.0],
             ['Park', 3, 4.5], ['Hargrove', 0, 5.5], ['Nakamura', 4, 6.0], ['Delgado', 2, 6.5], ['Ashby', 3, 7.5]],
  hoverTime: '10:30 AM',
  chartValue: 3000000, chartLabel: 'in business found overnight',
  cta: 'Scan now', endCta: 'scan now',
};

const WSLOW = 1.1;                                // word motion runs 10% slower than the shape morphs, so lines are easier to read
const ROLL = 0.6 * WSLOW;

/* ───────── math ───────── */
const clamp = (x, a = 0, b = 1) => x < a ? a : x > b ? b : x;
const lerp = (a, b, p) => a + (b - a) * p;
const lin = (t, a, b) => clamp((t - a) / (b - a));
const smooth = x => { x = clamp(x); return x * x * (3 - 2 * x); };
function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  return x => {
    if (x <= 0) return 0; if (x >= 1) return 1;
    let lo = 0, hi = 1, t = x;
    for (let i = 0; i < 26; i++) {
      const f = ((ax * t + bx) * t + cx) * t;
      if (f < x) lo = t; else hi = t;
      t = (lo + hi) / 2;
    }
    return ((ay * t + by) * t + cy) * t;
  };
}
const ease = bezier(.45, 0, .15, 1);           // every morph + the camera
const outE = bezier(.2, .7, .2, 1);            // pops (no overshoot)
const G = (t, a, d = 0.8) => ease((t - a) / d);
const O = (t, a, d = 0.4) => outE((t - a) / d);
const bump = (t, a, d = 0.22) => { const x = (t - a) / d + 0.35; return x <= 0 || x >= 1 ? 0 : Math.sin(Math.PI * x) ** 2; };
function rng(seed) { let s = seed >>> 0; return () => { s = (s + 0x6D2B79F5) >>> 0; let x = Math.imul(s ^ (s >>> 15), 1 | s); x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x; return ((x ^ (x >>> 14)) >>> 0) / 4294967296; }; }

/* ───────── canvas + assets ───────── */
const canvas = document.getElementById('c'), ctx = canvas.getContext('2d');
const mk = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; };
const inner = mk(W, H), ictx = inner.getContext('2d');
const gooC = mk(W, H), gctx = gooC.getContext('2d');
const IM = {}, BL = {};
const F = (w, s) => `${w} ${s}px Geist`, FM = (w, s) => `${w} ${s}px "Geist Mono"`;

function loadImg(n) { return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = 'assets/' + n + '.jpg'; }); }
function blurred(im, px) {
  const pad = 160, a = mk(W + 2 * pad, H + 2 * pad), x = a.getContext('2d');
  x.drawImage(im, 0, 0, W + 2 * pad, H + 2 * pad); x.drawImage(im, pad, pad);
  const b = mk(W + 2 * pad, H + 2 * pad), y = b.getContext('2d'); y.filter = `blur(${px}px) saturate(1.25)`; y.drawImage(a, 0, 0);
  const o = mk(W, H); o.getContext('2d').drawImage(b, -pad, -pad); return o;
}

/* ───────── small draw helpers (each restores the caller's alpha) ───────── */
function A(c, a, fn) { if (a <= 0.002) return; const pa = c.globalAlpha; c.globalAlpha = pa * clamp(a); fn(); c.globalAlpha = pa; }
function rr(c, x, y, w, h, r) { c.beginPath(); c.roundRect(x, y, w, h, Math.max(0, Math.min(r, w / 2, h / 2))); }
function text(c, s, x, y, font, color, align = 'left', ls = 0) {
  c.font = font; c.fillStyle = color; c.textAlign = align; c.textBaseline = 'alphabetic'; c.letterSpacing = ls + 'px'; c.fillText(s, x, y);
}
function measure(c, s, font, ls = 0) { c.font = font; c.letterSpacing = ls + 'px'; return c.measureText(s).width; }
function shadow(c, x, y, w, h, r, str = 1) {           // soft shadow that grows with the shape's height
  c.save();
  const k = c.getTransform().a;                          // shadow offsets ignore the transform, so scale them by hand
  c.shadowColor = `rgba(0,0,0,${0.34 * str})`; c.shadowBlur = Math.min(110, 14 + h * 0.075) * k; c.shadowOffsetX = 4000 * k; c.shadowOffsetY = (5 + h * 0.03) * k;
  c.fillStyle = '#000'; rr(c, x - 4000, y, w, h, r); c.fill();
  c.restore();
}
function rim(c, x, y, w, h, r, a = 1) {
  const gr = c.createLinearGradient(x, y, x + w * 0.3, y + h);
  gr.addColorStop(0, `rgba(255,255,255,${0.78 * a})`); gr.addColorStop(0.45, `rgba(255,255,255,${0.10 * a})`); gr.addColorStop(1, `rgba(255,255,255,${0.36 * a})`);
  c.save(); rr(c, x + 1.25, y + 1.25, w - 2.5, h - 2.5, r - 1.25); c.strokeStyle = gr; c.lineWidth = 2.5; c.stroke(); c.restore();
}

/* ───────── the world behind the glass: night → dawn → day ───────── */
const CAM = [[0, 1.16], [P - 0.1, 1.09], [T.send, 1.03], [T.pour, 1.08], [T.sent, 1.02], [T.split, 1.07], [T.phone, 1.13], [T.card, 1.07], [T.cta, 1.04]];
function cam(t) { let s = CAM[0][1]; for (let i = 1; i < CAM.length; i++) s = lerp(s, CAM[i][1], G(t, CAM[i][0])); return s + 0.0016 * t; }
function bgState(t) {
  const d = smooth(lin(t, T.day0, T.day1));
  if (d > 0) return ['dawn', 'day', d * 0.9];
  return ['night', 'dawn', smooth(lin(t, T.relight0, T.relight1))];
}
function drawBG(c, set, t) {
  const s = cam(t), [a, b, m] = bgState(t);
  c.save(); c.translate(CX, CY); c.scale(s, s); c.translate(-CX, -CY);
  c.drawImage(set[a], 0, 0);
  A(c, m, () => c.drawImage(set[b], 0, 0));
  c.restore();
}
function glass(c, t, x, y, w, h, r, o = {}) {
  if (o.shadow !== 0) shadow(c, x, y, w, h, r, o.shadow ?? 1);
  c.save(); rr(c, x, y, w, h, r); c.clip();
  drawBG(c, BL, t);
  c.fillStyle = o.tint || 'rgba(255,255,255,0.13)'; c.fillRect(x - 2, y - 2, w + 4, h + 4);
  c.restore();
  rim(c, x, y, w, h, r, o.rim ?? 1);
}
/* text that glides is drawn from a cached sprite: canvas text snaps to whole pixels vertically,
   which shows up as a one-pixel jump on the last frames of a slow ease */
const SPR = new Map();
function sprite(s, font, color, ls) {
  const key = s + '|' + font + '|' + color + '|' + ls; let sp = SPR.get(key); if (sp) return sp;
  const size = parseFloat(font.match(/([\d.]+)px/)[1]), pad = Math.ceil(size * 0.25), by = pad + Math.round(size * 1.1);
  const w = Math.ceil(measure(ctx, s, font, ls)), cv = mk(w + 2 * pad, Math.ceil(size * 1.5) + 2 * pad);
  text(cv.getContext('2d'), s, pad, by, font, color, 'left', ls);
  sp = { cv, w, pad, by }; if (SPR.size > 900) SPR.clear(); SPR.set(key, sp); return sp;
}
function stext(c, s, x, y, font, color, align = 'left', ls = 0) {
  if (!s) return; const sp = sprite(s, font, color, ls), ox = align === 'center' ? Math.round(sp.w / 2) : align === 'right' ? sp.w : 0;
  c.drawImage(sp.cv, x - ox - sp.pad, y - sp.by);
}
/* one mask line: lines roll up through it */
function roll(c, t, items, x, y, size, font, color, align = 'center', ls = 0) {
  const lh = size * 1.32;
  c.save(); c.beginPath(); c.rect(0, y - size * 0.98, W, size * 1.28); c.clip();
  for (const it of items) {
    const pin = G(t, it.tIn, ROLL), pout = it.tOut == null ? 0 : G(t, it.tOut, ROLL);
    if (pin <= 0 || pout >= 1) continue;
    stext(c, it.s, x, y + (1 - pin) * lh - pout * lh, font, color, align, ls);
  }
  c.restore();
}

/* ───────── cursors (the macOS pointer) ───────── */
const ARROW = new Path2D('M0 0 L0 17.2 L4.5 13.1 L7.6 20.4 L10.5 19.2 L7.5 12.1 L13.4 12.1 Z');
function pointer(c, x, y, fill, scale = 1, label) {
  c.save(); c.translate(x, y); c.scale(3.1 * scale, 3.1 * scale);
  c.shadowColor = 'rgba(0,0,0,0.35)'; c.shadowBlur = 10; c.shadowOffsetY = 4;
  c.lineJoin = 'round'; c.lineWidth = 2.2; c.strokeStyle = '#fff'; c.stroke(ARROW);
  c.shadowColor = 'transparent'; c.fillStyle = fill; c.fill(ARROW);
  c.restore();
  if (label) {
    c.save(); c.translate(x, y); c.scale(scale, scale);
    const w = measure(c, label, F(600, 25)) + 30;
    rr(c, 30, 58, w, 44, 13); c.fillStyle = fill; c.fill();
    text(c, label, 45, 89, F(600, 25), '#fff');
    c.restore();
  }
}
function path(t, start, segs) { let [x, y] = start; for (const s of segs) { const p = ease((t - s.a) / (s.b - s.a)); x = lerp(x, s.x, p); y = lerp(y, s.y, p); } return [x, y]; }

/* ───────── the one element: a table of states, each a 0.8s glide ───────── */
const R0 = 11;                                   // the period's radius
const MS = [
  { t: T.pill,     x: CX, y: CY,      w: 830,  h: 165,  r: 82.5, col: [255, 255, 255, 0], bz: 0 },   // "Ask" pill
  { t: T.click1,   w: 1190, h: 200, r: 64 },                                                       // input
  { t: T.send,     w: 16, h: 16, r: 8, col: [255, 255, 255, 1] },                                 // dot
  { t: T.pour,     y: 730, w: 1170, h: 680, r: 60, col: [255, 255, 255, 0] },                      // email composer
  { t: T.sent,     y: CY, w: 236, h: 236, r: 118 },                                                // orb
  { t: T.split, d: 0.001, w: 700, h: 150, r: 75, col: [0, 0, 0, 1] },                              // (goo) → Dynamic Island
  { t: T.phone,    w: 600, h: 1220, r: 104, bz: 14 },                                              // phone
  { t: T.card,     y: 730, w: 1084, h: 966, r: 76, col: [255, 255, 255, 1], bz: 0 },               // calendar card
  { t: T.chart,    w: 1204, h: 922, r: 76 },                                                       // chart card
  { t: T.cta,      y: CY, w: 580, h: 172, r: 86, col: [0, 0, 0, 1] },                              // CTA button
  { t: T.ctaClick, w: 2 * R0, h: 2 * R0, r: R0 },                                                  // the period
];
for (let i = 1; i < MS.length; i++) MS[i] = { ...MS[i - 1], d: 0.8, ...MS[i] };
function mState(t) {
  const s = { ...MS[0], col: [...MS[0].col] };
  for (let i = 1; i < MS.length; i++) {
    const k = MS[i]; if (t <= k.t) break;
    const p = ease((t - k.t) / k.d);
    for (const key of ['x', 'y', 'w', 'h', 'r', 'bz']) s[key] = lerp(s[key], k[key], p);
    for (let j = 0; j < 4; j++) s.col[j] = lerp(s.col[j], k.col[j], p);
  }
  const press = 1 - 0.035 * (bump(t, T.click1) + bump(t, T.ctaClick));
  const sc = lerp(0.82, 1, O(t, T.pill, 0.45)) * press;
  s.w *= sc; s.h *= sc; s.r *= sc; s.x0 = s.x - s.w / 2; s.y0 = s.y - s.h / 2; s.x1 = s.x0 + s.w; s.y1 = s.y0 + s.h;
  return s;
}
const GOO0 = T.split, GOO1 = T.merge + 0.86;

/* ───────── scene: grid ───────── */
const GRID = (() => {
  const cols = 23, rows = 15, sp = 40, gy = 750, dots = [], rnd = rng(7);
  for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
    const dx = (i - 11) * sp, dy = (j - 7) * sp;
    dots.push({ dx, dy, d: Math.hypot(dx, dy) / sp, k: rnd(), lit: false });
  }
  [...dots].sort((a, b) => a.k - b.k).slice(0, COPY.lit).forEach(d => d.lit = true);
  return { dots, gy, x0: CX - 11 * sp, x1: CX + 11 * sp, y0: gy - 7 * sp, y1: gy + 7 * sp };
})();
const scanX = t => lerp(GRID.x0 - 90, GRID.x1 + 90, ease(lin(t, T.scan0, T.scan1)));
function drawGrid(c, t, tf) {
  if (t < T.ripple || t > T.pour + 1.1) return;
  const sx = scanX(t);
  for (const d of GRID.dots) {
    const p = O(t, T.ripple + d.d * 0.036, 0.5); if (p <= 0) continue;
    let x = CX + d.dx * lerp(0.5, 1, p), y = GRID.gy + d.dy * lerp(0.5, 1, p), r = 4.6 * p, a = 0.5 * p;
    if (d.lit) {
      const l = clamp((sx - (CX + d.dx)) / 70);
      r = lerp(r, 7.2, l) + 3 * Math.sin(Math.PI * l); a = lerp(a, 1, l);
      const q = ease((t - (T.pour + d.d * 0.022 + d.k * 0.08)) / 0.56);
      if (q >= 1) continue;
      x = lerp(x, CX + d.dx * 0.06, q); y = lerp(y, 730 + d.dy * 0.06, q); r *= 1 - q * q * 0.75;
    } else {
      const q = G(t, T.pour - 0.05 + (14 - d.d) * 0.012, 0.45); if (q >= 1) continue;
      r *= 1 - q; a *= 1 - q;
    }
    c.fillStyle = `rgba(255,255,255,${a})`; c.beginPath(); c.arc(x, y, r, 0, 6.2832); c.fill();
  }
  // the scan line: a glass bar
  const ba = O(t, T.scan0 - 0.05, 0.3) * (1 - G(t, T.scan1 - 0.22, 0.3));
  A(c, ba, () => glass(c, t, sx - 36, GRID.y0 - 44, 72, GRID.y1 - GRID.y0 + 88, 22, { tint: 'rgba(255,255,255,0.30)', shadow: 0.6 }));
  // the counter (reads the frame's time)
  const n = GRID.dots.reduce((k, d) => k + (d.lit && CX + d.dx < scanX(tf) - 20 ? 1 : 0), 0);
  const font = F(700, 68), wAll = measure(c, `${COPY.lit} ${COPY.counter}`, font, -2), wNum = measure(c, `${COPY.lit}`, font, -2);
  const xN = Math.round(CX - wAll / 2 + wNum);
  roll(c, t, [{ s: String(n), tIn: T.scan0 - 0.1, tOut: T.pour - 0.05 }], xN, 392, 68, font, '#fff', 'right', -2);
  roll(c, t, [{ s: COPY.counter, tIn: T.scan0 - 0.1, tOut: T.pour - 0.05 }], xN + 18, 392, 68, font, '#fff', 'left', -2);
}

/* ───────── scene: contents of the one element ───────── */
function arrow(c, x, y, len, color, lw, dir = 'right') {
  c.save(); c.translate(x, y); if (dir === 'up') c.rotate(-Math.PI / 2);
  c.strokeStyle = color; c.lineWidth = lw; c.lineCap = 'round'; c.lineJoin = 'round';
  c.beginPath(); c.moveTo(-len / 2, 0); c.lineTo(len / 2, 0); c.moveTo(len / 2 - len * 0.38, -len * 0.38); c.lineTo(len / 2, 0); c.lineTo(len / 2 - len * 0.38, len * 0.38); c.stroke();
  c.restore();
}
function typed(lines, p) { let n = Math.floor(lines.join('').length * clamp(p)); return lines.map(l => { const s = l.slice(0, n); n = Math.max(0, n - l.length); return s; }); }

function askContent(c, t, tf, m) {
  // pill label
  A(c, O(t, P + 0.08, 0.4) * (1 - G(t, T.click1, 0.3)), () => text(c, COPY.ask, m.x, m.y + 19, F(600, 54), '#fff', 'center', -1));
  // input: typed job + send button
  const a = G(t, T.click1 + 0.3, 0.4) * (1 - G(t, T.send + 0.02, 0.3));
  if (a <= 0) return;
  A(c, a, () => {
    const font = F(500, 42), ls = -0.5, tx = m.x0 + 58, ys = [m.y - 14, m.y + 42];
    const out = typed(COPY.job, lin(tf, T.type0, T.type1));
    let cx = tx, cyl = ys[0];
    out.forEach((s, i) => { if (!s && i) return; text(c, s, tx, ys[i], font, '#fff', 'left', ls); cx = tx + measure(c, s, font, ls); cyl = ys[i]; });
    if (tf < T.send) { c.fillStyle = '#fff'; c.fillRect(cx + 5, cyl - 36, 3, 46); }
    if (tf < T.type0) text(c, 'Ask anything', tx + 18, ys[0] + 28, font, 'rgba(255,255,255,0.45)', 'left', ls);
    const bs = G(t, T.click1 + 0.25, 0.5) * (1 - 0.1 * bump(t, T.send)), bx = m.x1 - 92, by = m.y;
    c.fillStyle = '#fff'; c.beginPath(); c.arc(bx, by, 56 * bs, 0, 6.2832); c.fill();
    arrow(c, bx, by, 40 * bs, '#0b0b0f', 6 * bs, 'up');
  });
}

function mailContent(c, t, tf, m) {
  const a = G(t, T.pour + 0.42, 0.36) * (1 - G(t, T.sent + 0.14, 0.3));
  if (a <= 0) return;
  c.save(); rr(c, m.x0, m.y0, m.w, m.h, m.r); c.clip();
  A(c, a, () => {
    const x0 = CX - 585, y0 = 730 - 340, x1 = CX + 585, y1 = 730 + 340;
    text(c, 'To', x0 + 58, y0 + 96, F(500, 32), 'rgba(255,255,255,0.6)');
    const cw = measure(c, COPY.mailTo, FM(500, 29)) + 40;
    rr(c, x0 + 118, y0 + 58, cw, 56, 14); c.fillStyle = 'rgba(255,255,255,0.16)'; c.fill();
    text(c, COPY.mailTo, x0 + 138, y0 + 96, FM(500, 29), '#fff');
    const n = 1 + Math.round((COPY.drafts - 1) * lin(tf, T.sent + 0.02, T.sent + 0.3));
    text(c, `draft ${n}/${COPY.drafts}`, x1 - 58, y0 + 96, FM(500, 29), 'rgba(255,255,255,0.72)', 'right');
    c.fillStyle = 'rgba(255,255,255,0.16)'; c.fillRect(x0 + 58, y0 + 146, 1170 - 116, 2);
    text(c, COPY.mailSubject, x0 + 58, y0 + 238, F(700, 52), '#fff', 'left', -1.2);
    const font = F(500, 41), out = typed(COPY.mailBody, lin(tf, T.type2a, T.type2b));
    let cx = x0 + 58, cyl = y0 + 330;
    out.forEach((s, i) => { if (!s && i) return; const y = y0 + 330 + i * 62; text(c, s, x0 + 58, y, font, 'rgba(255,255,255,0.94)', 'left', -0.3); cx = x0 + 58 + measure(c, s, font, -0.3); cyl = y; });
    if (tf > T.type2a - 0.2 && tf < T.sent) { c.fillStyle = '#fff'; c.fillRect(cx + 5, cyl - 35, 3, 45); }
    const bs = 1 - 0.07 * bump(t, T.sent), bw = 214 * bs, bh = 88 * bs, bcx = x1 - 58 - 107, bcy = y1 - 56 - 44;
    shadow(c, bcx - bw / 2, bcy - bh / 2, bw, bh, 44, 0.7);
    rr(c, bcx - bw / 2, bcy - bh / 2, bw, bh, 44); c.fillStyle = '#fff'; c.fill();
    text(c, 'Send', bcx - 20, bcy + 13, F(600, 36), '#0b0b0f', 'center', -0.5);
    arrow(c, bcx + 52, bcy + 1, 26, '#0b0b0f', 4);
  });
  c.restore();
}
const SEND_BTN = [CX + 585 - 58 - 107, 730 + 340 - 56 - 44];

function orbContent(c, t, tf, m) {
  const a = G(t, T.sent + 0.42, 0.38); if (a <= 0 || t > T.split) return;
  A(c, a, () => {
    const p = lin(t, T.ring0, T.ring1), pf = lin(tf, T.ring0, T.ring1);
    c.lineWidth = 12; c.lineCap = 'round';
    c.strokeStyle = 'rgba(255,255,255,0.22)'; c.beginPath(); c.arc(m.x, m.y, 80, 0, 6.2832); c.stroke();
    if (p > 0) { c.strokeStyle = '#fff'; c.beginPath(); c.arc(m.x, m.y, 80, -Math.PI / 2, -Math.PI / 2 + Math.max(0.001, p) * 6.2832); c.stroke(); }
    text(c, Math.round(pf * 100) + '%', m.x, m.y + 17, F(700, 48), '#fff', 'center', -1);
  });
  // black flood
  const f = G(t, T.black, 0.3);
  if (f > 0) { c.save(); rr(c, m.x0, m.y0, m.w, m.h, m.r); c.clip(); c.fillStyle = '#000'; c.beginPath(); c.arc(m.x, m.y, f * 124, 0, 6.2832); c.fill(); c.restore(); }
}
function nightExtras(c, t) {
  // clock chip
  const a = G(t, T.sent + 0.45, 0.35) * (1 - G(t, T.black - 0.05, 0.3));
  if (a > 0) A(c, a, () => {
    const w = 262, h = 66, x = CX - w / 2, y = 498;
    glass(c, t, x, y, w, h, 33, { shadow: 0.7, tint: 'rgba(255,255,255,0.16)' });
    c.strokeStyle = '#fff'; c.lineWidth = 3; c.lineCap = 'round'; c.beginPath(); c.arc(x + 42, y + 33, 12, 0, 6.2832); c.moveTo(x + 42, y + 26); c.lineTo(x + 42, y + 33); c.lineTo(x + 47, y + 36); c.stroke();
    c.save(); rr(c, x, y + 6, w, h - 12, 20); c.clip();
    const items = COPY.clock.map((s, i) => ({ s, tIn: i ? T.clock[i] : -9, tOut: T.clock[i + 1] ?? null }));
    for (const it of items) {
      const pin = G(t, it.tIn, 0.34 * WSLOW), pout = it.tOut == null ? 0 : G(t, it.tOut, 0.34 * WSLOW);
      if (pin <= 0 || pout >= 1) continue;
      stext(c, it.s, x + 68, y + 44 + (1 - pin) * 56 - pout * 56, FM(600, 30), '#fff');
    }
    c.restore();
  });
  roll(c, t, [{ s: COPY.sleep, tIn: T.sleepIn, tOut: T.sleepOut }], CX, 300, 132, F(700, 132), '#fff', 'center', -5);
}

/* results pills (goo split) and the merge into the island */
let PILLW = [760, 520, 720];
function pillRect(i, t) {
  const ps = G(t, T.split + i * 0.03), pm = G(t, T.merge + (2 - i) * 0.02);
  const tgt = { x: CX, y: 458 + i * 262, w: PILLW[i], h: 150, r: 75 };
  const o = {};
  for (const [k, a, b, e] of [['x', CX, tgt.x, CX], ['y', CY, tgt.y, CY], ['w', 236, tgt.w, 700], ['h', 236, tgt.h, 150], ['r', 118, tgt.r, 75]]) o[k] = lerp(lerp(a, b, ps), e, pm);
  return o;
}
/* goo strength 0..1: at 0 the filter is an identity, so the hand-off to and from the crisp shape is exact */
const GOO_N = 32;
for (let i = 1; i <= GOO_N; i++) {
  const u = i / GOO_N, k = lerp(1, 26, u);
  document.querySelector('svg').insertAdjacentHTML('beforeend', `<filter id="goo${i}" x="-10%" y="-10%" width="120%" height="120%" color-interpolation-filters="sRGB"><feGaussianBlur in="SourceGraphic" stdDeviation="${16 * u}"/><feColorMatrix mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 ${k} ${-(k - 1) / 2}"/></filter>`);
}
const gooU = t => Math.max(Math.min(G(t, T.split, 0.15), 1 - G(t, T.split + 0.62, 0.26)), Math.min(G(t, T.merge, 0.15), 1 - G(t, T.merge + 0.58, 0.26)));
function drawGoo(c, t) {
  if (t < GOO0 || t >= GOO1) return false;
  const rs = [0, 1, 2].map(i => pillRect(i, t));
  rs.forEach((r, i) => {                           // one shadow while the shapes coincide, three once they part
    const sep = G(t, T.split + i * 0.03) * (1 - G(t, T.merge + (2 - i) * 0.02));
    shadow(c, r.x - r.w / 2, r.y - r.h / 2, r.w, r.h, r.r, i === 1 ? 1 - 0.2 * sep : 0.8 * sep);
  });
  gctx.clearRect(0, 0, W, H); gctx.fillStyle = '#000';
  rs.forEach((r, i) => {                           // coincident copies would triple the edge antialiasing
    if (i !== 1 && Math.abs(r.y - rs[1].y) + Math.abs(r.w - rs[1].w) + Math.abs(r.h - rs[1].h) < 0.02) return;
    rr(gctx, r.x - r.w / 2, r.y - r.h / 2, r.w, r.h, r.r); gctx.fill();
  });
  const lv = Math.round(gooU(t) * GOO_N);
  c.save(); if (lv > 0) c.filter = `url(#goo${lv})`; c.drawImage(gooC, 0, 0); c.restore();
  rs.forEach((r, i) => {
    const a = G(t, T.split + 0.5 + i * 0.05, 0.34) * (1 - G(t, T.merge - 0.04, 0.26));
    if (a <= 0) return;
    const x0 = r.x - PILLW[i] / 2;
    const cs = O(t, T.checks[i], 0.34);
    if (cs > 0) {
      const cx = x0 + 84, cy = r.y;
      A(c, 1 - G(t, T.merge - 0.04, 0.26), () => {
        c.fillStyle = '#30D158'; c.beginPath(); c.arc(cx, cy, 36 * cs, 0, 6.2832); c.fill();
        c.strokeStyle = '#fff'; c.lineWidth = 7 * cs; c.lineCap = 'round'; c.lineJoin = 'round';
        c.beginPath(); c.moveTo(cx - 15 * cs, cy + 1 * cs); c.lineTo(cx - 4 * cs, cy + 12 * cs); c.lineTo(cx + 16 * cs, cy - 11 * cs); c.stroke();
      });
    }
    A(c, a, () => text(c, COPY.results[i], x0 + 146, r.y + 17, F(600, 48), '#fff', 'left', -0.8));
  });
  return true;
}
function islandContent(c, t, m) {
  const a = G(t, T.merge + 0.5, 0.34) * (1 - G(t, T.phone, 0.25)); if (a <= 0) return;
  A(c, a, () => {
    const x = CX - 350, y = CY, sx = x + 74;
    c.fillStyle = '#FFD60A'; c.beginPath(); c.arc(sx, y, 14, 0, 6.2832); c.fill();
    c.strokeStyle = '#FFD60A'; c.lineWidth = 5; c.lineCap = 'round'; c.beginPath();
    for (let k = 0; k < 8; k++) { const an = k * Math.PI / 4; c.moveTo(sx + Math.cos(an) * 22, y + Math.sin(an) * 22); c.lineTo(sx + Math.cos(an) * 29, y + Math.sin(an) * 29); }
    c.stroke();
    text(c, COPY.island, x + 126, y + 16, F(600, 44), '#fff', 'left', -0.6);
    text(c, '7:00 AM', x + 700 - 54, y + 12, FM(500, 29), 'rgba(255,255,255,0.6)', 'right');
  });
}

/* phone lock screen */
function phoneBG(c, set, sx0, sy0, sw, sh) {       // the day photo, cover-fit to the screen
  const sc = Math.max(sh / H, sw / W) * 1.02, dw = W * sc, dh = H * sc;
  c.drawImage(set.day, sx0 + (sw - dw) / 2, sy0 + (sh - dh) / 2, dw, dh);
}
function notifRect(i) { return { x: CX - 268, y: 806 + i * 156, w: 536, h: 140, r: 38 }; }
function phoneContent(c, t, m) {
  if (t < T.phone || m.bz < 0.05 && t > T.card + 0.8) return;
  const b = m.bz, sx0 = m.x0 + b, sy0 = m.y0 + b, sw = m.w - 2 * b, sh = m.h - 2 * b, sr = Math.max(0, m.r - b);
  const lit = G(t, T.phone + 0.18, 0.62);
  const open = G(t, T.tap + 0.02, 0.8);            // the tapped notification opens like an app
  c.save(); rr(c, sx0, sy0, sw, sh, sr); c.clip();
  A(c, lit, () => phoneBG(c, IM, sx0, sy0, sw, sh));
  const la = G(t, T.phone + 0.42, 0.36) * (1 - G(t, T.tap + 0.2, 0.4));
  A(c, la, () => {
    rr(c, CX - 88, 148, 176, 52, 26); c.fillStyle = '#000'; c.fill();                       // Dynamic Island
    text(c, COPY.date, CX, 296, F(500, 35), '#fff', 'center', -0.3);
    text(c, '7:00', CX, 486, F(600, 196), '#fff', 'center', -6);
  });
  for (let i = 2; i >= 0; i--) {
    const n = notifRect(i), p = O(t, T.notif[i], 0.5); if (p <= 0) continue;
    const fade = i === 0 ? 1 : 1 - G(t, T.tap + 0.2, 0.4);
    let { x, y, w, h, r } = n; y += (1 - p) * 70;
    const tapS = i === 0 ? 1 - 0.03 * bump(t, T.tap) : 1;
    if (i === 0 && open > 0) { x = lerp(x, sx0, open); y = lerp(y, sy0, open); w = lerp(w, sw, open); h = lerp(h, sh, open); r = lerp(r, sr, open); }
    else { x += w * (1 - tapS) / 2; y += h * (1 - tapS) / 2; w *= tapS; h *= tapS; }
    A(c, p * fade, () => {
      shadow(c, x, y, w, h, r, 0.5);
      c.save(); rr(c, x, y, w, h, r); c.clip(); phoneBG(c, BL, sx0, sy0, sw, sh); c.fillStyle = 'rgba(255,255,255,0.58)'; c.fillRect(x, y, w, h); c.restore();
      rim(c, x, y, w, h, r, 0.8);
      const white = i === 0 ? G(t, T.tap, 0.3) : 0;
      if (white > 0) { A(c, white, () => { rr(c, x, y, w, h, r); c.fillStyle = '#fff'; c.fill(); }); }
      A(c, 1 - (i === 0 ? G(t, T.tap, 0.25) : 0), () => {
        rr(c, x + 22, y + 40, 60, 60, 16); c.fillStyle = '#0b0b0f'; c.fill();
        c.fillStyle = '#fff'; c.beginPath(); c.arc(x + 62, y + 80, 6, 0, 6.2832); c.fill();
        text(c, COPY.name, x + 100, y + 58, F(600, 25), '#0b0b0f', 'left', -0.2);
        text(c, COPY.notifs[i][1], x + w - 24, y + 58, F(500, 22), 'rgba(11,11,15,0.5)', 'right');
        text(c, COPY.notifs[i][0], x + 100, y + 100, F(500, 28.5), '#0b0b0f', 'left', -0.4);
      });
    });
  }
  c.restore();
}

/* calendar + chart (contents of the white card) */
const CAL = { x0: CX - 542, y0: 730 - 483, w: 1084, h: 966 };
function meetRect(i) { const [, col, row] = COPY.meetings[i]; const cw = (CAL.w - 128) / 5; return { x: CAL.x0 + 64 + col * cw + (cw - 172) / 2, y: CAL.y0 + 262 + row * 80, w: 172, h: 58 }; }
function calContent(c, t, m) {
  const a = G(t, T.card + 0.42, 0.4) * (1 - G(t, T.chart, 0.3)); if (a <= 0) return;
  c.save(); rr(c, m.x0, m.y0, m.w, m.h, m.r); c.clip();
  A(c, a, () => {
    const { x0, y0, w } = CAL, cw = (w - 128) / 5;
    text(c, COPY.calTitle, x0 + 64, y0 + 118, F(700, 62), '#0b0b0f', 'left', -2);
    text(c, COPY.calCount, x0 + w - 64, y0 + 112, FM(500, 30), 'rgba(11,11,15,0.5)', 'right');
    ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].forEach((d, i) => text(c, d, x0 + 64 + cw * (i + 0.5), y0 + 208, F(500, 33), 'rgba(11,11,15,0.5)', 'center'));
    c.fillStyle = 'rgba(11,11,15,0.09)'; for (let k = 0; k < 9; k++) c.fillRect(x0 + 64, y0 + 250 + k * 80, w - 128, 2);
    COPY.meetings.forEach((mt, i) => {
      const p = O(t, T.meet0 + i * 0.082, 0.36); if (p <= 0) return;
      const r = meetRect(i), s = lerp(0.6, 1, p), hov = i === 2 ? G(t, T.hover, 0.3) * 0.04 : 0, sc = s + hov;
      A(c, p, () => {
        c.save(); c.translate(r.x + r.w / 2, r.y + r.h / 2); c.scale(sc, sc);
        shadow(c, -r.w / 2, -r.h / 2, r.w, r.h, 15, 0.45);
        rr(c, -r.w / 2, -r.h / 2, r.w, r.h, 15); c.fillStyle = '#0b0b0f'; c.fill();
        text(c, mt[0], -r.w / 2 + 18, 10, F(600, 28), '#fff', 'left', -0.3);
        c.restore();
      });
    });
    const hp = O(t, T.hover + 0.05, 0.3) * (1 - G(t, T.chart - 0.2, 0.25));
    if (hp > 0) A(c, hp, () => {
      const r = meetRect(2), tw = 172, tx = r.x, ty = r.y - 66 + (1 - hp) * 10;
      shadow(c, tx, ty, tw, 54, 14, 0.6); rr(c, tx, ty, tw, 54, 14); c.fillStyle = '#0b0b0f'; c.fill();
      text(c, COPY.hoverTime, tx + tw / 2, ty + 37, F(600, 27), '#fff', 'center');
    });
  });
  c.restore();
}
const CH = (() => {
  const x0 = CX - 602 + 72, x1 = CX + 602 - 72, yb = 730 + 461 - 70, yt = 730 + 461 - 470;
  const pts = [[0, .05], [.09, .10], [.17, .12], [.25, .09], [.34, .19], [.43, .26], [.5, .24], [.58, .37], [.66, .47], [.73, .44], [.82, .62], [.91, .78], [1, .96]];
  const P2 = [];                                    // Catmull-Rom sampled polyline
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    for (let k = 0; k < 24; k++) {
      const u = k / 24, u2 = u * u, u3 = u2 * u, q = j => 0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * u + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * u2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * u3);
      P2.push([q(0), q(1)]);
    }
  }
  P2.push(pts[pts.length - 1]);
  const xy = p => [lerp(x0, x1, p[0]), lerp(yb, yt, p[1])];
  const at = f => { const u = clamp(f) * (P2.length - 1), i = Math.min(P2.length - 2, Math.floor(u)), k = u - i; return [lerp(P2[i][0], P2[i + 1][0], k), lerp(P2[i][1], P2[i + 1][1], k)]; };
  return { x0, x1, yb, yt, P2, xy, at, end: xy(pts[pts.length - 1]) };
})();
const chartF = t => ease(lin(t, T.count0, T.count1));
const money = v => '$' + Math.round(v).toLocaleString('en-US');
function chartContent(c, t, tf, m) {
  const a = G(t, T.chart + 0.45, 0.4) * (1 - G(t, T.flood + 0.05, 0.3)); if (a <= 0) return;
  c.save(); rr(c, m.x0, m.y0, m.w, m.h, m.r); c.clip();
  A(c, a, () => {
    const x0 = CX - 602, y0 = 730 - 461, f = chartF(t), ff = chartF(tf);
    text(c, money(COPY.chartValue * CH.at(ff)[1] / 0.96), x0 + 70, y0 + 196, F(700, 124), '#0b0b0f', 'left', -5);
    text(c, COPY.chartLabel, x0 + 74, y0 + 258, F(500, 34), 'rgba(11,11,15,0.5)', 'left', -0.2);
    c.fillStyle = 'rgba(11,11,15,0.08)'; for (let k = 0; k < 3; k++) c.fillRect(CH.x0, CH.yt + 20 + k * 150, CH.x1 - CH.x0, 2);
    if (f > 0) {
      const n = f * (CH.P2.length - 1), head = CH.xy(CH.at(f));
      const trace = () => { c.beginPath(); CH.P2.forEach((p, i) => { if (i > n) return; const [x, y] = CH.xy(p); i ? c.lineTo(x, y) : c.moveTo(x, y); }); c.lineTo(head[0], head[1]); };
      trace(); c.lineTo(head[0], CH.yb + 70); c.lineTo(CH.x0, CH.yb + 70); c.closePath();
      const gr = c.createLinearGradient(0, CH.yt, 0, CH.yb + 70); gr.addColorStop(0, 'rgba(11,11,15,0.13)'); gr.addColorStop(1, 'rgba(11,11,15,0.0)'); c.fillStyle = gr; c.fill();
      trace(); c.strokeStyle = '#0b0b0f'; c.lineWidth = 5.5; c.lineCap = 'round'; c.lineJoin = 'round'; c.stroke();
      // hover that follows the line
      c.save(); c.setLineDash([3, 9]); c.lineWidth = 2.5; c.strokeStyle = 'rgba(11,11,15,0.35)'; c.beginPath(); c.moveTo(head[0], CH.yt - 30); c.lineTo(head[0], CH.yb + 70); c.stroke(); c.restore();
      c.fillStyle = '#0b0b0f'; c.beginPath(); c.arc(head[0], head[1], 10, 0, 6.2832); c.fill(); c.fillStyle = '#fff'; c.beginPath(); c.arc(head[0], head[1], 4.5, 0, 6.2832); c.fill();
      const v = COPY.chartValue * CH.at(ff)[1] / 0.96, lab = v >= 1e6 ? '$' + (v / 1e6).toFixed(1) + 'M' : '$' + Math.round(v / 1000) + 'K';
      const tw = 150, tx = clamp(head[0] - tw / 2, CH.x0, CH.x1 - tw), ty = head[1] - 86, ta = O(t, T.count0 + 0.08, 0.3);
      A(c, ta, () => { shadow(c, tx, ty, tw, 54, 14, 0.6); rr(c, tx, ty, tw, 54, 14); c.fillStyle = '#0b0b0f'; c.fill(); text(c, lab, tx + tw / 2, ty + 37, F(600, 27), '#fff', 'center'); });
    }
  });
  c.restore();
}
function floodAndCta(c, t, m) {
  const f = G(t, T.flood, 0.8);
  if (f > 0 && t < T.cta + 0.8) { c.save(); rr(c, m.x0, m.y0, m.w, m.h, m.r); c.clip(); c.fillStyle = '#000'; c.beginPath(); c.arc(CH.end[0], CH.end[1], f * 1500, 0, 6.2832); c.fill(); c.restore(); }
  const a = G(t, T.cta + 0.46, 0.36) * (1 - G(t, T.ctaClick + 0.03, 0.28));
  if (a > 0) A(c, a, () => {
    const font = F(600, 52), w = measure(c, COPY.cta, font, -1), x = m.x - (w + 70) / 2;
    text(c, COPY.cta, x, m.y + 18, font, '#fff', 'left', -1);
    arrow(c, x + w + 48, m.y + 1, 36, '#fff', 5.5);
  });
}

/* ───────── inside world ───────── */
const LINE_END_HOLD = { a: T.count1 - 0.002, b: T.count1 - 0.001, x: CH.end[0], y: CH.end[1] };
const START = CH.xy(CH.P2[0]);
const CUR = [
  { a: P + 0.12, b: T.click1 - 0.06, x: 792, y: 760 }, { a: T.send - 0.88, b: T.send - 0.08, x: CX + 595 - 88, y: CY + 12 }, { a: T.send + 0.12, b: T.send + 0.92, x: 1580, y: 1330 },
  { a: T.tap - 1.0, b: T.tap - 0.1, x: 772, y: 884 }, { a: T.card + 0.63, b: T.card + 1.34, x: meetRect(2).x + 118, y: meetRect(2).y + 40 },
  { a: T.chart + 0.08, b: T.chart + 0.73, x: START[0], y: START[1] }, LINE_END_HOLD,
  { a: T.cta + 0.08, b: T.cta + 0.98, x: 912, y: 764 }, { a: T.ctaClick + 0.11, b: T.ctaClick + 0.89, x: 1580, y: 1560 },
];
const PUR = [{ a: T.pour + 0.17, b: T.pour + 0.77, x: 1030, y: 812 }, { a: T.sent - 0.6, b: T.sent - 0.08, x: SEND_BTN[0] + 74, y: SEND_BTN[1] + 22 }];

function drawInside(c, t, tf) {
  c.globalAlpha = 1; c.filter = 'none';
  drawBG(c, IM, t);
  // the black of the period lifting off the night as the iris opens
  if (t < 3) { const k = 1 - smooth((irisR(t) - R0) / 300); if (k > 0) { c.fillStyle = `rgba(0,0,0,${k})`; c.fillRect(0, 0, W, H); } }
  // open: two lines through one mask line
  if (t < 4.2) roll(c, t, [{ s: COPY.line1, tIn: T.line1, tOut: T.line2 }, { s: COPY.line2, tIn: T.line2, tOut: T.linesOut }], CX, 478, 104, F(700, 104), '#fff', 'center', -4);
  drawGrid(c, t, tf);
  nightExtras(c, t);

  if (t >= T.pill) {
    const m = mState(t), spawn = O(t, T.pill, 0.45);
    const goo = drawGoo(c, t);
    if (goo) islandContent(c, t, m);               // the island's label fades in while the pills are still merging
    else A(c, spawn, () => {
      if (m.col[3] < 0.995) glass(c, t, m.x0, m.y0, m.w, m.h, m.r, { rim: 1 - G(t, T.black, T.split - T.black) });   // the rim goes dark with the orb
      else shadow(c, m.x0, m.y0, m.w, m.h, m.r, 1);
      if (m.col[3] > 0) { rr(c, m.x0, m.y0, m.w, m.h, m.r); c.fillStyle = `rgba(${m.col[0] | 0},${m.col[1] | 0},${m.col[2] | 0},${m.col[3]})`; c.fill(); }
      if (t < T.send + 0.6) askContent(c, t, tf, m);
      else if (t < T.sent + 0.6) mailContent(c, t, tf, m);
      if (t > T.sent && t < T.split) orbContent(c, t, tf, m);
      if (t >= GOO1 && t < T.phone + 0.4) islandContent(c, t, m);
      if (t >= T.phone && t < T.card + 0.8) phoneContent(c, t, m);
      if (t >= T.card && t < T.chart + 0.4) calContent(c, t, m);
      if (t >= T.chart && t < T.cta + 0.4) chartContent(c, t, tf, m);
      if (t >= T.flood) floodAndCta(c, t, m);
    });
  }
  // cursors
  let [x, y] = path(t, [1580, 1300], CUR);
  if (t >= T.count0 && t <= T.count1) [x, y] = CH.xy(CH.at(chartF(t)));
  const dip = 1 - 0.13 * (bump(t, T.click1) + bump(t, T.send) + bump(t, T.tap) + bump(t, T.ctaClick));
  pointer(c, x, y, '#0b0b0f', dip);
  if (t > T.pour && t < T.sent + 0.7) {
    const [px, py] = path(t, [1620, 960], PUR), s = (1 - 0.13 * bump(t, T.sent)) * (1 - G(t, T.sent + 0.16, 0.4));
    if (s > 0.01) pointer(c, px, py, '#7B5CFF', s, COPY.name);
  }
}

/* ───────── outside world: daytime, black wordmark ───────── */
const RMAX = 1032;
function irisR(t) {
  if (t <= T.irisOpen) return R0;
  if (t < MID) return Math.sqrt(lerp(R0 * R0, RMAX * RMAX, G(t, T.irisOpen)));
  return Math.sqrt(lerp(RMAX * RMAX, R0 * R0, G(t, T.irisClose)));      // eased by area, not radius
}
let WORD = null;
function drawOutside(c, t) {
  c.globalAlpha = 1; c.drawImage(IM.day, 0, 0);
  const q = t < MID ? G(t, T.lettersIn) : 1 - G(t, T.lettersOut);         // 0 = wordmark, 1 = just the period
  const font = F(700, 136), ls = -5.5, gap = 7;
  if (!WORD) WORD = measure(c, COPY.name, font, ls);
  const total = WORD + gap + 2 * R0, pxRest = CX - total / 2 + WORD + gap + R0, px = lerp(pxRest, CX, q);
  if (q < 1) {
    c.save(); c.beginPath(); c.rect(0, 0, px, H); c.clip();
    text(c, COPY.name, px - R0 - gap - WORD + q * (WORD + gap + R0), CY + R0, font, '#0b0b0f', 'left', ls);
    c.restore();
  }
  c.fillStyle = '#0b0b0f'; c.beginPath(); c.arc(px, CY, R0, 0, 6.2832); c.fill();
  // tagline through its own mask line
  const p = t < MID ? 1 - G(t, 0.08, 0.5 * WSLOW) : G(t, T.tagline, ROLL);
  if (p > 0) { c.save(); c.beginPath(); c.rect(0, CY + 62, W, 52); c.clip(); stext(c, COPY.tagline, CX, CY + 100 + (1 - p) * 52, F(500, 37), '#0b0b0f', 'center', -0.4); c.restore(); }
  // the end card's call to action: a black "scan now ->" pill that rises after the tagline
  const cp = t < MID ? 1 - G(t, 0.04, 0.5 * WSLOW) : G(t, T.tagline + 0.12, ROLL);
  if (cp > 0) A(c, cp, () => {
    const font = F(600, 37), tw = Math.ceil(measure(c, COPY.endCta, font, -0.6)), w = tw + 150, h = 88, x = Math.round(CX - w / 2), y = CY + 156 + (1 - cp) * 36;
    shadow(c, x, y, w, h, 44, 0.75); rr(c, x, y, w, h, 44); c.fillStyle = '#0b0b0f'; c.fill();
    stext(c, COPY.endCta, x + 50, y + 57, font, '#fff', 'left', -0.6);
    arrow(c, x + 50 + tw + 34, y + 45, 28, '#fff', 4.5);
  });
}

function seek(t, tf = t) {
  t = ((t % DUR) + DUR) % DUR; tf = ((tf % DUR) + DUR) % DUR;
  const R = irisR(t), open = t > T.irisOpen && t < T.irisClosed;
  ctx.globalAlpha = 1; ctx.filter = 'none';
  if (!open || R < RMAX - 1) drawOutside(ctx, t);
  if (open) {
    drawInside(ictx, t, tf);
    ctx.save(); ctx.beginPath(); ctx.arc(CX, CY, R, 0, 6.2832); ctx.clip(); ctx.drawImage(inner, 0, 0); ctx.restore();
    if (R < RMAX - 1 && R > R0 + 3) { ctx.save(); ctx.strokeStyle = `rgba(255,255,255,${0.5 * smooth((R - R0) / 40)})`; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(CX, CY, R - 1, 0, 6.2832); ctx.stroke(); ctx.restore(); }
  }
}

window.T = T; window.DUR = DUR; window.seek = seek;
window.ready = (async () => {
  await Promise.all([document.fonts.load(F(700, 100)), document.fonts.load(F(500, 40)), document.fonts.load(F(600, 40)), document.fonts.load(FM(500, 30)), document.fonts.load(FM(600, 30))]);
  for (const n of ['day', 'dawn', 'night']) { IM[n] = await loadImg(n); BL[n] = blurred(IM[n], 30); }
  PILLW = COPY.results.map(s => Math.ceil(measure(ctx, s, F(600, 48), -0.8)) + 146 + 62);
  seek(0);
  return true;
})();

// preview: ?t=12.3 shows a still, otherwise it plays on a loop
window.ready.then(() => {
  const q = new URLSearchParams(location.search);
  if (q.has('t')) return seek(parseFloat(q.get('t')));
  if (q.has('still')) return;
  const t0 = performance.now(); const tick = now => { seek(((now - t0) / 1000) % DUR); requestAnimationFrame(tick); }; requestAnimationFrame(tick);
});
