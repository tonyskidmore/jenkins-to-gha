# Reproduces captures/trace-checks.txt: read-only follow-ups from README Part 5 (after a trace-mode run).
#   .claude/skills/narrated-explainer/scripts/nx capture local docs/video/000-ch3-differential-runs/captures/trace-checks.txt \
#     docs/video/000-ch3-differential-runs/captures/trace-checks.sh
cd "$(git rev-parse --show-toplevel)"
R=examples/000/runs
O=examples/000/Jenkinsfile
L=$R/jenkins-trace/Jenkinsfile.localized
JC=$R/jenkins-trace/console.log
# the README snippet, kept in a file so its quotes survive eval (the cut only shortens long lines to fit the screen)
S=$(mktemp -d)/stages.py
cat > "$S" <<'PY'
import json
r = json.load(open('examples/000/runs/act-trace/result.json'))
for s in r['comparison']['stages']:
    print(f"{s['status']:<9} {s['stage'] or '(pipeline environment)':<26} {s['jenkins']}")
PY
step 'grep -c J2GHA-TRACE $JC'
step 'grep -m4 J2GHA-TRACE $JC | cut -c28-'
step 'python3 $S | cut -c1-70'
step 'diff -U0 $O $L | grep -E "^(@@|[-+][^-+])" | cut -c1-70 | head -16'
step 'diff $O $L | grep -c "^<"'
step 'diff $O $L | grep -c "^>"'
