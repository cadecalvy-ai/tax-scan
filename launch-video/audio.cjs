// Builds the soundtrack: the song enters on its hit at the first pill, and every event gets a
// sound effect placed by its measured peak. The mix is levelled to -14 LUFS with the music at full level;
// SONG.level in timing.js then turns only the music down, leaving the effects where they were.
//   node audio.cjs <sfxDir> <out.wav>
const { spawnSync } = require('child_process'), fs = require('fs'), path = require('path');
const ffmpeg = require('ffmpeg-static');
const sfxDir = process.argv[2], out = process.argv[3];
const { P, T, DUR, SONG: SONGINFO } = require('./timing.js');
const SONG = path.join(__dirname, 'assets', SONGINFO.file), SONG_HIT = SONGINFO.hit;   // measured: where the hit is in the track

// name: [file id, what it is]
const S = { click: 1117, tap: 2580, type: 2531, swish: 3115, quick: 1464, wind: 1461, soft: 175, sweep: 166, air: 1489, vacuum: 2608,
            scan: 3114, slide: 3120, bubble: 2925, pop: 2358, msg: 2354, hardpop: 2364, tick: 2577, softtick: 1125, blip: 2568 };
// [sound, time the PEAK should land, volume, pitch rate]; times come from timing.js so sound follows any retime
const E = [
  ['quick', 0.62, 0.45], ['air', 1.45, 0.55], ['swish', 1.54, 0.5], ['swish', 2.5, 0.5],
  ['click', T.click1, 0.8], ['soft', T.click1 + 0.39, 0.9], ['click', T.send, 0.8], ['swish', T.send + 0.28, 0.6], ['slide', T.send + 0.57, 1.6],
  ['scan', T.scan0 + 0.5, 1.7], ['vacuum', T.pour + 0.33, 0.5],
  ['click', T.sent, 0.8], ['wind', T.sent + 0.16, 0.45],
  ['softtick', T.clock[0] + 0.15, 1.2], ['swish', T.sleepIn + 0.3, 0.4], ['softtick', T.clock[1] + 0.15, 1.2], ['softtick', T.clock[2] + 0.15, 1.2], ['softtick', T.clock[3] + 0.15, 1.2],
  ['bubble', T.split + 0.23, 0.5],
  ['pop', T.checks[0] + 0.04, 0.6, 1.0], ['pop', T.checks[1] + 0.04, 0.6, 1.12], ['pop', T.checks[2] + 0.04, 0.6, 1.26],
  ['quick', T.merge + 0.32, 0.45], ['soft', T.phone + 0.355, 0.9],
  ['msg', T.notif[0] + 0.08, 0.7, 1.0], ['msg', T.notif[1] + 0.08, 0.7, 1.06], ['msg', T.notif[2] + 0.08, 0.7, 1.12],
  ['tap', T.tap, 1.0], ['swish', T.tap + 0.3, 0.6], ['sweep', T.card + 0.34, 0.3],
  ['blip', T.hover + 0.08, 0.5], ['soft', T.chart + 0.33, 0.8], ['scan', T.count0 + 0.63, 1.6], ['air', T.flood + 0.33, 0.5],
  ['click', T.ctaClick, 0.8], ['swish', T.ctaClick + 0.29, 0.6], ['vacuum', T.irisClose + 0.45, 0.5], ['quick', T.lettersOut + 0.36, 0.45],
  ['slide', T.tagline + 0.2, 1.4], ['pop', T.tagline + 0.5, 0.3, 0.9],
];
for (let i = 0; i < 10; i++) E.push(['hardpop', T.meet0 + i * 0.082 + 0.1, 0.22, 1 + (i % 4) * 0.06]);   // meetings popping in
for (let i = 0; i < 7; i++) E.push(['tick', T.scan0 + 0.12 + i * 0.125, 0.16]);                          // scan counter
for (let i = 0; i < 9; i++) E.push(['tick', T.count0 + 0.08 + i * 0.105, 0.16, 1 + i * 0.03]);           // chart count-up
const TYPING = [[T.type0, T.type1 - T.type0, 1.2, 0.5], [T.type2a, T.type2b - T.type2a, 6.4, 0.5]];      // [start, length, offset in file, volume]

// The repeating tick effects (scan counter, chart count-up, clock chip) are left out by default.
// MUTE= node audio.cjs ...  brings them back; MUTE=pop,msg ... leaves other sounds out.
const MUTE = (process.env.MUTE ?? 'tick,softtick').split(',').filter(Boolean);
for (let i = E.length - 1; i >= 0; i--) if (MUTE.includes(E[i][0])) E.splice(i, 1);
if (MUTE.length) console.log('muted:', MUTE.join(', '));

function peakOf(file) {                                  // seconds to the loudest 5ms window
  const r = spawnSync(ffmpeg, ['-v', 'quiet', '-i', file, '-ac', '1', '-ar', '48000', '-f', 's16le', '-'], { maxBuffer: 1 << 28 });
  const a = new Int16Array(r.stdout.buffer, r.stdout.byteOffset, r.stdout.length >> 1), hop = 240; let best = 0, at = 0;
  for (let i = 0; i + hop <= a.length; i += hop) { let s = 0; for (let k = 0; k < hop; k++) s += a[i + k] * a[i + k]; if (s > best) { best = s; at = i; } }
  return at / 48000;
}
const peaks = {}; for (const [k, id] of Object.entries(S)) peaks[k] = peakOf(path.join(sfxDir, id + '.mp3'));
console.log('measured peaks', JSON.stringify(peaks));

const inputs = [], chains = [], labels = [];
const add = (file, chain) => { const n = inputs.length / 2; inputs.push('-i', file); chains.push(`[${n}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,${chain}[a${n}]`); labels.push(`[a${n}]`); };
const delay = s => `adelay=${Math.round(s * 1000)}:all=1`;
// the song plays so its hit lands on the first pill: trimmed if the hit is later in the track than P, delayed if earlier
const lead = SONG_HIT - P;
add(SONG, (lead >= 0 ? `atrim=start=${lead.toFixed(4)},asetpts=PTS-STARTPTS,afade=t=in:d=0.3` : delay(-lead)) + `,volume=@@SONGVOL@@,afade=t=out:st=${(DUR - 1.7).toFixed(2)}:d=1.6`);
for (const [name, at, vol, rate = 1] of E) {
  const start = at - peaks[name] / rate, trim = start < 0 ? -start : 0;
  add(path.join(sfxDir, S[name] + '.mp3'), `asetrate=${Math.round(48000 * rate)},aresample=48000,atrim=start=${trim.toFixed(3)},asetpts=PTS-STARTPTS,volume=${vol},${delay(Math.max(0, start))}`);
}
for (const [start, len, off, vol] of TYPING)
  add(path.join(sfxDir, S.type + '.mp3'), `atrim=start=${off}:duration=${len.toFixed(3)},asetpts=PTS-STARTPTS,afade=t=in:d=0.03,afade=t=out:st=${(len - 0.06).toFixed(2)}:d=0.06,volume=${vol},${delay(start)}`);
const mix = `${chains.join(';')};${labels.join('')}amix=inputs=${labels.length}:normalize=0:duration=longest,apad,atrim=0:${DUR},alimiter=limit=0.84:attack=3:release=60:level=false`;

const LEVEL = SONGINFO.level ?? 1;
const run = (level, extra, outArgs) => spawnSync(ffmpeg, ['-y', '-hide_banner', ...inputs, '-filter_complex', mix.replace('@@SONGVOL@@', (SONGINFO.volume * level).toFixed(4)) + extra, ...outArgs], { encoding: 'utf8', maxBuffer: 1 << 26 });
const p1 = run(1, ',loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json[o]', ['-map', '[o]', '-f', 'null', '-']);
const m = JSON.parse(p1.stderr.slice(p1.stderr.lastIndexOf('{'), p1.stderr.lastIndexOf('}') + 1));
console.log('before loudnorm: I', m.input_i, 'TP', m.input_tp, 'LRA', m.input_lra);
const gain = Math.min(-14 - parseFloat(m.input_i), -1.0 - parseFloat(m.input_tp));      // the same gain a linear loudnorm would apply
console.log(`gain ${gain.toFixed(2)} dB; music level ${Math.round(LEVEL * 100)}%`);
const p2 = run(LEVEL, `,volume=${gain.toFixed(3)}dB,aresample=48000[o]`, ['-map', '[o]', '-c:a', 'pcm_s24le', out]);
if (p2.status !== 0) { console.log(p2.stderr.slice(-2000)); process.exit(1); }
const chk = spawnSync(ffmpeg, ['-hide_banner', '-i', out, '-af', 'ebur128=peak=true', '-f', 'null', '-'], { encoding: 'utf8', maxBuffer: 1 << 26 });
console.log(chk.stderr.slice(chk.stderr.lastIndexOf('Summary:')));
console.log(`events: ${E.length} effects + ${TYPING.length} typing beds + song`);
