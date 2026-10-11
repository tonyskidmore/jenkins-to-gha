// Build WORK/timeline.json from scenes.json + WORK/audio/manifest.json + real terminal captures.
// Usage: node make-timeline.mjs --script scenes.json --work WORKDIR
// A scene with "beats" becomes one timeline unit per beat ("<scene>.<n>"); terminal beats continue the same screen.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { loadClip, clipTime, speedLabels } from './clip-lib.mjs';

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : undefined; };
const scriptPath = path.resolve(arg('--script') ?? ''), work = path.resolve(arg('--work') ?? '');
if (!arg('--script') || !arg('--work')) { console.error('usage: make-timeline.mjs --script scenes.json --work DIR'); process.exit(2); }
const script = JSON.parse(fs.readFileSync(scriptPath, 'utf8'));
const manifest = JSON.parse(fs.readFileSync(path.join(work, 'audio/manifest.json'), 'utf8'));
const meta = script.meta ?? {};

// Parse "@@CMD@@ cmd \n output \n@@END@@ rc=0 ms=123" blocks (real captures, never edited).
function parseCapture(file) {
  const txt = fs.readFileSync(path.resolve(path.dirname(scriptPath), file), 'utf8');
  const steps = [];
  for (const blk of txt.split('@@CMD@@ ').slice(1)) {
    const [head, ...rest] = blk.split('\n');
    const body = rest.join('\n');
    const m = body.match(/@@END@@ rc=(\d+) ms=(\d+)/);
    if (!m) throw new Error(`capture ${file}: block "${head}" has no @@END@@ line`);
    steps.push({ cmd: head.trim(), out: body.slice(0, m.index).split('\n').filter((l) => l !== ''), rc: +m[1], ms: +m[2] });
  }
  return steps;
}
const caps = {}, labels = {};
for (const [k, v] of Object.entries(script.captures ?? {})) {
  const c = typeof v === 'string' ? { file: v } : v;
  caps[k] = parseCapture(c.file); labels[k] = c.label ?? k;
}

// Caption words: prefer the narration's own words (keeps punctuation). The TTS speaks respelled terms ("Jenkinsfile" ->
// "Jenkins file") and splits hyphenated words, so align each narration token to the number of TTS tokens it produces
// and merge their timings. If the counts still disagree, fall back to the TTS tokens (no punctuation).
let respell = {};
{ const pf = path.resolve(path.dirname(scriptPath), meta.pronunciations ?? 'pronunciations.json');
  if (fs.existsSync(pf)) respell = JSON.parse(fs.readFileSync(pf, 'utf8')).respell ?? {}; }
const bareOf = (tok) => tok.replace(/^[("'\[]+|[)"'\].,;:!?]+$/g, '');
const count = (str, splitHyphen) => str.split(splitHyphen ? /[\s-]+/ : /\s+/).filter(Boolean).length || 1;
const COUNTERS = [                       // how many TTS tokens does one narration token become? tried in order
  () => 1,                                                              // 1:1 (hyphenated words kept whole)
  (t) => count(respell[bareOf(t)] ?? bareOf(t), false),                 // respelled terms become several words
  (t) => count(respell[bareOf(t)] ?? bareOf(t), true),                  // ...and hyphenated words are split too
];
function captionWords(narration, tts) {
  const toks = narration.split(/\s+/).filter(Boolean);
  for (const f of COUNTERS) {
    const need = toks.map(f);
    if (need.reduce((a, b) => a + b, 0) !== tts.length) continue;
    let i = 0;
    return toks.map((text, k) => { const a = tts[i], b = tts[i + need[k] - 1]; i += need[k]; return { text, start: a.start, end: b.end }; });
  }
  console.warn(`  caption words differ from TTS words (${toks.length} vs ${tts.length}); using TTS tokens (no punctuation)`);
  return tts;
}

// 1) flatten scenes to units
const units = [];
for (const s of script.scenes) {
  if (s.beats) {
    const prior = [];
    s.beats.forEach((b, k) => {
      const cap = b.capture || s.capture;
      if (!caps[cap]) throw new Error(`scene ${s.id}: unknown capture "${cap}"`);
      if (b.clear) prior.length = 0;               // new screen
      const steps = b.steps.map((i) => { if (!caps[cap][i]) throw new Error(`scene ${s.id} beat ${k + 1}: capture ${cap} has no step ${i}`); return caps[cap][i]; });
      units.push({ id: `${s.id}.${k + 1}`, group: s.id, kind: s.kind, narration: b.narration, part: b.part || s.part || labels[cap],
        steps, prior: prior.slice(), highlight: b.highlight || [], first: k === 0, last: k === s.beats.length - 1 });
      prior.push(...steps);
    });
  } else {
    let data = s.data;
    if (s.kind === 'screenshot') { const img = path.resolve(path.dirname(scriptPath), s.data.image); if (!fs.existsSync(img)) throw new Error(`scene ${s.id}: image not found: ${img}`); data = { ...s.data, imageUrl: pathToFileURL(img).href }; }
    if (s.kind === 'clip') {
      // live footage: one extracted frame per output frame; every time named by the script is resolved to clip seconds here
      const c = loadClip(work, s.data.clip);
      if (!c) throw new Error(`scene ${s.id}: clip "${s.data.clip}" not built; run: nx clips`);
      const at = (x) => { try { return clipTime(c.map, x); } catch (e) { throw new Error(`scene ${s.id}: ${e.message}`); } };
      const { speed, cuts } = speedLabels(c.map, c.info.fps);
      data = { ...s.data, frames: { dir: pathToFileURL(c.dir).href, count: c.info.count, fps: c.info.fps }, clipSec: c.map.total, speed, cuts,
        urls: Array.isArray(s.data.url) ? s.data.url.map((x) => ({ ...x, at: at(x.at) })) : [{ at: 0, url: s.data.url ?? '' }],
        callouts: (s.data.callouts ?? []).map((a) => ({ ...a, at: at(a.at) })), zoom: (s.data.zoom ?? []).map((z) => ({ ...z, at: at(z.at) })) };
      console.log(`  clip ${s.data.clip} in ${s.id}: ${c.map.total.toFixed(1)} s of footage; ${[...new Set(speed.map((x) => x.text))].join(', ')}${cuts.length ? `; ${cuts.length} cut(s)` : ''}`);
    }
    units.push({ id: s.id, group: s.id, kind: s.kind, narration: s.narration, onScreen: s.onScreen || [], data, title: s.title,
      first: true, last: true, part: s.kind === 'section' ? s.onScreen?.join(' · ') : s.part });
  }
}

// 2) times
let t = 0;
const scenes = [];
for (const u of units) {
  const au = manifest[u.id];
  if (!au) throw new Error(`missing audio for ${u.id}; run: nx audio`);
  const lead = u.first ? 0.5 : 0.15, tail = u.last ? 0.9 : 0.3;
  let duration = lead + au.durationSec + tail;
  const sc = { ...u, start: +t.toFixed(3), lead, audioFile: au.file, audioSec: au.durationSec, audioOffset: lead };
  if (u.kind === 'clip') {
    // the footage starts with the narration (or at data.start) and holds its last frame; the scene lasts for whichever is longer
    sc.data.clipStart = u.data.start ?? lead;
    const footageEnd = sc.data.clipStart + u.data.clipSec + (u.data.hold ?? 1.0);
    if (footageEnd - (lead + au.durationSec) > 2) console.warn(`  WARNING ${u.id}: footage runs ${(footageEnd - lead - au.durationSec).toFixed(1)} s past the narration (silence): narrate more, cut the clip, or lower data.start/hold`);
    duration = Math.max(duration, footageEnd);
  }
  if (u.kind === 'terminal') {
    // Sequential schedule: type each command, short run delay, output lines, gap. Spread over ~60% of the narration,
    // then stage the callouts. If the on-screen action outlasts the narration, centre the narration inside it.
    const TYPE = 40;
    let tt = lead + 0.15; const plan = [];
    for (const st of u.steps) {
      const typed = st.cmd.length / TYPE, run = Math.min(1.0, Math.max(0.15, (st.ms / 1000) * 0.5));
      plan.push({ t0: tt, tOut: tt + typed + 0.25 + run });
      tt += typed + 0.25 + run + st.out.length * 0.12 + 0.4;
    }
    const extra = Math.max(0, (0.6 * au.durationSec - (tt - lead - 0.15)) / u.steps.length);
    plan.forEach((p, i) => { p.t0 += extra * i; p.tOut += extra * i; });
    tt += extra * u.steps.length;
    const hlStart = tt + 0.1, hlGap = 0.8, n = u.highlight.length;
    Object.assign(sc, { plan, hlStart, hlGap, type: TYPE });
    const need = hlStart + n * hlGap + (u.last ? 1.2 : 0.5);
    if (need > duration) { sc.audioOffset = lead + (need - duration) * 0.5; duration = Math.max(need, sc.audioOffset + au.durationSec + tail); }
  }
  sc.words = captionWords(u.narration, au.words).map((w) => ({ ...w, start: +(w.start + sc.audioOffset).toFixed(3), end: +(w.end + sc.audioOffset).toFixed(3) }));
  sc.duration = +duration.toFixed(3);
  scenes.push(sc);
  t += duration;
}
const timeline = {
  fps: meta.fps ?? 30, width: meta.width ?? 1920, height: meta.height ?? 1080, duration: +t.toFixed(3),
  meta: { title: meta.title ?? '', chip: meta.chip ?? meta.title ?? '', prompt: meta.prompt ?? '$ ', replayLabel: meta.replayLabel ?? 'replay of real captured output',
    colour: meta.colour ?? null, lineIcons: meta.lineIcons !== false },
  scenes,
};
fs.mkdirSync(work, { recursive: true });
fs.writeFileSync(path.join(work, 'timeline.json'), JSON.stringify(timeline, null, 1));
console.log(`timeline: ${scenes.length} units, ${(timeline.duration / 60).toFixed(1)} min (${timeline.duration.toFixed(0)} s) -> ${path.join(work, 'timeline.json')}`);
