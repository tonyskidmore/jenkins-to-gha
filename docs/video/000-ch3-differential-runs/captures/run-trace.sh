# Reproduces captures/run-trace.txt: README Part 5, the trace-mode differential run (about 1 minute).
# Needs the local Jenkins controller running and the harness already converted (analysis/ and gha/ present).
#   .claude/skills/narrated-explainer/scripts/nx capture local docs/video/000-ch3-differential-runs/captures/run-trace.txt \
#     docs/video/000-ch3-differential-runs/captures/run-trace.sh
cd "$(git rev-parse --show-toplevel)"
step 'uv run j2gha run 000 --tier jenkins,act'
