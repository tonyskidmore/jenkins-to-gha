// Turn a live capture (frames + real timestamps) into a constant-frame-rate MP4 clip for HyperFrames.
//
// Captures only have a frame when the page repainted (screencast) or every ~200 ms (screenshot loop), so each frame is
// held until the next one (ffmpeg concat demuxer with per-frame durations). Piecewise speeds compress waits while the
// interesting moments stay at real speed; a segment at 20-50x is shorter than one output frame, i.e. a cut.
//
//   spec = { trimStart, trimEnd, segments: "a-b:x,b-c:y", crop: "W:H:X:Y", scale: W, mask: [{ box: [x, y, w, h], why }] }
//   segments: source seconds a..b play at speed x ("0-6.5:1,6.5-30:4"); default: everything at 1x
//   mask: filled boxes (fractions of the cropped, scaled frame) drawn into every frame: footage shows what the page
//         showed, including names the video must not (account name, run number, commit id). `why` is for the reader.
//
// Writes the MP4 (H.264, yuv420p, 30 fps, no audio) and <name>.map.json: every capture event with its clip time.
// Also used by narrated-explainer (nx clips, for clip scenes): keep buildClip()'s signature and the map format stable.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

export function buildClip(capDir, outFile, spec = {}) {
  const tl = JSON.parse(fs.readFileSync(path.join(capDir, 'timeline.json'), 'utf8'));
  const endEvt = tl.events.find((e) => e.event === 'end');
  const trimStart = Number(spec.trimStart ?? 0);
  const trimEnd = Number(spec.trimEnd ?? (endEvt ? endEvt.t : tl.frames.at(-1).t + 1));
  const segments = spec.segments
    ? spec.segments.split(',').map((s) => { const [r, x] = s.split(':'); const [a, b] = r.split('-').map(Number); return { a, b, x: Number(x) }; })
    : [{ a: 0, b: Infinity, x: Number(spec.speed ?? 1) }];

  // source time -> output time (integral of 1/speed over the segments, after trimming)
  const remap = (t) => {
    t = Math.min(Math.max(t, trimStart), trimEnd);
    let out = 0;
    for (const s of segments) {
      const a = Math.max(s.a, trimStart), b = Math.min(s.b, t);
      if (b > a) out += (b - a) / s.x;
    }
    return out;
  };

  const frames = tl.frames.filter((f) => f.t <= trimEnd);
  let first = 0;
  for (let i = 0; i < frames.length; i++) if (frames[i].t <= trimStart) first = i;   // opening frame
  const use = frames.slice(first);
  const total = remap(trimEnd);

  const list = [];
  for (let i = 0; i < use.length; i++) {
    const start = remap(use[i].t);
    const end = i + 1 < use.length ? remap(use[i + 1].t) : total;
    const d = Math.max(end - start, 0);
    if (d <= 0 && i + 1 < use.length) continue;
    list.push(`file '${path.resolve(capDir, 'frames', use[i].file)}'`, `duration ${d.toFixed(4)}`);
  }
  list.push(`file '${path.resolve(capDir, 'frames', use.at(-1).file)}'`);   // the concat demuxer needs the last file again

  const listFile = path.join(capDir, 'concat.txt');
  fs.writeFileSync(listFile, list.join('\n') + '\n');
  fs.mkdirSync(path.dirname(path.resolve(outFile)), { recursive: true });
  const vf = ['fps=30', spec.crop && `crop=${spec.crop}`,
    spec.scale ? `scale=${spec.scale}:-2:flags=lanczos` : 'scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos',
    ...(spec.mask ?? []).map(({ box: [x, y, w, h] }) => `drawbox=x=iw*${x}:y=ih*${y}:w=iw*${w}:h=ih*${h}:color=0x3d4450:t=fill`),
    'format=yuv420p'].filter(Boolean).join(',');
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', listFile, '-vf', vf,
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-movflags', '+faststart', '-an', outFile], { stdio: 'inherit' });

  const map = { source: capDir, kind: tl.kind, total: +total.toFixed(3), segments, trimStart, trimEnd,
    capture: Object.fromEntries(Object.entries(tl).filter(([k]) => !['frames', 'events'].includes(k))),
    events: tl.events.map((e) => ({ ...e, clip_t: +remap(e.t).toFixed(3) })) };
  fs.writeFileSync(outFile.replace(/\.mp4$/, '.map.json'), JSON.stringify(map, null, 1));
  return map;
}
