# Reproduces captures/full-checks.txt: read-only artifact checks from README Part 6 (after a full-mode run).
# The artifact ids differ from run to run (41 and 47 here; the README says 35 and 40); check with ls first. The zips keep the
# Jenkins archive paths (dist/..., deploy/...), as README Part 6 now shows.
#   .claude/skills/narrated-explainer/scripts/nx capture local docs/video/000-ch3-differential-runs/captures/full-checks.txt \
#     docs/video/000-ch3-differential-runs/captures/full-checks.sh
A="$(git rev-parse --show-toplevel)/examples/000/runs/act-full/artifacts/1"
J=http://127.0.0.1:18080/job/ex-000-full/lastBuild/artifact
cd "$(mktemp -d)"
step 'ls -C -T 0 -w 68 $A'
step 'unzip -q $A/artifacts-41/*.zip -d release'
step 'unzip -q $A/artifacts-47/*.zip -d deploy'
step 'ls release/dist deploy/deploy'
step '(cd release/dist && sha256sum -c inventory-service-1.4.0.tar.gz.sha256)'
step 'cat release/dist/BUILD_INFO.txt'
step 'python3 -m json.tool deploy/deploy/staging.json'
# extra, not in the README: the same record as Jenkins' own full-mode build produced it (read-only, local controller)
step 'curl -fsSu admin:j2gha-local-only $J/deploy/staging.json | python3 -m json.tool'
step 'curl -fsSu admin:j2gha-local-only $J/dist/BUILD_INFO.txt'
