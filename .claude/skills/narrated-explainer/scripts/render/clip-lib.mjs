// Live-footage clips for `clip` scenes: where nx clips writes them, how a clip time is named, and the speed labels.
// A clip is cut from a screen capture made by the hyperframes-walkthrough skill (hfw capture: frames/*.jpg + timeline.json)
// with that skill's build-clip.mjs, so both skills read the same captures and the same edit format.
import fs from 'node:fs';
import path from 'node:path';

export const CLIP_FPS = 30;   // build-clip.mjs writes 30 fps clips; the frame index is floor(clip time * 30)

export const clipPaths = (work, name) => {
  const dir = path.join(path.resolve(work), 'clips');
  return { mp4: path.join(dir, `${name}.mp4`), map: path.join(dir, `${name}.map.json`), frames: path.join(dir, name), info: path.join(dir, name, 'frames.json') };
};

// The capture directory of a clip spec: relative to the work dir (where hfw capture writes), or absolute.
export const captureDir = (work, spec) => path.resolve(path.resolve(work), spec.capture ?? '');

export function loadClip(work, name) {
  const p = clipPaths(work, name);
  if (!fs.existsSync(p.map) || !fs.existsSync(p.info)) return null;
  return { ...p, map: JSON.parse(fs.readFileSync(p.map, 'utf8')), info: JSON.parse(fs.readFileSync(p.info, 'utf8')), dir: p.frames };
}

// "at" names a moment of the clip: seconds of clip time, or a capture event: "event", "event:label" (label = the event's
// job, stage, name or message) and an optional "#n" for the n-th match (default the first).
export function clipTime(map, at) {
  if (typeof at === 'number') return at;
  const m = String(at).match(/^([^:#]+)(?::([^#]+))?(?:#(\d+))?$/);
  if (!m) throw new Error(`"${at}" is not seconds or event[:label][#n]`);
  const [, ev, label, nth] = m;
  const hits = map.events.filter((e) => e.event === ev && (!label || [e.job, e.stage, e.name, e.message].includes(label)));
  const hit = hits[(Number(nth) || 1) - 1];
  if (!hit) {
    const names = [...new Set(map.events.map((e) => e.event + (e.job || e.stage ? ':' + (e.job || e.stage) : '')))];
    throw new Error(`no event "${at}" in clip ${path.basename(map.source)} (has: ${names.slice(0, 12).join(', ')}${names.length > 12 ? ', ...' : ''})`);
  }
  return hit.clip_t;
}

// Speed labels from the clip's edit, so a sped-up stretch can never go unlabelled. A segment shorter than one frame
// is a cut: it is labelled "cut" for a moment instead.
export function speedLabels(map, fps = CLIP_FPS) {
  const { segments, trimStart, trimEnd } = map;
  const remap = (t) => {
    t = Math.min(Math.max(t, trimStart), trimEnd);
    let out = 0;
    for (const s of segments) { const a = Math.max(s.a, trimStart), b = Math.min(s.b, t); if (b > a) out += (b - a) / s.x; }
    return out;
  };
  const speed = [], cuts = [];
  for (const s of segments) {
    const a = Math.max(s.a, trimStart), b = Math.min(s.b, trimEnd);
    if (b <= a) continue;
    const from = remap(a), to = remap(b);
    if (to - from < 1 / fps) { cuts.push(+from.toFixed(3)); continue; }
    speed.push({ from: +from.toFixed(3), to: +to.toFixed(3), text: s.x === 1 ? '▶ real time' : s.x > 1 ? `▶▶ ${+s.x.toFixed(2)}× speed` : `▶ slowed to ${+s.x.toFixed(2)}×` });
  }
  return { speed, cuts };
}
