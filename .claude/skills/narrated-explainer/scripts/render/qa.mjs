// Objective QA for a rendered video. It cannot judge how the video sounds or feels: say so in your report.
// Usage: node qa.mjs --work WORKDIR [--video name] [--sheet SECONDS_PER_TILE (default 21)]
// Reports duration, loudness, silent gaps mapped to timeline units, and writes out/sheet.png (a contact sheet of the
// whole video) so you can look at every part of it with one image read.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : undefined; };
if (!arg('--work')) { console.error('usage: qa.mjs --work DIR [--video name] [--sheet S]'); process.exit(2); }
const WORK = path.resolve(arg('--work')), OUT = path.join(WORK, 'out');
const video = path.join(OUT, `${arg('--video') || 'video'}.mp4`);
const tl = JSON.parse(fs.readFileSync(path.join(WORK, 'timeline.json'), 'utf8'));
const ff = (args) => spawnSync('ffmpeg', ['-hide_banner', '-nostats', ...args], { encoding: 'utf8' }).stderr;
const report = { video, issues: [] };

report.durationSec = +execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', video], { encoding: 'utf8' }).trim();
if (Math.abs(report.durationSec - tl.duration) > 1) report.issues.push(`duration ${report.durationSec}s differs from timeline ${tl.duration}s`);

const vol = ff(['-i', video, '-af', 'volumedetect', '-vn', '-f', 'null', '-']);
report.meanVolumeDb = +(vol.match(/mean_volume: (-?[\d.]+)/)?.[1] ?? NaN);
report.maxVolumeDb = +(vol.match(/max_volume: (-?[\d.]+)/)?.[1] ?? NaN);
if (report.meanVolumeDb < -23) report.issues.push(`audio is quiet (mean ${report.meanVolumeDb} dB)`);
if (report.maxVolumeDb > -0.5) report.issues.push(`audio peaks near clipping (${report.maxVolumeDb} dB)`);

const sil = ff(['-i', video, '-af', 'silencedetect=n=-45dB:d=1.0', '-vn', '-f', 'null', '-']);
const gaps = [...sil.matchAll(/silence_end: ([\d.]+) \| silence_duration: ([\d.]+)/g)].map((m) => ({ start: +m[1] - +m[2], dur: +m[2] }));
report.silentGaps = gaps.filter((g) => g.dur > 2.3).map((g) => {
  const sc = tl.scenes.find((s) => g.start + 0.01 >= s.start && g.start < s.start + s.duration);
  return { at: +g.start.toFixed(1), seconds: +g.dur.toFixed(1), unit: sc?.id };
});
report.gapsOver1s = gaps.length;
for (const g of report.silentGaps) if (g.seconds > 3.2) report.issues.push(`long silence ${g.seconds}s at ${g.at}s in ${g.unit}`);

const every = Number(arg('--sheet') || 21);
const cols = 5, rows = Math.max(1, Math.min(6, Math.ceil(report.durationSec / every / cols)));
const sheet = path.join(OUT, 'sheet.png');
const step = Math.max(every, report.durationSec / (cols * rows));
execFileSync('ffmpeg', ['-y', '-v', 'error', '-i', video, '-vf', `fps=1/${step.toFixed(2)},scale=384:-1,tile=${cols}x${rows}`, '-frames:v', '1', sheet]);
report.contactSheet = sheet; report.contactSheetSecondsPerTile = +step.toFixed(1);
report.notChecked = 'How it sounds (pronunciation, voice, pacing) and whether the on-screen content reads well: a person must watch it.';
fs.writeFileSync(path.join(OUT, 'qa-report.json'), JSON.stringify(report, null, 1));
console.log(JSON.stringify(report, null, 1));
