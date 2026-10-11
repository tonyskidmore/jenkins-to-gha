# Reproduces captures/run-full.txt: README Part 6, full-mode differential run (about 2 minutes).
#   .claude/skills/narrated-explainer/scripts/nx capture local docs/video/000-ch3-differential-runs/captures/run-full.txt \
#     docs/video/000-ch3-differential-runs/captures/run-full.sh
cd "$(git rev-parse --show-toplevel)"
step 'uv run j2gha run 000 --tier jenkins,act --mode full'
