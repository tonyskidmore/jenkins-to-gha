// Frame-capture renderer: headless Chrome (puppeteer-core + the system Chrome) -> ffmpeg. No video framework.
// Usage: node render.mjs --work WORKDIR                 -> WORKDIR/out/video.mp4
//        node render.mjs --work WORKDIR --stills 3,28   -> WORKDIR/out/still_<t>.png for visual QA (no video)
//        --out NAME  (default "video")   --fps N (override)
//        --scale N   draw at N times the pixel density (deviceScaleFactor): 2 gives a 3840x2160 video from the 1920x1080
//                    layout, with sharp text (YouTube encodes 1440p and 4K uploads at a much higher quality). Default 1.
//        --jobs N    render N slices of the frames in parallel (one Chrome each) and join them losslessly; about 2x faster
//                    with 3 on 8 cores; default 1. Slices are byte-different from a one-job render but visually the same.
// Every frame is a pure function of t (player.js renderAt). Frames whose DOM is identical to the previous frame are
// not re-captured, which makes static scenes cheap.
import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import os from 'node:os';

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : undefined; };
if (!arg('--work')) { console.error('usage: render.mjs --work DIR [--stills t1,t2] [--out name]'); process.exit(2); }
const HERE = path.dirname(fileURLToPath(import.meta.url));
const NX_HOME = process.env.NX_HOME || path.join(process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache'), 'narrated-explainer');
const puppeteer = createRequire(path.join(NX_HOME, 'package.json'))('puppeteer-core');   // installed by `nx setup`
const WORK = path.resolve(arg('--work')), OUT = path.join(WORK, 'out'); fs.mkdirSync(OUT, { recursive: true });
const tl = JSON.parse(fs.readFileSync(path.join(WORK, 'timeline.json'), 'utf8'));
const fps = Number(arg('--fps') || tl.fps);
const stills = arg('--stills')?.split(',').map(Number);
const scale = Math.max(1, Math.min(Number(arg('--scale') || 1), 3));

const chrome = [process.env.CHROME_PATH, 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'].filter(Boolean)
  .map((c) => { try { return c.includes('/') ? c : execFileSync('which', [c], { encoding: 'utf8' }).trim(); } catch { return null; } }).find(Boolean);
if (!chrome) { console.error('No Chrome/Chromium found; set CHROME_PATH'); process.exit(1); }

const browser = await puppeteer.launch({
  executablePath: chrome, headless: true,
  args: ['--no-sandbox', '--hide-scrollbars', '--force-color-profile=srgb', '--font-render-hinting=none'],   // --no-sandbox: needed on some WSL2/container setups
});
const page = await browser.newPage();
await page.setViewport({ width: tl.width, height: tl.height, deviceScaleFactor: scale });
await page.goto(pathToFileURL(path.join(HERE, '../player/index.html')).href);
await page.evaluate(() => document.fonts.ready);
await page.evaluate((t) => window.setTimeline(t), tl);
const imagesReady = () => page.evaluate(() => Promise.all([...document.images].map((i) => (i.complete ? 1 : new Promise((r) => { i.onload = i.onerror = r; })))));

if (stills) {
  for (const t of stills) {
    await page.evaluate((x) => window.renderAt(x), t); await imagesReady();
    const f = path.join(OUT, `still_${String(t).replace('.', '_')}.png`);
    await page.screenshot({ path: f }); console.log('wrote', f);
  }
  await browser.close(); process.exit(0);
}

const total = Math.ceil(tl.duration * fps);
const encode = (args, out) => spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-', ...args,
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', ...out], { stdio: ['pipe', 'inherit', 'inherit'] });
async function capture(ff, from, to, tag = '') {
  const done = new Promise((res, rej) => { ff.on('close', (c) => (c === 0 ? res() : rej(new Error('ffmpeg exit ' + c)))); });
  const t0 = Date.now();
  let lastHtml = null, lastBuf = null, shots = 0;
  for (let f = from; f < to; f++) {
    const html = await page.evaluate((x) => window.renderAt(x), f / fps);
    if (html !== lastHtml) { await imagesReady(); lastBuf = await page.screenshot({ type: 'jpeg', quality: 92 }); lastHtml = html; shots++; }
    if (!ff.stdin.write(lastBuf)) await new Promise((r) => ff.stdin.once('drain', r));
    if ((f - from) % 900 === 0) console.log(`${tag}frame ${f}/${total}  screenshots ${shots}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end(); await done;
  return { shots, secs: (Date.now() - t0) / 1000 };
}
if (arg('--slice')) {
  const [from, to, ...rest] = arg('--slice').split(':'), file = rest.join(':');
  const r = await capture(encode([], ['-an', file]), Number(from), Number(to), `[${from}-${to}] `);
  await browser.close(); console.log(`slice ${from}-${to}: ${r.shots} screenshots, ${r.secs.toFixed(0)}s`); process.exit(0);
}

// 1) narration track: pad each unit's wav to its length (delayed by audioOffset), then concatenate
const tmp = path.join(OUT, 'audio_parts'); fs.mkdirSync(tmp, { recursive: true });
const list = [];
for (const sc of tl.scenes) {
  const out = path.join(tmp, `${sc.id}.wav`), ms = Math.round(sc.audioOffset * 1000);
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-i', path.join(WORK, 'audio', sc.audioFile), '-af',
    `adelay=${ms}|${ms},apad=whole_dur=${sc.duration}`, '-ar', '48000', '-ac', '1', out]);
  list.push(`file '${out}'`);
}
fs.writeFileSync(path.join(tmp, 'list.txt'), list.join('\n'));
const narration = path.join(OUT, 'narration.wav');
execFileSync('ffmpeg', ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', path.join(tmp, 'list.txt'), '-c', 'copy', narration]);

// 2) video: capture frames, pipe to ffmpeg with the narration (loudness normalised to about -16 LUFS)
const video = path.join(OUT, `${arg('--out') || 'video'}.mp4`);
const mux = ['-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', '48000', '-c:a', 'aac', '-b:a', '160k', '-shortest', video];
const jobs = Math.max(1, Math.min(Number(arg('--jobs') || 1), 8));
const t0 = Date.now();
let shots = 0;
if (jobs === 1) {
  ({ shots } = await capture(encode(['-i', narration], mux), 0, total));
  await browser.close();
} else {
  // N workers render slices of the frames (each its own Chrome, all pure functions of t), then one lossless join + mux
  await browser.close();
  const parts = [...Array(jobs).keys()].map((i) => ({ from: Math.floor((total * i) / jobs), to: Math.floor((total * (i + 1)) / jobs), file: path.join(tmp, `slice${i}.mp4`) }));
  const self = fileURLToPath(import.meta.url);
  await Promise.all(parts.map((p) => new Promise((res, rej) => {
    const c = spawn(process.execPath, [self, '--work', WORK, '--fps', String(fps), '--scale', String(scale), '--slice', `${p.from}:${p.to}:${p.file}`], { stdio: ['ignore', 'pipe', 'inherit'] });
    c.stdout.on('data', (d) => { const m = String(d).match(/slice \d+-\d+: (\d+) screenshots/); if (m) shots += +m[1]; process.stdout.write(d); });
    c.on('close', (code) => (code === 0 ? res() : rej(new Error(`slice ${p.from}-${p.to} failed (${code})`))));
  })));
  fs.writeFileSync(path.join(tmp, 'slices.txt'), parts.map((p) => `file '${p.file}'`).join('\n'));
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', path.join(tmp, 'slices.txt'), '-i', narration, '-c:v', 'copy', ...mux]);
}
console.log(`wrote ${video}  (${tl.width * scale}x${tl.height * scale}, ${total} frames, ${shots} screenshots, ${((Date.now() - t0) / 1000).toFixed(0)}s${jobs > 1 ? `, ${jobs} jobs` : ''})`);
