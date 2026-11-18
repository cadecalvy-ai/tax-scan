// Builds the soundtrack: the song enters on its hit at the first pill, and every event gets a
// sound effect placed by its measured peak. Two-pass loudnorm to -14 LUFS.
//   node audio.cjs <sfxDir> <out.wav>
const { spawnSync } = require('child_process'), fs = require('fs'), path = require('path');
const ffmpeg = require('ffmpeg-static');
const sfxDir = process.argv[2], out = process.argv[3];
const DUR = 24, P = 2.8, BEAT = 0.4626, g = k => P + 0.265 + (k - 1) * BEAT;
const SONG = path.join(__dirname, 'assets', 'song.mp3'), SONG_HIT = 1.845;     // measured: the hit is 1.845s into the track

// name: [file id, what it is]
const S = { click: 1117, tap: 2580, type: 2531, swish: 3115, quick: 1464, wind: 1461, soft: 175, sweep: 166, air: 1489, vacuum: 2608,
            scan: 3114, slide: 3120, bubble: 2925, pop: 2358, msg: 2354, hardpop: 2364, tick: 2577, softtick: 1125, blip: 2568 };
// [sound, time the PEAK should land, volume, pitch rate]
const E = [
  ['quick', 0.62, 0.45], ['air', 1.45, 0.55], ['swish', 1.54, 0.5], ['swish', 2.5, 0.5],
  ['click', g(2), 0.8], ['soft', 3.92, 0.9], ['click', g(6), 0.8], ['swish', 5.66, 0.6], ['slide', 5.95, 1.6],
  ['scan', 6.72, 1.7], ['vacuum', 7.56, 0.5],
  ['click', g(13), 0.8], ['wind', 8.78, 0.45],
  ['softtick', 9.3, 1.2], ['swish', 9.8, 0.4], ['softtick', 10.05, 1.2], ['softtick', 10.52, 1.2], ['softtick', 10.98, 1.2],
  ['bubble', 11.45, 0.5],
  ['pop', 11.90, 0.6, 1.0], ['pop', 12.02, 0.6, 1.12], ['pop', 12.14, 0.6, 1.26],
  ['quick', 13.1, 0.45], ['soft', 14.06, 0.9],
  ['msg', 14.58, 0.7, 1.0], ['msg', 14.74, 0.7, 1.06], ['msg', 14.90, 0.7, 1.12],
  ['tap', g(28), 1.0], ['swish', 15.86, 0.6], ['sweep', 16.36, 0.3],
  ['blip', 17.46, 0.5], ['soft', 18.2, 0.8], ['scan', 19.25, 1.6], ['air', 20.05, 0.5],
  ['click', g(40), 0.8], ['swish', 21.4, 0.6], ['vacuum', 22.0, 0.5], ['quick', 22.66, 0.45], ['slide', 23.2, 1.4], ['pop', 23.5, 0.3, 0.9],
];
for (let i = 0; i < 10; i++) E.push(['hardpop', 16.6 + i * 0.082 + 0.1, 0.22, 1 + (i % 4) * 0.06]);   // meetings popping in
for (let i = 0; i < 7; i++) E.push(['tick', 6.34 + i * 0.125, 0.16]);                                 // scan counter
for (let i = 0; i < 9; i++) E.push(['tick', 18.7 + i * 0.105, 0.16, 1 + i * 0.03]);                   // chart count-up
const TYPING = [[4.0, 1.05, 1.2, 0.5], [7.68, 0.73, 6.4, 0.5]];                                      // [start, length, offset in file, volume]

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
add(SONG, `volume=0.85,${delay(P - SONG_HIT)},afade=t=out:st=22.3:d=1.6`);
for (const [name, at, vol, rate = 1] of E) {
  const start = at - peaks[name] / rate, trim = start < 0 ? -start : 0;
  add(path.join(sfxDir, S[name] + '.mp3'), `asetrate=${Math.round(48000 * rate)},aresample=48000,atrim=start=${trim.toFixed(3)},asetpts=PTS-STARTPTS,volume=${vol},${delay(Math.max(0, start))}`);
}
for (const [start, len, off, vol] of TYPING)
  add(path.join(sfxDir, S.type + '.mp3'), `atrim=start=${off}:duration=${len},asetpts=PTS-STARTPTS,afade=t=in:d=0.03,afade=t=out:st=${(len - 0.06).toFixed(2)}:d=0.06,volume=${vol},${delay(start)}`);
const mix = `${chains.join(';')};${labels.join('')}amix=inputs=${labels.length}:normalize=0:duration=longest,apad,atrim=0:${DUR},alimiter=limit=0.84:attack=3:release=60:level=false`;

const run = (extra, outArgs) => spawnSync(ffmpeg, ['-y', '-hide_banner', ...inputs, '-filter_complex', mix + extra, ...outArgs], { encoding: 'utf8', maxBuffer: 1 << 26 });
const p1 = run(',loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json[o]', ['-map', '[o]', '-f', 'null', '-']);
const m = JSON.parse(p1.stderr.slice(p1.stderr.lastIndexOf('{'), p1.stderr.lastIndexOf('}') + 1));
console.log('before loudnorm: I', m.input_i, 'TP', m.input_tp, 'LRA', m.input_lra);
const p2 = run(`,loudnorm=I=-14:TP=-1.0:LRA=11:measured_I=${m.input_i}:measured_TP=${m.input_tp}:measured_LRA=${m.input_lra}:measured_thresh=${m.input_thresh}:offset=${m.target_offset}:linear=true,aresample=48000[o]`,
  ['-map', '[o]', '-c:a', 'pcm_s24le', out]);
if (p2.status !== 0) { console.log(p2.stderr.slice(-2000)); process.exit(1); }
const chk = spawnSync(ffmpeg, ['-hide_banner', '-i', out, '-af', 'ebur128=peak=true', '-f', 'null', '-'], { encoding: 'utf8', maxBuffer: 1 << 26 });
console.log(chk.stderr.slice(chk.stderr.lastIndexOf('Summary:')));
console.log(`events: ${E.length} effects + ${TYPING.length} typing beds + song`);
