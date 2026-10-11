#!/usr/bin/env node
// Signed-in GitHub browser profile for the GitHub Actions capture (the harness repository may be private).
//
//   hfw gh-login            opens a visible browser window on github.com/login using the profile; sign in by hand
//                           (2FA included), then close the window
//   hfw gh-login --check    headless: which account the profile is signed in as, and whether it can open the repo's
//                           Actions page
//
// The profile lives outside the repository (default ~/.cache/j2gha-capture-profile, override with HFW_GH_PROFILE).
// No credentials pass through this script: the user types them into the browser.
import fs from 'node:fs';
import { playwright, chromePath, GH_PROFILE, repoRoot, assertOutside, ghRepo, args } from '../lib.mjs';

const a = args();
const root = repoRoot();
assertOutside(GH_PROFILE, root, 'profile');
const repo = process.env.GH_REPO || ghRepo(root);
fs.mkdirSync(GH_PROFILE, { recursive: true, mode: 0o700 });

const { chromium } = playwright();
const ctx = await chromium.launchPersistentContext(GH_PROFILE, {
  executablePath: chromePath(),
  headless: !!a.check,
  viewport: a.check ? { width: 1440, height: 900 } : null,
  args: ['--no-sandbox', '--no-first-run', '--no-default-browser-check'],
});
const page = ctx.pages()[0] || await ctx.newPage();

if (!a.check) {
  await page.goto('https://github.com/login');
  console.log(`Sign in to GitHub in the browser window with an account that can read ${repo}, then close the window.`);
  console.log(`Profile: ${GH_PROFILE}`);
  await new Promise((resolve) => ctx.on('close', resolve));
  console.log('Window closed. Verify with: hfw gh-login --check');
  process.exit(0);
}

await page.goto('https://github.com/');
const user = await page.locator('meta[name="user-login"]').getAttribute('content').catch(() => null);
const res = await page.goto(`https://github.com/${repo}/actions`);
const status = res ? res.status() : 0;
await ctx.close();
console.log(`signed in as: ${user || '(not signed in)'}`);
console.log(`${repo}/actions: HTTP ${status}${status === 200 ? ' (readable)' : ' (not readable: sign in with an account that has access)'}`);
process.exit(user && status === 200 ? 0 : 1);
