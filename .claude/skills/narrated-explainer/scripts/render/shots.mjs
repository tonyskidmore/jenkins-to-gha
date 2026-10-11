// Capture REAL browser screenshots of a web UI (e.g. a local disposable Jenkins) for `screenshot` scenes.
// Usage: node shots.mjs --spec shots.json --out DIR
// spec: { "viewport": {"width":1440,"height":900}, "auth": {"user":"admin","pass":"..."},   (HTTP basic auth, optional)
//         "shots": [ { "name":"dashboard", "url":"http://127.0.0.1:18080/", "waitFor":"#main-panel" | 1500 (ms),
//                      "clip": {"x":0,"y":0,"width":1440,"height":700}, "fullPage": false,
//                      "hide": ["css selector", ...], "redact": {"text":"replacement"}  (also allowed at top level),            (elements to hide, e.g. noisy banners)
//                      "actions": [ {"click":"sel"}, {"clickText":"visible text"}, {"type":["sel","text"]}, {"wait":500}, {"waitForText":"text"},
//                                   {"scroll":"bottom" | "top" | "css selector" | 1200 (px)} ] } ] }
// clip coordinates are page coordinates and may extend below the viewport (long pages such as console output); if both
// clip and fullPage are given, clip wins. Usage also: --only name1,name2 re-shoots just those entries.
// Logged-in sites (e.g. github.com): "profile": "/abs/path/chrome-profile" reuses a dedicated Chrome profile that YOU logged in
// to once with `--login` (headed window; sign in, then close it). The profile must be outside the current directory so it can
// never be committed. While a profile is used the capture is READ-ONLY: every non-GET request is aborted (so a click on
// "Re-run" or "Delete" cannot do anything) and top-level navigation is limited to the origins named in the shots.
// Use a separate, read-only account for the profile, never your main one.
// Writes DIR/<name>.png and DIR/shots.log (urls and sizes). Look at every PNG before using it: pages can show
// secrets, usernames, tokens or hostnames. Nothing here modifies the target; do creation/approval steps with the
// tool's API or CLI first (and only actions the user approved).
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : undefined; };
if (!arg('--spec') || !arg('--out')) { console.error('usage: shots.mjs --spec shots.json --out DIR'); process.exit(2); }
const NX_HOME = process.env.NX_HOME || path.join(process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache'), 'narrated-explainer');
const puppeteer = createRequire(path.join(NX_HOME, 'package.json'))('puppeteer-core');
const spec = JSON.parse(fs.readFileSync(arg('--spec'), 'utf8'));
const out = path.resolve(arg('--out')); fs.mkdirSync(out, { recursive: true });
const chrome = [process.env.CHROME_PATH, 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'].filter(Boolean)
  .map((c) => { try { return c.includes('/') ? c : execFileSync('which', [c], { encoding: 'utf8' }).trim(); } catch { return null; } }).find(Boolean);
if (!chrome) { console.error('No Chrome/Chromium found; set CHROME_PATH'); process.exit(1); }

const profile = spec.profile ? path.resolve(spec.profile) : undefined;
if (profile) {
  const rel = path.relative(process.cwd(), profile);
  if (!rel.startsWith('..') && !path.isAbsolute(rel)) { console.error(`profile ${profile} is inside the working directory; use a path outside it`); process.exit(2); }
}
const login = process.argv.includes('--login');
if (login && !profile) { console.error('--login needs "profile" in the spec'); process.exit(2); }
const browser = await puppeteer.launch({
  executablePath: chrome, headless: !login, ...(profile ? { userDataDir: profile } : {}),
  args: ['--no-sandbox', '--hide-scrollbars', '--force-color-profile=srgb'],
});
if (login) {
  const lp = await browser.newPage();
  await lp.goto(new URL(spec.shots[0].url).origin);
  console.log(`Sign in with the read-only account in the browser window, then close the window. Profile: ${profile}`);
  await new Promise((r) => browser.on('disconnected', r));
  process.exit(0);
}
const page = await browser.newPage();
await page.setViewport({ deviceScaleFactor: 1, ...(spec.viewport ?? { width: 1440, height: 900 }) });
const origins = new Set(spec.shots.map((s) => new URL(s.url).origin));
if (spec.auth || profile) {
  // Basic auth goes only to the origins being captured (never to third-party hosts the page might load from).
  // (page.authenticate only answers 401 challenges, which many apps, Jenkins included, do not send.)
  const header = spec.auth ? 'Basic ' + Buffer.from(`${spec.auth.user}:${spec.auth.pass}`).toString('base64') : undefined;
  await page.setRequestInterception(true);
  page.on('request', (req) => {
    let o = ''; try { o = new URL(req.url()).origin; } catch {}
    if (profile) {
      // read-only guard for a logged-in profile
      if (req.method() !== 'GET' && req.method() !== 'HEAD') { console.error('blocked', req.method(), req.url()); return req.abort('blockedbyclient'); }
      if (req.isNavigationRequest() && req.frame() === page.mainFrame() && !origins.has(o)) { console.error('blocked navigation to', req.url()); return req.abort('blockedbyclient'); }
    }
    req.continue(header && origins.has(o) ? { headers: { ...req.headers(), authorization: header } } : {});
  });
}
const log = [];
const only = arg('--only')?.split(',');
for (const s of spec.shots) {
  if (only && !only.includes(s.name)) continue;
  await page.goto(s.url, { waitUntil: 'networkidle2', timeout: 60000 });
  if (typeof s.waitFor === 'string') await page.waitForSelector(s.waitFor, { timeout: 30000 });
  else if (typeof s.waitFor === 'number') await new Promise((r) => setTimeout(r, s.waitFor));
  for (const a of s.actions ?? []) {
    if (a.click) await page.click(a.click);
    else if (a.clickText) {
      const ok = await page.evaluate((t) => {
        const els = [...document.querySelectorAll('body *')].filter((e) => e.children.length === 0 && e.textContent.includes(t));
        if (!els.length) return false; els[0].click(); return true;
      }, a.clickText);
      if (!ok) throw new Error(`clickText: no element contains "${a.clickText}"`);
    }
    else if (a.type) await page.type(a.type[0], a.type[1]);
    else if (a.wait) await new Promise((r) => setTimeout(r, a.wait));
    else if (a.waitForText) await page.waitForFunction((t) => document.body.innerText.includes(t), { timeout: 30000 }, a.waitForText);
    else if (a.scroll !== undefined) await page.evaluate((v) => {
      if (v === 'bottom') window.scrollTo(0, document.body.scrollHeight);
      else if (v === 'top') window.scrollTo(0, 0);
      else if (typeof v === 'number') window.scrollTo(0, v);
      else document.querySelector(v)?.scrollIntoView({ block: 'start' });
    }, a.scroll);
  }
  if (spec.redact || s.redact) {
    // replace text in the rendered page (e.g. account names) so it never reaches a screenshot; {"from":"to"}
    await page.evaluate((map) => {
      const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = w.nextNode(); n; n = w.nextNode()) for (const [a, b] of Object.entries(map)) n.nodeValue = n.nodeValue.split(a).join(b);
    }, { ...spec.redact, ...s.redact });
  }
  if (s.hide?.length) await page.addStyleTag({ content: s.hide.map((h) => `${h}{display:none !important}`).join('\n') });
  const file = path.join(out, `${s.name}.png`);
  await page.screenshot({ path: file, ...(s.clip ? { clip: s.clip, captureBeyondViewport: true } : { fullPage: !!s.fullPage }) });
  log.push(`${s.name}.png  ${s.url}  ${fs.statSync(file).size} bytes`); console.log('wrote', file);
}
fs.writeFileSync(path.join(out, 'shots.log'), log.join('\n') + '\n');
await browser.close();
