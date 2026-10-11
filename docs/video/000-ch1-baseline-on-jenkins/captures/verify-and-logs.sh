# Reproduces captures/verify-and-logs.txt: README Part 1.6 artifact checks, plus read-only greps of the console logs.
# Needs the local disposable Jenkins running with builds #1 and #2 of inventory-service (see README Part 1).
#   .claude/skills/narrated-explainer/scripts/nx capture local docs/video/000-ch1-baseline-on-jenkins/captures/verify-and-logs.txt \
#     docs/video/000-ch1-baseline-on-jenkins/captures/verify-and-logs.sh
J=http://127.0.0.1:18080/job/inventory-service/1/artifact
FILES='dist/inventory-service-1.4.0.tar.gz dist/inventory-service-1.4.0.tar.gz.sha256 dist/BUILD_INFO.txt deploy/staging.json'
cd "$(mktemp -d)"
step 'for f in $FILES; do curl -fsSu admin:j2gha-local-only -O "$J/$f"; done; ls'
step 'sha256sum -c inventory-service-1.4.0.tar.gz.sha256'
step 'cat BUILD_INFO.txt'
step 'python3 -m json.tool staging.json'
step 'tar -xzf inventory-service-1.4.0.tar.gz'
step 'REPORT_FORMAT=json PYTHONPATH=. python3 -m inventory.cli widget=2 gadget=1'
# helper (not shown on screen): download a build's console log and strip the timestamp prefix
console() { curl -fsSu admin:j2gha-local-only "http://127.0.0.1:18080/job/inventory-service/$1/consoleText" | cut -c28-; }
step 'console 1 | grep -E "^(Uploaded|Approved|Deploying|inventory.*finished)"'
step 'console 2 | grep -E "^(Snapshot|Stage)"'
