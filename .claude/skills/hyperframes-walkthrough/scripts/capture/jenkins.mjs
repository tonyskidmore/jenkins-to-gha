#!/usr/bin/env node
// Live capture of a real Jenkins pipeline run on the local j2gha controller (`uv run j2gha jenkins up`).
//
// Own-job mode (a self-contained Jenkinsfile such as examples/000 or a twin examples/1NN; inputs answered ON CAMERA):
//   hfw capture jenkins --work W --jenkinsfile examples/000/Jenkinsfile --job inventory-service \
//       [--input CHANGE_TICKET=CHG-1234 ...] [--approve Deploy]
//   (Re)creates the job so the run is build #1. A job is only deleted if this skill created it (description marker),
//   unless --replace is given. Each pending `input` is opened, its parameters typed with a visible cursor and the
//   proceed button clicked (--approve names its label; default: the form's proceed button).
//
// Harness mode (any example the harness can run; the harness approves inputs itself, off camera):
//   hfw capture jenkins --work W --harness NNN [--mode trace|full]
//   Starts `uv run j2gha run NNN --tier jenkins --mode M` and records the new build of job ex-NNN-M. The run record it
//   writes is the harness's normal output for that example.
//
// Both record the Pipeline Overview (stages page) with a CDP screencast: a frame whenever the page repaints, each with
// its real timestamp. Output: W/capture/jenkins/{frames/*.jpg, timeline.json[, j2gha.log]}.
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { playwright, chromePath, repoRoot, args, sleep } from '../lib.mjs';

const a = args();
const usage = 'usage: hfw capture jenkins --work W (--jenkinsfile F --job NAME [--input K=V ...] [--approve LABEL] [--replace] | --harness NNN [--mode trace|full])';
if (!a.work || (!a.jenkinsfile && !a.harness)) { console.error(usage); process.exit(2); }
const ROOT = repoRoot();
const JENKINS = process.env.JENKINS_URL || 'http://127.0.0.1:18080';
const USER = process.env.JENKINS_USER || 'admin';
const PASS = process.env.JENKINS_PASS || 'j2gha-local-only';
const HARNESS = a.harness ? String(a.harness) : null;
const MODE = a.mode || 'full';
const JOB = HARNESS ? `ex-${HARNESS}-${MODE}` : a.job;
if (!JOB) { console.error(usage); process.exit(2); }
const INPUTS = Object.fromEntries([].concat(a.input || []).map((kv) => { const i = kv.indexOf('='); return [kv.slice(0, i), kv.slice(i + 1)]; }));
const MARKER = '[hyperframes-walkthrough]';
const OUT = path.resolve(a.work, 'capture', 'jenkins');
const FRAMES = path.join(OUT, 'frames');

// Viewport with the aspect of the composition's browser body (964x520 in the reference project). The screencast
// delivers CSS-pixel frames, so this is also the clip resolution.
const VIEWPORT = { width: Number(a.width || 1280), height: Number(a.height || 690) };

const authHeader = 'Basic ' + Buffer.from(`${USER}:${PASS}`).toString('base64');
let cookie = '';
let crumb = null;
async function jfetch(p, opts = {}) {
  const headers = { Authorization: authHeader, ...(opts.headers || {}) };
  if (cookie) headers.Cookie = cookie;
  if (crumb && opts.method && opts.method !== 'GET') headers[crumb.field] = crumb.value;
  const res = await fetch(JENKINS + p, { ...opts, headers, redirect: 'manual' });
  const sc = res.headers.get('set-cookie');
  if (sc) cookie = sc.split(';')[0];
  return res;
}
async function jjson(p) { const r = await jfetch(p); return r.ok ? r.json() : null; }
async function getCrumb() {
  const j = await jjson('/crumbIssuer/api/json');
  if (j) crumb = { field: j.crumbRequestField, value: j.crumb };
}

function jobConfigXml(script) {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  // ASCII-escape (the controller rejects raw non-ASCII job XML)
  const ascii = (s) => s.replace(/[^\x00-\x7f]/g, (c) => `&#${c.codePointAt(0)};`);
  return ascii(`<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <description>${MARKER} ${esc(JOB)}: ${esc(a.jenkinsfile)}</description>
  <keepDependencies>false</keepDependencies>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps">
    <script>${esc(script)}</script>
    <sandbox>true</sandbox>
  </definition>
  <disabled>false</disabled>
</flow-definition>`);
}

async function prepareOwnJob() {
  await getCrumb();
  const existing = await jjson(`/job/${encodeURIComponent(JOB)}/api/json?tree=description`);
  if (existing) {
    if (!(existing.description || '').startsWith(MARKER) && !a.replace) {
      throw new Error(`job ${JOB} exists and was not created by this skill; choose another --job or pass --replace`);
    }
    console.log(`[jenkins] deleting ${JOB} so the capture is build #1`);
    const d = await jfetch(`/job/${encodeURIComponent(JOB)}/doDelete`, { method: 'POST' });
    if (![200, 302].includes(d.status)) throw new Error(`delete failed: ${d.status}`);
  }
  const script = fs.readFileSync(path.resolve(ROOT, a.jenkinsfile), 'utf8');
  const c = await jfetch(`/createItem?name=${encodeURIComponent(JOB)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/xml' }, body: jobConfigXml(script),
  });
  if (c.status !== 200) throw new Error(`createItem failed: ${c.status} ${await c.text()}`);
  console.log(`[jenkins] created ${JOB} from ${a.jenkinsfile}`);
  return (await jjson(`/job/${encodeURIComponent(JOB)}/api/json?tree=nextBuildNumber`)).nextBuildNumber;
}

// Visible cursor and click ring (screenshots never include the OS cursor)
const CURSOR_JS = `
(() => {
  if (window.__hfwCursor) return;
  const install = () => {
    if (!document.body || document.getElementById('hfw-cursor')) return;
    const c = document.createElement('div');
    c.id = 'hfw-cursor';
    c.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24"><path d="M4 2l16 9.5-7 1.6-3.6 6.9z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: 'fixed', left: '-100px', top: '-100px', zIndex: 2147483647, pointerEvents: 'none',
      filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.45))' });
    document.body.appendChild(c);
    const ring = document.createElement('div');
    ring.id = 'hfw-click';
    Object.assign(ring.style, { position: 'fixed', width: '36px', height: '36px', borderRadius: '50%', zIndex: 2147483646,
      border: '3px solid rgba(245,158,11,.9)', pointerEvents: 'none', opacity: 0, transform: 'translate(-50%,-50%) scale(.4)' });
    document.body.appendChild(ring);
  };
  window.__hfwCursor = true;
  document.addEventListener('mousemove', (e) => {
    install();
    const c = document.getElementById('hfw-cursor');
    if (c) { c.style.left = (e.clientX - 3) + 'px'; c.style.top = (e.clientY - 2) + 'px'; }
  }, true);
  document.addEventListener('mousedown', (e) => {
    const r = document.getElementById('hfw-click');
    if (!r) return;
    r.style.transition = 'none'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    r.style.opacity = 1; r.style.transform = 'translate(-50%,-50%) scale(.4)';
    requestAnimationFrame(() => { r.style.transition = 'opacity 450ms ease-out, transform 450ms ease-out';
      r.style.opacity = 0; r.style.transform = 'translate(-50%,-50%) scale(1.6)'; });
  }, true);
  document.addEventListener('DOMContentLoaded', install);
})();`;

async function glide(page, locator, steps = 28) {
  const box = await locator.boundingBox();
  if (!box) throw new Error('target not visible');
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps });
}

async function main() {
  const up = await jfetch('/api/json');
  if (!up.ok) throw new Error(`Jenkins is not answering at ${JENKINS} (uv run j2gha jenkins up)`);
  let buildNo = HARNESS ? null : await prepareOwnJob();   // may refuse: keep any previous capture until it succeeds
  let before = null;
  if (HARNESS) {
    const j = await jjson(`/job/${JOB}/api/json?tree=lastBuild[number]`);
    before = j?.lastBuild?.number ?? null;
  }
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(FRAMES, { recursive: true });

  const { chromium } = playwright();
  const browser = await chromium.launch({ executablePath: chromePath(), headless: true });
  const context = await browser.newContext({ viewport: VIEWPORT, colorScheme: 'light' });
  await context.addInitScript(CURSOR_JS);
  const page = await context.newPage();
  await page.goto(`${JENKINS}/login`);
  await page.fill('input[name="j_username"]', USER);
  await page.fill('input[name="j_password"]', PASS);
  await Promise.all([page.waitForNavigation(), page.press('input[name="j_password"]', 'Enter')]);

  const cdp = await context.newCDPSession(page);
  const frames = [];
  const events = [];
  let t0 = null;
  const mark = (event, extra = {}) => {
    const t = Date.now() / 1000 - (t0 ?? Date.now() / 1000);
    events.push({ t: +t.toFixed(3), event, ...extra });
    console.log(`[event] ${t.toFixed(2)}s ${event}${extra.stage ? ' ' + extra.stage : ''}`);
  };
  cdp.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
    cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
    if (t0 === null) t0 = metadata.timestamp;
    const file = `${String(frames.length).padStart(6, '0')}.jpg`;
    fs.writeFileSync(path.join(FRAMES, file), Buffer.from(data, 'base64'));
    frames.push({ file, t: +(metadata.timestamp - t0).toFixed(3) });
  });

  let child = null, childDone = false, childCode = null;
  if (!HARNESS) {
    await page.goto(`${JENKINS}/job/${encodeURIComponent(JOB)}/`);
  } else {
    await page.goto(`${JENKINS}/`);
  }
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: VIEWPORT.width, maxHeight: VIEWPORT.height, everyNthFrame: 1 });
  await sleep(800);
  t0 = t0 ?? Date.now() / 1000;
  mark('start-page');

  if (!HARNESS) {
    const r = await jfetch(`/job/${encodeURIComponent(JOB)}/build?delay=0sec`, { method: 'POST' });
    if (![201, 302].includes(r.status)) throw new Error(`build trigger failed: ${r.status} (parameterised jobs need buildWithParameters)`);
    mark('build-triggered');
  } else {
    const log = fs.createWriteStream(path.join(OUT, 'j2gha.log'));
    child = spawn('uv', ['run', 'j2gha', 'run', HARNESS, '--tier', 'jenkins', '--mode', MODE], { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] });
    child.stdout.on('data', (b) => log.write(b));
    child.stderr.on('data', (b) => log.write(b));
    child.on('exit', (code) => { childDone = true; childCode = code; log.end(); });
    mark('j2gha-started');
    for (let i = 0; i < 1200 && !buildNo && !childDone; i++) {
      const j = await jjson(`/job/${JOB}/api/json?tree=lastBuild[number]`);
      const n = j?.lastBuild?.number ?? null;
      if (n !== null && n !== before) buildNo = n;
      else await sleep(250);
    }
    if (!buildNo) throw new Error(`no new build of ${JOB} appeared (see ${path.join(OUT, 'j2gha.log')})`);
    mark('build-started', { build: buildNo });
  }

  for (let i = 0; i < 120; i++) { if ((await jfetch(`/job/${encodeURIComponent(JOB)}/${buildNo}/api/json`)).ok) break; await sleep(250); }
  const stagesUrl = `${JENKINS}/job/${encodeURIComponent(JOB)}/${buildNo}/stages`;
  await page.goto(stagesUrl);
  mark('stages-page');

  // Follow the build; answer each input on camera (own-job mode) or just note it (harness mode)
  let result = null;
  const answered = new Set();
  for (let i = 0; i < 14400; i++) {
    const b = await jjson(`/job/${encodeURIComponent(JOB)}/${buildNo}/api/json?tree=building,result`);
    if (b && !b.building) { result = b.result; break; }
    const pending = await jjson(`/job/${encodeURIComponent(JOB)}/${buildNo}/wfapi/pendingInputActions`);
    const p = Array.isArray(pending) ? pending.find((x) => !answered.has(x.id)) : null;
    if (p) {
      answered.add(p.id);
      mark('input-pending', { id: p.id, message: p.message });
      if (!HARNESS) {
        await sleep(3500);                        // let the paused state be seen on the overview
        await page.goto(`${JENKINS}/job/${encodeURIComponent(JOB)}/${buildNo}/input/`);
        mark('input-page');
        await page.mouse.move(VIEWPORT.width * 0.55, VIEWPORT.height * 0.85);
        await sleep(700);
        for (const [name, value] of Object.entries(INPUTS)) {
          const field = page.locator(`div[name="parameter"]:has(input[name="name"][value="${name}"]) [name="value"]`).first();
          if (!(await field.count())) continue;
          await glide(page, field);
          await sleep(250);
          await field.click({ clickCount: 3 });
          await sleep(200);
          await page.keyboard.type(value, { delay: 110 });
          mark('input-typed', { name });
          await sleep(600);
        }
        let btn = a.approve ? page.getByRole('button', { name: a.approve, exact: true }) : page.locator('button[name="proceed"], input[name="proceed"]');
        if (!(await btn.count())) btn = page.locator('form button[type="submit"], form input[type="submit"]');
        await glide(page, btn.first());
        await sleep(450);
        mark('approve-click');
        await Promise.all([page.waitForLoadState('load').catch(() => {}), btn.first().click()]);
        await sleep(900);
        await page.goto(stagesUrl);
        mark('stages-after-approval');
      }
      continue;
    }
    await sleep(250);
  }
  mark('build-finished', { result });
  await sleep(2500);
  await page.reload();
  mark('final-reload');
  await sleep(2500);
  mark('end');
  await cdp.send('Page.stopScreencast');
  await sleep(300);
  await browser.close();
  if (child) for (let i = 0; i < 480 && !childDone; i++) await sleep(500);

  const version = (await jfetch('/api/json')).headers.get('x-jenkins');
  const timeline = { kind: 'jenkins', job: JOB, build: buildNo, result, jenkins: version, harness: HARNESS, mode: HARNESS ? MODE : null,
    jenkinsfile: a.jenkinsfile || null, viewport: VIEWPORT, frames, events, j2gha_exit: childCode };
  fs.writeFileSync(path.join(OUT, 'timeline.json'), JSON.stringify(timeline, null, 1));
  console.log(`[done] ${JOB} #${buildNo} ${result}; ${frames.length} frames over ${frames.at(-1)?.t}s -> ${OUT}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
