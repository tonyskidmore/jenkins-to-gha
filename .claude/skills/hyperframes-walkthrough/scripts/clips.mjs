#!/usr/bin/env node
// hfw clips --project P --work W [--only NAME]
// Builds every clip in P/edit.json from W/capture/<capture>/ into W/site/assets/clips/<name>.mp4 (+ .map.json) and prints
// each event's clip time: the composition's GSAP times are <video data-start> + these clip times.
//
// edit.json: { "clips": { "<name>": { "capture": "jenkins"|"gha", "trimStart": s, "trimEnd": s,
//                                      "segments": "a-b:x,...", "crop": "W:H:X:Y", "scale": W,
//                                      "mask": [{ "box": [x, y, w, h], "why": "..." }] } } }   (see build-clip.mjs)
import fs from 'node:fs';
import path from 'node:path';
import { args } from './lib.mjs';
import { buildClip } from './build-clip.mjs';

const a = args();
if (!a.project || !a.work) { console.error('usage: hfw clips --project P --work W [--only NAME]'); process.exit(2); }
const edit = JSON.parse(fs.readFileSync(path.join(a.project, 'edit.json'), 'utf8'));
for (const [name, spec] of Object.entries(edit.clips || {})) {
  if (a.only && a.only !== name) continue;
  const cap = path.resolve(a.work, 'capture', spec.capture);
  if (!fs.existsSync(path.join(cap, 'timeline.json'))) { console.error(`${name}: no capture in ${cap} (hfw capture ${spec.capture} ...)`); process.exit(1); }
  const out = path.resolve(a.work, 'site', 'assets', 'clips', `${name}.mp4`);
  const map = buildClip(cap, out, spec);
  console.log(`[clip] ${path.relative(process.cwd(), out)}: ${map.total.toFixed(2)}s`);
  for (const e of map.events) {
    const what = e.job || e.stage || e.name || e.message || e.result || e.conclusion || '';
    console.log(`  ${e.clip_t.toFixed(2).padStart(6)}s  ${e.event}${what ? '  ' + what : ''}`);
  }
}
