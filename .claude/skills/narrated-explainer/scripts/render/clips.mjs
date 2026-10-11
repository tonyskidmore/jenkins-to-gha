// Build the live-footage clips listed in scenes.json "clips" and extract their frames for the player.
// Usage: node clips.mjs --script scenes.json --work WORKDIR [--only NAME]
//   "clips": { "<name>": { "capture": "capture/jenkins", "trimStart": s, "trimEnd": s, "segments": "a-b:x,...", "crop": "W:H:X:Y", "scale": W } }
//   "mask": [{ "box": [x, y, w, h], "why": "account name" }]   filled boxes (fractions of the clip frame) that the cutter
//   draws into every frame: footage shows what the page showed, including names the video must not (anonymise, see SKILL.md).
// "capture" is a screen capture made by the hyperframes-walkthrough skill (hfw capture jenkins|gha --work WORKDIR), relative
// to the work dir or absolute; the other fields are that skill's edit format (its references/capture-and-edit.md).
// Writes WORKDIR/clips/<name>.mp4 + .map.json (every capture event with its clip time) and WORKDIR/clips/<name>/NNNNN.jpg.
// The player shows one extracted frame per output frame, so a render is deterministic and needs no video decoding.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { CLIP_FPS, clipPaths, captureDir } from './clip-lib.mjs';

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : undefined; };
if (!arg('--script') || !arg('--work')) { console.error('usage: clips.mjs --script scenes.json --work DIR [--only NAME]'); process.exit(2); }
const script = JSON.parse(fs.readFileSync(path.resolve(arg('--script')), 'utf8'));
const work = path.resolve(arg('--work'));
if ((script.meta?.fps ?? 30) !== CLIP_FPS) { console.error(`clips are cut at ${CLIP_FPS} fps; meta.fps is ${script.meta.fps}`); process.exit(1); }

// The cutter belongs to the hyperframes-walkthrough skill, which also makes the captures.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const cutter = path.resolve(HERE, '../../../hyperframes-walkthrough/scripts/build-clip.mjs');
if (!fs.existsSync(cutter)) { console.error(`clip cutter not found: ${cutter} (the hyperframes-walkthrough skill provides it)`); process.exit(1); }
const { buildClip } = await import(pathToFileURL(cutter).href);

const clips = Object.entries(script.clips ?? {}).filter(([name]) => !arg('--only') || arg('--only') === name);
if (!clips.length) { console.log('no clips in the script'); process.exit(0); }
for (const [name, spec] of clips) {
  const cap = captureDir(work, spec), p = clipPaths(work, name);
  if (!fs.existsSync(path.join(cap, 'timeline.json'))) { console.error(`${name}: no capture in ${cap} (make one with hfw capture ... --work ${work})`); process.exit(1); }
  const map = buildClip(cap, p.mp4, spec);
  fs.rmSync(p.frames, { recursive: true, force: true }); fs.mkdirSync(p.frames, { recursive: true });
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', p.mp4, '-q:v', '2', '-start_number', '0', path.join(p.frames, '%05d.jpg')]);
  const count = fs.readdirSync(p.frames).filter((f) => f.endsWith('.jpg')).length;
  const [width, height] = execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', p.mp4], { encoding: 'utf8' }).trim().split(',').map(Number);
  fs.writeFileSync(p.info, JSON.stringify({ count, fps: CLIP_FPS, width, height }));
  console.log(`[clip] ${name}: ${map.total.toFixed(2)} s, ${count} frames ${width}x${height}${spec.mask?.length ? `, ${spec.mask.length} mask(s)` : ''} -> ${path.relative(process.cwd(), p.mp4)}`);
  for (const e of map.events) {
    const what = e.job || e.stage || e.name || e.message || e.result || e.conclusion || '';
    console.log(`  ${e.clip_t.toFixed(2).padStart(6)}s  ${e.event}${what ? '  ' + what : ''}`);
  }
}
