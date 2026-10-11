// Shared helpers for the hyperframes-walkthrough scripts: runtime modules, the capture browser, repo root, arguments.
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const HFW_HOME = process.env.HFW_HOME ||
  path.join(process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache'), 'hyperframes-walkthrough');

export function playwright() {
  try {
    return createRequire(path.join(HFW_HOME, 'package.json'))('playwright-core');   // installed by `hfw setup`
  } catch {
    console.error(`playwright-core not found in ${HFW_HOME}: run hfw setup`);
    process.exit(1);
  }
}

export function chromePath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const f = path.join(HFW_HOME, 'chrome-path');
  if (fs.existsSync(f)) return fs.readFileSync(f, 'utf8').trim();
  console.error('no capture browser recorded: run hfw setup');
  process.exit(1);
}

// GitHub capture profile: outside the repository so it can never be committed
export const GH_PROFILE = path.resolve(process.env.HFW_GH_PROFILE || path.join(os.homedir(), '.cache/j2gha-capture-profile'));

export function repoRoot() {
  try {
    return execFileSync('git', ['rev-parse', '--show-toplevel']).toString().trim();
  } catch {
    console.error('run this from inside the j2gha repository');
    process.exit(2);
  }
}

export function assertOutside(dir, root, what) {
  const rel = path.relative(root, dir);
  if (!rel.startsWith('..') && !path.isAbsolute(rel)) {
    console.error(`${what} ${dir} is inside the repository; use a path outside it`);
    process.exit(2);
  }
}

export function ghRepo(root) {
  return execFileSync('gh', ['repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'], { cwd: root }).toString().trim();
}

// --name value / repeated --name a --name b / --flag
export function args(argv = process.argv.slice(2)) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) { out._.push(a); continue; }
    const key = a.slice(2);
    const next = argv[i + 1];
    const val = next === undefined || next.startsWith('--') ? true : (i++, next);
    if (key in out) out[key] = [].concat(out[key], val); else out[key] = val;
  }
  return out;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
