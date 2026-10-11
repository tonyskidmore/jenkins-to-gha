# Reproduces captures/run-hosted.txt: README 7.2, GitHub-hosted trace run. SPENDS Actions minutes (about 11; guard worst case 55).
# Needs the user's approval each time. The budget data is complete since the token got the `user` scope, so no override.
#   NX_REDACT=... nx capture local captures/run-hosted.txt captures/run-hosted.sh
cd "$(git rev-parse --show-toplevel)"
step 'uv run j2gha run 000 --tier hosted --yes --max-minutes 60'
