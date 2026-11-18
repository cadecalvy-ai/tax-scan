// Renders stills of the film at given times.  node stills.cjs name=time name=time ...
// Needs playwright-core and sharp on NODE_PATH; uses the installed Chrome.
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright-core');
const sharp = require('sharp');

const root = __dirname;
const types = { '.html': 'text/html', '.js': 'text/javascript', '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.mp3': 'audio/mpeg', '.png': 'image/png' };
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0].replace(/^\/+/, '')) || 'index.html');
  if (!p.startsWith(root) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': types[path.extname(p)] || 'application/octet-stream' }); fs.createReadStream(p).pipe(res);
});

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  const shots = process.argv.slice(2).filter(a => a.includes('=')).map(a => a.split('='));
  const outDir = path.join(root, 'stills'); fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1440 }, deviceScaleFactor: 1 });
  page.on('console', m => console.log('[page]', m.text())); page.on('pageerror', e => console.log('[pageerror]', e.message));
  await page.goto(`http://127.0.0.1:${port}/index.html?still=1`);
  await page.evaluate(() => window.ready);
  const tiles = [];
  for (const [name, t] of shots) {
    const url = await page.evaluate(tt => { window.seek(tt); return document.getElementById('c').toDataURL('image/png'); }, parseFloat(t));
    const buf = Buffer.from(url.split(',')[1], 'base64');
    if (!name.startsWith('_')) fs.writeFileSync(path.join(outDir, name + '.png'), buf);
    tiles.push({ name, t, buf: await sharp(buf).resize(480, 480).jpeg({ quality: 82 }).toBuffer() });
  }
  const cols = 3, rows = Math.ceil(tiles.length / cols);
  for (let s = 0; s * 6 < tiles.length; s++) {
    const part = tiles.slice(s * 6, s * 6 + 6), r = Math.ceil(part.length / cols);
    await sharp({ create: { width: cols * 480, height: r * 480, channels: 3, background: '#000' } })
      .composite(part.map((x, i) => ({ input: x.buf, left: (i % cols) * 480, top: Math.floor(i / cols) * 480 }))).jpeg({ quality: 85 })
      .toFile(path.join(outDir, `_sheet${s + 1}.jpg`));
  }
  console.log('done', tiles.map(x => `${x.name}@${x.t}`).join(' '), rows);
  await browser.close(); server.close();
})();
