#!/usr/bin/env node
// Live capture of a real GitHub Actions run of examples/NNN (self-hosted tier: JIT runners on this machine, no
// Actions minutes).
//
//   hfw capture gha --work W --example NNN [--mode trace|full]
//
// 1. Checks the GitHub capture profile is signed in (hfw gh-login).
// 2. Starts `uv run j2gha run NNN --tier selfhosted --mode M`; as soon as j2gha prints the run URL, opens the run page
//    and records it with a screenshot loop at 2x density (the CDP screencast only delivers CSS-pixel frames). Nothing
//    is recorded before the run page: the Actions list shows other runs and other repositories' names.
// 3. Polls the run and its jobs with `gh api` (every job transition becomes a timeline event) until the run completes,
//    reloads once so the final state is painted, and stops. j2gha's own output (verdict line) goes to j2gha.log.
//
// The browser is READ-ONLY: every non-GET/HEAD request is aborted (the profile is a real signed-in account) and the
// run is started from the terminal, never from the page. Avatars are hidden.
//
// Output: W/capture/gha/{frames/*.jpg, timeline.json, j2gha.log}. Starting the run pushes an orphan branch to the
// harness repository and creates a workflow run there: run this only with the user's approval for this run.
import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import { playwright, chromePath, GH_PROFILE, repoRoot, assertOutside, ghRepo, args, sleep } from '../lib.mjs';

const a = args();
if (!a.work || !a.example) { console.error('usage: hfw capture gha --work W --example NNN [--mode trace|full]'); process.exit(2); }
const EXAMPLE = String(a.example);
const MODE = a.mode || 'trace';
const ROOT = repoRoot();
assertOutside(GH_PROFILE, ROOT, 'profile');
const OUT = path.resolve(a.work, 'capture', 'gha');
const FRAMES = path.join(OUT, 'frames');

// GitHub's run page at 1600 CSS px; frames keep y 96..700 (title, job list, summary, graph) at 2x density.
const VIEWPORT = { width: 1600, height: 1000 };
const DSF = 2;
const CLIP = { x: 0, y: 96, width: 1600, height: 604 };
const MIN_FRAME_MS = 180;           // ~5 fps cap; a GitHub run is sped up ~10-15x in the video

const repo = ghRepo(ROOT);
const ghJson = (p) => JSON.parse(execFileSync('gh', ['api', p], { cwd: ROOT }).toString());
const HIDE_CSS = 'img.avatar, .avatar, .avatar-user, img[alt^="@"] { visibility: hidden !important; }';

async function main() {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(FRAMES, { recursive: true });

  const { chromium } = playwright();
  const ctx = await chromium.launchPersistentContext(GH_PROFILE, {
    executablePath: chromePath(), headless: true, viewport: VIEWPORT, deviceScaleFactor: DSF, colorScheme: 'dark',
    args: ['--no-sandbox', '--hide-scrollbars'],
  });
  const blocked = [];
  await ctx.route('**/*', (route) => {
    const m = route.request().method();
    if (m !== 'GET' && m !== 'HEAD') { blocked.push(`${m} ${route.request().url().slice(0, 100)}`); return route.abort(); }
    return route.continue();
  });
  await ctx.addInitScript((css) => {
    const add = () => { if (document.head && !document.getElementById('hfw-hide')) {
      const s = document.createElement('style'); s.id = 'hfw-hide'; s.textContent = css; document.head.appendChild(s); } };
    document.addEventListener('DOMContentLoaded', add); add();
  }, HIDE_CSS);
  const page = ctx.pages()[0] || await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);

  await page.goto(`https://github.com/${repo}`, { waitUntil: 'domcontentloaded' });
  const user = await page.locator('meta[name="user-login"]').getAttribute('content').catch(() => null);
  if (!user) throw new Error('capture profile is not signed in: run hfw gh-login');

  const frames = [];
  const events = [];
  const t0 = Date.now();
  const now = () => +((Date.now() - t0) / 1000).toFixed(3);
  const mark = (event, extra = {}) => {
    const t = now(); events.push({ t, event, ...extra });
    console.log(`[event] ${t.toFixed(2)}s ${event}${extra.job ? ' ' + extra.job : ''}${extra.conclusion ? ' ' + extra.conclusion : ''}`);
  };
  let recording = true;
  const record = async () => {
    while (recording) {
      const start = Date.now();
      try {
        const { data } = await cdp.send('Page.captureScreenshot', {
          format: 'jpeg', quality: 90, clip: { ...CLIP, scale: DSF }, captureBeyondViewport: false,
        });
        const file = `${String(frames.length).padStart(6, '0')}.jpg`;
        fs.writeFileSync(path.join(FRAMES, file), Buffer.from(data, 'base64'));
        frames.push({ file, t: +((start - t0) / 1000).toFixed(3) });
      } catch { /* page mid-navigation: skip this frame */ }
      const spent = Date.now() - start;
      if (spent < MIN_FRAME_MS) await sleep(MIN_FRAME_MS - spent);
    }
  };

  // Start the run from the terminal
  const log = fs.createWriteStream(path.join(OUT, 'j2gha.log'));
  const child = spawn('uv', ['run', 'j2gha', 'run', EXAMPLE, '--tier', 'selfhosted', '--mode', MODE],
    { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] });
  let runUrl = null, runId = null, childDone = false, childCode = null;
  const onLine = (buf) => {
    log.write(buf);
    for (const line of buf.toString().split('\n')) {
      const m = line.match(/run (\d+): (https:\/\/github\.com\/\S+\/actions\/runs\/\d+)/);
      if (m && !runUrl) { runId = m[1]; runUrl = m[2]; }
      if (/pushed j2gha\/run\//.test(line)) mark('pushed');
    }
  };
  child.stdout.on('data', onLine);
  child.stderr.on('data', onLine);
  child.on('exit', (code) => { childDone = true; childCode = code; });
  mark('j2gha-started');

  for (let i = 0; i < 240 && !runUrl && !childDone; i++) await sleep(500);
  if (!runUrl) throw new Error(`j2gha did not report a run URL (see ${path.join(OUT, 'j2gha.log')})`);
  mark('run-url', { runId });
  await page.goto(runUrl, { waitUntil: 'domcontentloaded' });
  const recorder = record();
  mark('run-page');

  const seen = {};
  let run = null;
  for (let i = 0; i < 900; i++) {
    run = ghJson(`/repos/${repo}/actions/runs/${runId}`);
    const jobs = ghJson(`/repos/${repo}/actions/runs/${runId}/jobs?per_page=100`).jobs || [];
    for (const j of jobs) {
      const state = j.status === 'completed' ? `completed:${j.conclusion}` : j.status;
      if (seen[j.name] !== state) {
        seen[j.name] = state;
        mark(`job-${j.status}`, { job: j.name, conclusion: j.conclusion || undefined });
      }
    }
    if (run.status === 'completed') break;
    await sleep(2000);
  }
  mark('run-completed', { conclusion: run.conclusion });
  await sleep(3000);
  await page.reload({ waitUntil: 'domcontentloaded' });
  mark('final-reload');
  await sleep(4000);
  mark('end');
  recording = false;
  await recorder;
  await ctx.close();

  for (let i = 0; i < 480 && !childDone; i++) await sleep(500);   // let j2gha finish its comparison
  log.end();

  const jobs = ghJson(`/repos/${repo}/actions/runs/${runId}/jobs?per_page=100`).jobs.map((j) => ({
    name: j.name, conclusion: j.conclusion, started_at: j.started_at, completed_at: j.completed_at }));
  const timeline = { kind: 'gha', example: EXAMPLE, mode: MODE, runId, runUrl, runNumber: run.run_number,
    conclusion: run.conclusion, run_started_at: run.run_started_at, updated_at: run.updated_at,
    viewport: VIEWPORT, dsf: DSF, clip: CLIP, frames, events, jobs, blocked_requests: blocked.length, j2gha_exit: childCode };
  fs.writeFileSync(path.join(OUT, 'timeline.json'), JSON.stringify(timeline, null, 1));
  console.log(`[done] run ${runId} (#${run.run_number}) ${run.conclusion}; ${jobs.length} jobs; ${frames.length} frames over ` +
    `${frames.at(-1)?.t}s; ${blocked.length} non-GET requests blocked; j2gha exit ${childCode}`);
  console.log(fs.readFileSync(path.join(OUT, 'j2gha.log'), 'utf8').split('\n').filter((l) => /->|EQUIVALENT|DIFFER|INCONCLUSIVE/.test(l)).join('\n'));
}

main().catch((e) => { console.error(e); process.exit(1); });
