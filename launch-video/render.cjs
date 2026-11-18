// Renders the film: 60fps, 4 motion-blur subframes per frame, piped straight into ffmpeg.
// Also writes a per-frame change metric so single-frame jumps can be found.
//   node render.cjs <out.mp4> <metrics.json> [firstFrame lastFrame]
// Needs playwright-core and ffmpeg-static on NODE_PATH; uses the installed Chrome.
const http = require('http'), fs = require('fs'), path = require('path'), { spawn } = require('child_process');
const { chromium } = require('playwright-core');
const ffmpeg = require('ffmpeg-static');

const FPS = 60, SUB = 4, SHUTTER = 0.5, { DUR } = require('./timing.js');       // shutter = fraction of the frame the blur spans
const root = __dirname, out = process.argv[2], metricsPath = process.argv[3];
const f0 = parseInt(process.argv[4] ?? '0'), f1 = parseInt(process.argv[5] ?? String(Math.round(FPS * DUR)));
const types = { '.html': 'text/html', '.js': 'text/javascript', '.jpg': 'image/jpeg', '.woff2': 'font/woff2' };
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0].replace(/^\/+/, '')) || 'index.html');
  if (!p.startsWith(root) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': types[path.extname(p)] || 'application/octet-stream' }); fs.createReadStream(p).pipe(res);
});

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1440 }, deviceScaleFactor: 1 });
  page.on('pageerror', e => console.log('[pageerror]', e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/index.html?still=1`);
  await page.evaluate(() => window.ready);
  await page.evaluate(({ SUB, SHUTTER, FPS }) => {
    const src = document.getElementById('c');
    const acc = document.createElement('canvas'); acc.width = acc.height = 1440; const a = acc.getContext('2d');
    const sm = document.createElement('canvas'); sm.width = sm.height = 144; const s = sm.getContext('2d', { willReadFrequently: true });
    let prev = null;
    window.renderFrame = async i => {
      const t = i / FPS;
      for (let k = 0; k < SUB; k++) {                    // running average of the subframes
        window.seek(t + (k / SUB) * SHUTTER / FPS, t);   // counters read the frame's time
        a.globalAlpha = 1 / (k + 1); a.drawImage(src, 0, 0);
      }
      a.globalAlpha = 1;
      s.drawImage(acc, 0, 0, 144, 144);
      const d = s.getImageData(0, 0, 144, 144).data; let mean = 0, bmax = 0;
      if (prev) {
        const blocks = new Float32Array(144);
        for (let y = 0; y < 144; y++) for (let x = 0; x < 144; x++) {
          const o = (y * 144 + x) * 4, v = Math.abs(d[o] - prev[o]) + Math.abs(d[o + 1] - prev[o + 1]) + Math.abs(d[o + 2] - prev[o + 2]);
          mean += v; blocks[((y / 12) | 0) * 12 + ((x / 12) | 0)] += v;
        }
        mean /= 144 * 144 * 3; for (const b of blocks) bmax = Math.max(bmax, b / (144 * 3));
      }
      prev = d.slice();
      const blob = await new Promise(r => acc.toBlob(r, 'image/png'));
      const url = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(blob); });
      return { png: url.slice(url.indexOf(',') + 1), mean, bmax };
    };
  }, { SUB, SHUTTER, FPS });

  const ff = spawn(ffmpeg, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '13',
    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const metrics = [], started = Date.now();
  if (f0 > 0) await page.evaluate(i => window.renderFrame(i), f0 - 1);          // prime the metric
  for (let i = f0; i < f1; i++) {
    const r = await page.evaluate(n => window.renderFrame(n), i);
    metrics.push({ i, t: +(i / FPS).toFixed(4), mean: +r.mean.toFixed(3), bmax: +r.bmax.toFixed(3) });
    if (!ff.stdin.write(Buffer.from(r.png, 'base64'))) await new Promise(r2 => ff.stdin.once('drain', r2));
    if (i % 120 === 0) console.log(`frame ${i}/${f1}  ${((Date.now() - started) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end(); await new Promise(r => ff.on('close', r));
  fs.writeFileSync(metricsPath, JSON.stringify(metrics));
  console.log('done', out, ((Date.now() - started) / 1000).toFixed(0) + 's');
  await browser.close(); server.close();
})();
