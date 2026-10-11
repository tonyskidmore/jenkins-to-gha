# Reproduces captures/run-selfhosted-full.txt: README 7.1 optional full-mode run on self-hosted runners (free). Approved once.
#   NX_REDACT=docs/video/000-ch4-real-github-actions/captures/redact.txt .claude/skills/narrated-explainer/scripts/nx capture local \
#     docs/video/000-ch4-real-github-actions/captures/run-selfhosted-full.txt docs/video/000-ch4-real-github-actions/captures/run-selfhosted-full.sh
cd "$(git rev-parse --show-toplevel)"
step 'uv run j2gha run 000 --tier selfhosted --mode full'
