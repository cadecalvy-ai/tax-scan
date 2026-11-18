# tax scanner. launch film

A 24-second square film (1440×1440, 60fps) that loops. One HTML canvas; every frame is a pure function of
time, so `seek(t)` can draw any moment.

| File | What it is |
|---|---|
| `scene.js` | The whole film. Copy is in `COPY` at the top; all timing is in the `T` table below it |
| `index.html` | Open it through a local web server to play the film; add `?t=12.3` for a still |
| `render.cjs` | Renders 1440 frames with 4 motion-blur subframes each and pipes them into ffmpeg |
| `audio.cjs` | Builds the soundtrack: song on its hit at 2.8s, effects placed by measured peak, -14 LUFS |
| `stills.cjs` | Renders stills at chosen times |
| `diag.cjs` | Shows what changed on screen around a frame (for hunting single-frame jumps) |

## Re-rendering

```
npm install
npm run render      (video.mp4, silent, plus metrics.json for the jump scan)
npm run audio       (audio.wav)
ffmpeg -i video.mp4 -i audio.wav -c:v copy -c:a aac -b:a 256k tax-scanner-launch.mp4
```

Rendering uses the Chrome already installed on the PC. The web copy on the site is a 1080×1080 re-encode
saved to `app/src/web/launch.mp4`.

## Not in the repository

- `tax-scanner-launch.mp4`, the 25 MB master. The web copy is in `app/src/web/`.
- `assets/song.mp3` and `assets/sfx/`. They are Mixkit files and are not redistributed here. `audio.cjs` lists
  the effect ids; download each from `https://assets.mixkit.co/active_storage/sfx/<id>/<id>-preview.mp3` into
  `assets/sfx/`, and the song from `https://assets.mixkit.co/music/77/77.mp3` to `assets/song.mp3`.

## Credits

- Photo: Unsplash, photo `1464822759023-fed622ff2c3b` (Unsplash licence). The dawn and night versions are
  graded from the same frame.
- Typeface: Geist and Geist Mono (SIL Open Font License).
- Music and sound effects: Mixkit (Mixkit licence, https://mixkit.co/license/).
- Client names, the email and every figure in the film are fictional.
