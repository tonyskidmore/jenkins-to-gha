# Reproduces captures/run-selfhosted.txt: README 7.1, trace-mode run on self-hosted runners (about 3 minutes, free).
# Pushes a temporary j2gha/run/... branch to the harness repo and starts local runner containers. Approved once.
#   NX_REDACT=docs/video/000-ch4-real-github-actions/captures/redact.txt .claude/skills/narrated-explainer/scripts/nx capture local \
#     docs/video/000-ch4-real-github-actions/captures/run-selfhosted.txt docs/video/000-ch4-real-github-actions/captures/run-selfhosted.sh
cd "$(git rev-parse --show-toplevel)"
step 'uv run j2gha run 000 --tier selfhosted'
