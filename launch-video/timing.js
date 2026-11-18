/* The film's one timing table, shared by the picture (scene.js) and the sound (audio.cjs).
   Beats are the song's: its first big impact lands on the first pill at P, and g(k) is the k-th beat after it.
   Song: Mixkit 224 "RnB", 100 BPM. The impact is 12.837s into the track and the downbeat follows 0.2s later. */
(function (root) {
  // volume balances the song against the effects when the mix is levelled; level then turns only the music down (1 = full)
  const SONG = { file: 'song.mp3', hit: 12.837, volume: 1.45, level: 0.39 };
  const P = 2.8, BEAT = 0.6, g = k => P + 0.2 + (k - 1) * BEAT;

  const sent = g(14), checks0 = g(20), split = checks0 - 0.64, black = split - 0.27;
  // the night scene's clock and sky ride on the email's send and stretch to end as the orb goes black
  const stretch = (black - sent) / (10.95 - 8.616), night = old => sent + (old - 8.616) * stretch;

  const T = {
    lettersIn: 0.25, irisOpen: 1.05, line1: 1.25, line2: 2.2, linesOut: 3.4,
    // ask: the job types in 1.2s, then stays up for about 1.3s before send
    pill: P, click1: g(2), type0: g(2) + 0.47, type1: g(2) + 1.67, send: g(7),
    // find
    ripple: g(7) + 0.242, scan0: g(7) + 0.82, scan1: g(7) + 1.8, pour: g(10),
    // write: the email types in 0.9s, then stays up for about a second before send
    type2a: g(10) + 0.45, type2b: g(10) + 1.35, sent,
    // night
    ring0: night(9.3), ring1: black + 0.05, clock: [sent + 0.4, sent + 0.95, sent + 1.5, sent + 2.05],
    sleepIn: night(9.5), sleepOut: black - 0.05, relight0: night(9.45), relight1: split + 0.13,
    // results: the checks pop on beat 20 and the three pills hold for about 1.6s
    black, split, checks: [checks0, checks0 + 0.12, checks0 + 0.24],
    // morning: "5 emails drafted" holds two beats (1.2s)
    merge: g(23), day0: g(23), phone: g(25), day1: g(25) + 0.8,
    notif: [g(25) + 0.8, g(25) + 0.96, g(25) + 1.12], tap: g(28), card: g(29),
    // proof
    meet0: g(29) + 0.58, hover: g(29) + 1.36, chart: g(32), count0: g(32) + 0.75, count1: g(32) + 1.75,
    flood: g(35), cta: g(35) + 0.2, ctaClick: g(38),
    // out
    irisClose: g(38) + 0.444, irisClosed: g(38) + 1.244, lettersOut: g(38) + 1.194, tagline: g(38) + 1.894,
  };
  const DUR = 28.2;                             // seconds; the last frame equals the first
  const TIMING = { P, BEAT, g, T, DUR, SONG };
  if (typeof module !== 'undefined' && module.exports) module.exports = TIMING; else root.TIMING = TIMING;
})(typeof window !== 'undefined' ? window : globalThis);
