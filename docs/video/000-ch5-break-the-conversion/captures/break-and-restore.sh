# Reproduces captures/break-and-restore.txt: README Part 8, sabotage, differential run, restore, run again (about 2 to 3 minutes).
# Needs the local Jenkins controller running and example 000 already analysed and converted (earlier chapters).
# WARNING: step 1 edits a gitignored generated file; step 6 (convert) restores it.
#   NX_REDACT=docs/video/000-ch5-break-the-conversion/captures/redact.txt \
#   .claude/skills/narrated-explainer/scripts/nx capture local docs/video/000-ch5-break-the-conversion/captures/break-and-restore.txt \
#     docs/video/000-ch5-break-the-conversion/captures/break-and-restore.sh
cd "$(git rev-parse --show-toplevel)"
set -o pipefail
step 'grep -n env.DEPLOY_ENV examples/000/gha/workflow.model.json'
step 'sed -i "s/env.DEPLOY_ENV != '\''none'\''/env.DEPLOY_ENV == '\''none'\''/" examples/000/gha/workflow.model.json'
step 'grep -n env.DEPLOY_ENV examples/000/gha/workflow.model.json'
step 'uv run j2gha run 000 --tier act --edited-model | fold -s -w 68'
step 'grep -n missing-stage examples/000/RESULTS.md | fold -s -w 68'
step 'uv run j2gha convert 000 | fold -s -w 68 | tail -n 12'
step 'grep -n env.DEPLOY_ENV examples/000/gha/workflow.model.json'
step 'uv run j2gha run 000 --tier act | fold -s -w 68'
