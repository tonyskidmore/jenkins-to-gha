# Reproduces captures/budget-before.txt: README 7.2, the allowance check before the hosted run (read-only, no minutes).
#   NX_REDACT=... nx capture local captures/budget-before.txt captures/budget-before.sh
cd "$(git rev-parse --show-toplevel)"
step 'uv run j2gha budget'
