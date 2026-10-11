// Lint scenes.json before spending any time on audio. Errors exit 1; warnings are advice.
// Usage: node check-script.mjs --script scenes.json
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { loadClip, clipTime, captureDir } from './clip-lib.mjs';

const i = process.argv.indexOf('--script');
if (i < 0) { console.error('usage: check-script.mjs --script scenes.json'); process.exit(2); }
const scriptPath = path.resolve(process.argv[i + 1]);
const dir = path.dirname(scriptPath);
let script;
try { script = JSON.parse(fs.readFileSync(scriptPath, 'utf8')); } catch (e) { console.error('ERROR: not valid JSON:', e.message); process.exit(1); }

const errors = [], warns = [];
const workDir = process.argv.includes('--work') ? path.resolve(process.argv[process.argv.indexOf('--work') + 1]) : null;
const KINDS = ['title', 'disclaimer', 'explainer', 'section', 'summary', 'flow', 'filestack', 'compare', 'steps', 'cmdlist', 'screenshot', 'clip', 'terminal'];
const meta = script.meta ?? {};
if (!meta.voice?.voice) warns.push('meta.voice.voice missing (defaults to bf_emma / lang_code b)');
let pron = { phonemes: {}, respell: {} };
const pp = path.resolve(dir, meta.pronunciations ?? 'pronunciations.json');
if (fs.existsSync(pp)) pron = { phonemes: {}, respell: {}, ...JSON.parse(fs.readFileSync(pp, 'utf8')) };
else warns.push(`no pronunciations file at ${pp} (fine for a first draft; the audio step will audit dropped words)`);
const known = new Set([...Object.keys(pron.phonemes), ...Object.keys(pron.respell)].map((s) => s.toLowerCase()));

for (const [k, c] of Object.entries(script.clips ?? {})) {
  if (!c?.capture) { errors.push(`clip ${k}: "capture" (the hfw capture dir, relative to the work dir) is required`); continue; }
  for (const m of c.mask ?? []) if (!(Array.isArray(m?.box) && m.box.length === 4 && m.box.every((n) => n >= 0 && n <= 1))) errors.push(`clip ${k}: mask needs {box:[x,y,w,h] as fractions 0..1}`);
  if (workDir && !fs.existsSync(path.join(captureDir(workDir, c), 'timeline.json'))) warns.push(`clip ${k}: no capture at ${captureDir(workDir, c)} (hfw capture ... --work ${workDir})`);
}
const caps = {};
for (const [k, v] of Object.entries(script.captures ?? {})) {
  const f = path.resolve(dir, typeof v === 'string' ? v : v.file);
  if (!fs.existsSync(f)) { errors.push(`capture ${k}: file not found: ${f}`); continue; }
  const txt = fs.readFileSync(f, 'utf8');
  caps[k] = (txt.match(/^@@CMD@@ /gm) || []).length;
  if (/\p{Extended_Pictographic}/u.test(txt.replace(/[✓✗✔✘•→←↑↓▶▼►●○◆■□★☆]/gu, ''))) warns.push(`capture ${k}: contains emoji; machines without an emoji font draw them as empty boxes. Pick a command that avoids them (e.g. awk -F'|' to select columns) rather than editing the text`);
  const longCmds = txt.split('\n').filter((l) => l.startsWith('@@CMD@@ ') && l.length - 8 > 100).length;
  if (longCmds) warns.push(`capture ${k}: ${longCmds} command(s) over 100 characters: they wrap on screen. Shorten them with a silent setup line (variables or a helper function defined before the first step) and keep the shown command readable`);
  const longLines = txt.split('\n').filter((l) => l.length > 110).length;
  if (longLines) warns.push(`capture ${k}: ${longLines} line(s) over 110 characters wrap onto several screen lines (about 70 fit) and push earlier lines out of view; select columns/ranges with awk, cut or sed`);
  if (caps[k] !== (txt.match(/^@@END@@ /gm) || []).length) errors.push(`capture ${k}: @@CMD@@/@@END@@ markers do not pair up`);
}

// Leak scan: things that identify the user or machine must not be in files that may be tracked or shown.
{
  const files = [scriptPath, pp, ...Object.values(script.captures ?? {}).map((v) => path.resolve(dir, typeof v === 'string' ? v : v.file))];
  const capDir = path.join(dir, 'captures');
  if (fs.existsSync(capDir)) for (const f of fs.readdirSync(capDir)) if (/\.(sh|txt|json)$/.test(f)) files.push(path.join(capDir, f));
  const names = new Set();
  try { const url = spawnSync('git', ['-C', dir, 'remote', 'get-url', 'origin'], { encoding: 'utf8' }).stdout.trim(); const m = url.match(/[:/]([^/:]+)\/([^/]+?)(\.git)?$/); if (m) { names.add(m[1]); names.add(m[2]); } } catch {}
  names.add(path.basename(process.env.HOME ?? ''));
  // a name that is the subject of the video (in the title) or listed in meta.allowedNames is not a leak
  const subject = `${meta.title ?? ''} ${meta.chip ?? ''} ${(meta.allowedNames ?? []).join(' ')}`.toLowerCase();
  for (const n of [...names]) if (subject.includes(String(n).toLowerCase())) names.delete(n);
  const pats = [[/\/home\/[a-z_][\w-]*\//, 'home path'], [/\/Users\/[\w-]+\//, 'home path'], [/gh[pousr]_[A-Za-z0-9]{20,}/, 'GitHub token'], [/[A-Za-z0-9][\w.+-]*@[A-Za-z0-9-]+\.[A-Za-z]{2,}/, 'email address']];
  for (const n of names) if (n && n.length > 2) pats.push([new RegExp(n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'), `"${n}" (account/repo/user name)`]);
  const seen = new Set();
  for (const f of [...new Set(files)]) {
    if (!fs.existsSync(f) || /redact\.txt$/.test(f)) continue;
    const txt = fs.readFileSync(f, 'utf8');
    for (const [re, what] of pats) if (re.test(txt) && !seen.has(f + what)) { seen.add(f + what); warns.push(`possible leak: ${what} in ${path.relative(dir, f)}`); }
  }
}
const ids = new Set();
let words = 0, units = 0;
const need = (cond, msg) => { if (!cond) errors.push(msg); };
function narrationChecks(where, text, limit = 45) {
  if (!text || !text.trim()) { errors.push(`${where}: empty narration`); return; }
  const w = text.trim().split(/\s+/).length; words += w; units++;
  if (w > limit) warns.push(`${where}: ${w} words (aim for under ${limit}${limit > 45 ? ' for this scene kind' : ' per terminal beat'})`);
  const bad = new Set();
  for (const tok of text.split(/\s+/)) {
    const t = tok.replace(/^[("'\[]+|[)"'\].,;:!?]+$/g, '');
    if (!t || known.has(t.toLowerCase())) continue;
    if (/\d/.test(t)) bad.add(`${t} (digits: write the words, e.g. "fifty-one")`);
    else if (/[_/\\=<>{}|*#@]/.test(t)) bad.add(`${t} (code-like: show it on screen, say it in words)`);
    else if (/[a-z][A-Z]/.test(t)) bad.add(`${t} (camelCase: add phonemes/respell)`);
    else if (/^[A-Z]{2,}s?$/.test(t)) bad.add(`${t} (acronym: add phonemes or respell as spaced letters)`);
  }
  if (bad.size) warns.push(`${where}: TTS-unfriendly: ${[...bad].join('; ')}`);
}
for (const s of script.scenes ?? []) {
  const where = `scene ${s.id}`;
  if (!s.id) { errors.push('scene without id'); continue; }
  if (ids.has(s.id)) errors.push(`${where}: duplicate id`); ids.add(s.id);
  if (!KINDS.includes(s.kind)) errors.push(`${where}: unknown kind "${s.kind}" (known: ${KINDS.join(', ')})`);
  if (!s.source && !s.note) warns.push(`${where}: no "source"/"note": record which doc/section/capture backs the claims`);
  if (s.kind === 'terminal') {
    need(Array.isArray(s.beats) && s.beats.length, `${where}: terminal scenes need "beats"`);
    for (const [k, b] of (s.beats ?? []).entries()) {
      const cap = b.capture || s.capture;
      if (!(cap in caps)) { errors.push(`${where} beat ${k + 1}: unknown capture "${cap}"`); continue; }
      need(Array.isArray(b.steps) && b.steps.length, `${where} beat ${k + 1}: "steps" (indexes into the capture) required`);
      for (const st of b.steps ?? []) if (!(Number.isInteger(st) && st >= 0 && st < caps[cap])) errors.push(`${where} beat ${k + 1}: step ${st} not in capture ${cap} (has ${caps[cap]} commands)`);
      narrationChecks(`${where}.${k + 1}`, b.narration);
      for (const h of b.highlight ?? []) if (!(typeof h === 'string' || (h && h.text))) errors.push(`${where} beat ${k + 1}: highlight must be a string or {text, tone}`);
    }
  } else {
    narrationChecks(where, s.narration, 90);
    if (['flow', 'filestack', 'compare', 'steps', 'cmdlist', 'screenshot', 'clip'].includes(s.kind)) need(s.data, `${where}: kind ${s.kind} needs "data"`);
    if (s.kind === 'clip' && s.data) {
      const spec = script.clips?.[s.data.clip];
      if (!spec) errors.push(`${where}: clip "${s.data.clip}" is not defined in the top-level "clips"`);
      if (!s.data.url) warns.push(`${where}: clip has no data.url (the address-bar label: a string, or [{at, url}] to follow the footage)`);
      if (Array.isArray(s.data.url)) for (const u of s.data.url) if (!(u && u.url && u.at !== undefined)) errors.push(`${where}: url steps are {at, url}`);
      for (const a of s.data.callouts ?? []) if (!(a && a.label && a.at !== undefined)) errors.push(`${where}: callout needs {at, label} (at: clip seconds or a capture event)`);
      for (const z of s.data.zoom ?? []) if (!(z && z.at !== undefined && typeof z.scale === 'number')) errors.push(`${where}: zoom key needs {at, scale} (origin, dur optional)`);
      const c = workDir && spec && loadClip(workDir, s.data.clip);
      if (c) for (const x of [...(s.data.callouts ?? []), ...(s.data.zoom ?? []), ...(Array.isArray(s.data.url) ? s.data.url : [])]) { try { clipTime(c.map, x.at); } catch (e) { errors.push(`${where}: ${e.message}`); } }
      else if (workDir && spec) warns.push(`${where}: clip "${s.data.clip}" not built yet (nx clips), so its event names were not checked`);
    }
    if (s.kind === 'screenshot' && s.data) {
      const img = path.resolve(dir, s.data.image ?? '');
      if (!s.data.url) warns.push(`${where}: screenshot has no data.url (the address-bar label)`);
      if (!s.data.image || !fs.existsSync(img)) errors.push(`${where}: screenshot image not found: ${img}`);
      for (const a of s.data.annotations ?? []) if (!(Array.isArray(a.box) && a.box.length === 4 && a.box.every((n) => n >= 0 && n <= 1) && a.label)) errors.push(`${where}: annotation needs {box:[x,y,w,h] as fractions 0..1, label}`);
    }
    if (['title', 'disclaimer', 'explainer', 'section', 'summary'].includes(s.kind)) need(Array.isArray(s.onScreen) && s.onScreen.length, `${where}: kind ${s.kind} needs "onScreen"`);
    for (const it of Array.isArray(s.onScreen) ? s.onScreen : []) {
      if (typeof it === 'string') continue;
      const keys = Object.keys(it);
      if (s.kind === 'explainer' && !('v' in it)) errors.push(`${where}: explainer items are "text" or {k, v}; got keys ${keys.join(',')}`);
      if (s.kind === 'summary' && !('text' in it)) errors.push(`${where}: summary items are "text" or {text, tone}; got keys ${keys.join(',')}`);
      if (!['explainer', 'summary'].includes(s.kind)) errors.push(`${where}: onScreen items for kind ${s.kind} must be strings`);
    }
  }
}
const scenes = script.scenes?.length ?? 0;
const speech = words / 3.0, overhead = scenes * 1.4 + (units - scenes) * 0.45;   // Kokoro bf_emma speaks about 3 words/s (measured); scene lead/tail and beat gaps
console.log(`${scenes} scenes, ${units} narration units, about ${words} words: speech about ${(speech / 60).toFixed(1)} min; expect the finished video at about ${((speech + overhead) / 60).toFixed(1)} min`);
for (const [k, n] of Object.entries(caps)) { const f = path.resolve(dir, typeof script.captures[k] === 'string' ? script.captures[k] : script.captures[k].file); const bad = [...fs.readFileSync(f, 'utf8').matchAll(/^@@CMD@@ (.*)\n[\s\S]*?^@@END@@ rc=(\d+)/gm)].filter((m) => m[2] !== '0'); for (const m of bad) console.log(`INFO  capture ${k}: "${m[1].slice(0, 60)}" exited ${m[2]}: fine if that is the point, a bug if it is a quoting slip`); }
const wi = process.argv.indexOf('--work');
if (wi > 0) { try { const r = spawnSync('git', ['-C', dir, 'check-ignore', '-q', path.resolve(process.argv[wi + 1], 'x')]); if (r.status === 1) warns.push(`work dir is not git-ignored: add it to .gitignore so generated audio/video is not committed`); } catch {} }
for (const w of warns) console.log('WARN  ' + w);
for (const e of errors) console.log('ERROR ' + e);
console.log(errors.length ? `${errors.length} error(s)` : 'script OK');
process.exit(errors.length ? 1 : 0);
