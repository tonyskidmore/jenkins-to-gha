# Reproduces captures/budget-after.txt: README 7.2, the allowance check after the hosted run (read-only).
#   NX_REDACT=... nx capture local captures/budget-after.txt captures/budget-after.sh
cd "$(git rev-parse --show-toplevel)"
step 'uv run j2gha budget'
