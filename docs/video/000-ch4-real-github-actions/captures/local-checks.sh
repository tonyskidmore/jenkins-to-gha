# Reproduces captures/local-checks.txt: read-only looks at the saved run records and logs under examples/000/runs
# (written by the self-hosted and hosted runs; nothing is contacted). Run after those runs.
#   NX_REDACT=... nx capture local captures/local-checks.txt captures/local-checks.sh
cd "$(git rev-parse --show-toplevel)"
R=examples/000/runs
S=$(mktemp -d)/jobs.py
cat > "$S" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
for j in r['jobs']:
    print(f"{j['conclusion']:<8} {','.join(j['labels']):<22} {j['name'][:32]}")
print('billable_minutes', r['billable_minutes'], ' seconds', r['seconds'])
PY
step 'python3 $S $R/selfhosted-trace/result.json'
step 'python3 $S $R/hosted-trace/result.json'
step 'grep -o "Artifact [^ ]* has been successfully" $R/selfhosted-full/logs.json | cut -d" " -f2 | sort -u | paste -d" " - - | column -t'
step 'grep -o "Artifact [^ ]* has been successfully" $R/selfhosted-full/logs.json | cut -d" " -f2 | sort -u | wc -l'
