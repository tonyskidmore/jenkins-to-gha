#!/usr/bin/env bash
# One-time (idempotent) runtime install for narrated-explainer. Never uses sudo.
# Installs into $NX_HOME: a Python 3.12 venv with CPU torch + kokoro, and puppeteer-core (uses the system Chrome).
set -euo pipefail
NX_HOME="${NX_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/narrated-explainer}"
mkdir -p "$NX_HOME"; cd "$NX_HOME"
ok=1
need() { command -v "$1" >/dev/null 2>&1 || { echo "MISSING: $1 ($2)"; ok=0; }; }
need node "Node 18+ (nvm or distro package)"; need npm "comes with node"; need ffmpeg "apt install ffmpeg"; need ffprobe "comes with ffmpeg"; need uv "https://docs.astral.sh/uv/"
chrome=""
for c in "${CHROME_PATH:-}" google-chrome google-chrome-stable chromium chromium-browser; do
  [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && { chrome="$(command -v "$c")"; break; }
done
[ -n "$chrome" ] || { echo "MISSING: Chrome/Chromium (set CHROME_PATH). Snap chromium may not work with puppeteer; prefer google-chrome."; ok=0; }
[ "$ok" = 1 ] || { echo "Install the missing tools above, then re-run: nx setup"; exit 1; }
echo "node $(node -v), ffmpeg $(ffmpeg -version | head -1 | cut -d' ' -f3), chrome: $chrome"

if [ ! -x .venv/bin/python ]; then uv venv --python 3.12 .venv; fi
# torch first, separately, from the CPU index (mixing indexes in one resolve picks an ancient transformers and fails building tokenizers)
if ! .venv/bin/python -c "import torch" 2>/dev/null; then uv pip install --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu; fi
# transformers must be pinned modern for the same reason
if ! .venv/bin/python -c "import kokoro, soundfile" 2>/dev/null; then uv pip install --python .venv/bin/python kokoro soundfile "transformers>=4.45"; fi
# the spaCy English model used by Kokoro's text processor (downloaded from GitHub releases)
if ! .venv/bin/python -c "import spacy; spacy.load('en_core_web_sm')" 2>/dev/null; then .venv/bin/python -m spacy download en_core_web_sm; fi
[ -f package.json ] || echo '{"name":"narrated-explainer-runtime","private":true}' > package.json
[ -d node_modules/puppeteer-core ] || npm i --save-exact --no-audit --no-fund puppeteer-core
echo "Runtime ready in $NX_HOME"
echo "The first audio run downloads the Kokoro weights (hexgrad/Kokoro-82M) from Hugging Face."
