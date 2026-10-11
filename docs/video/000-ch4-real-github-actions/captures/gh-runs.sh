# Reproduces captures/gh-runs.txt (read-only). Run from anywhere inside the repo:
#   NX_REDACT=<absolute path to redact.txt kept outside the project> nx capture local captures/gh-runs.txt captures/gh-runs.sh
cd "$(git rev-parse --show-toplevel)"
# columns of `gh run list` are tab-separated: status, conclusion, title, workflow, branch, ...; keep conclusion and title
step 'gh run list --limit 5 | cut -f2,3'
