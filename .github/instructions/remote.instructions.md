---
description: "Remote runs on GitHub (selfhosted and hosted tiers), environments, the minutes budget guard and the GitHub client"
applyTo: "j2gha/gha/**,j2gha/github.py"
paths:
  - "j2gha/gha/**"
  - "j2gha/github.py"
---
# Remote runs and the GitHub client

- **Remote runs** push the workflow variant to an orphan `j2gha/run/...` branch of `J2GHA_REPO` (default: the clone's
  `origin`) through the Git Data API, and delete it afterwards.
- **Your own pipelines:** `stages.remote_refusal` refuses the remote tiers for a pipeline that is not a corpus example
  unless `J2GHA_REPO` is private or internal. Keep that check in front of any new path that pushes to GitHub.
- **`--environments`** creates `j2gha-<name>` environments (no required reviewers) with a random canary secret via
  `gh secret set`, and compares deployments with the inputs Jenkins reached (`approved_inputs`).
- **Hosted runs** are gated by `j2gha/gha/budget.py` (`guard`): the target repository owner's billing, refusing
  incomplete usage, ledger reservations under a lock; interrupted runs are cancelled and stay pending. Never start one
  without the user's explicit go-ahead.
- **Remote jobs** still get GitHub's automatic `GITHUB_TOKEN`: don't describe runs as credential-free.
- **The GitHub client** (`j2gha/github.py`) caches GETs in `.cache/github` (24 h; 7 days for action SHA lookups).
  With `J2GHA_OFFLINE=1` it serves the cache only and raises `OfflineError` for anything else.
- `j2gha/gha/*` is protected for rule-improvement changes (`evals/protected.txt`).

Reference: [docs/usage.md](../../docs/usage.md), [docs/own-pipelines.md](../../docs/own-pipelines.md),
[docs/architecture.md](../../docs/architecture.md).
