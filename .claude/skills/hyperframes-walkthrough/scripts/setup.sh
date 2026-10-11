#!/usr/bin/env bash
# One-time (idempotent) runtime install for hyperframes-walkthrough. Never uses sudo.
# Installs into $HFW_HOME: playwright-core and the hyperframes CLI, both pinned. Narration reuses narrated-explainer's
# Kokoro runtime ($NX_HOME, made by `nx setup`).
set -euo pipefail
HFW_HOME="${HFW_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/hyperframes-walkthrough}"
NX_HOME="${NX_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/narrated-explainer}"
PLAYWRIGHT_VERSION=1.64.0
HYPERFRAMES_VERSION=0.8.145
mkdir -p "$HFW_HOME"; cd "$HFW_HOME"
ok=1
need() { command -v "$1" >/dev/null 2>&1 || { echo "MISSING: $1 ($2)"; ok=0; }; }
need node "Node 22+"; need npm "comes with node"; need ffmpeg "apt install ffmpeg"; need ffprobe "comes with ffmpeg"
need gh "GitHub CLI, signed in (gh auth status)"; need uv "https://docs.astral.sh/uv/ (runs j2gha)"
[ "$ok" = 1 ] || { echo "Install the missing tools above, then re-run: hfw setup"; exit 1; }

# Browser for the live captures. Kept stable in $HFW_HOME/chrome-path: the signed-in GitHub profile only works with
# the browser build that created it (cookie encryption differs between Chrome and Chromium).
if [ ! -s chrome-path ]; then
  chrome="${CHROME_PATH:-}"
  [ -n "$chrome" ] || chrome="$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux/chrome 2>/dev/null | sort -V | tail -1 || true)"
  [ -n "$chrome" ] || chrome="$(command -v google-chrome || command -v google-chrome-stable || true)"
  [ -n "$chrome" ] || { echo "MISSING: a Chrome/Chromium binary (set CHROME_PATH, or: npx playwright install chromium)"; exit 1; }
  echo "$chrome" > chrome-path
fi
echo "node $(node -v), ffmpeg $(ffmpeg -version | head -1 | cut -d' ' -f3), capture browser: $(cat chrome-path)"

[ -f package.json ] || echo '{"name":"hyperframes-walkthrough-runtime","private":true}' > package.json
have() { node -e "process.exit(require('./node_modules/$1/package.json').version==='$2'?0:1)" 2>/dev/null; }
have playwright-core "$PLAYWRIGHT_VERSION" || npm i --save-exact --no-audit --no-fund "playwright-core@$PLAYWRIGHT_VERSION"
have hyperframes "$HYPERFRAMES_VERSION" || npm i --save-exact --no-audit --no-fund "hyperframes@$HYPERFRAMES_VERSION"

if [ -x "$NX_HOME/.venv/bin/python" ]; then echo "Kokoro runtime: $NX_HOME"
else echo "NOTE: narration needs narrated-explainer's runtime: .claude/skills/narrated-explainer/scripts/nx setup"; fi
echo "Runtime ready in $HFW_HOME"
