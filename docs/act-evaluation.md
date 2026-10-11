# Is nektos/act still relevant? (evaluated October 2026)

**Verdict: yes, as the fast local smoke-test tier, not as a fidelity oracle.** j2gha uses it as tier 2 of the
execution ladder and backs it with real GitHub Actions on ephemeral self-hosted runners (no hosted-runner minutes) and, sparingly,
GitHub-hosted runners (budget-guarded).

## Maintenance status

| Signal | Finding |
|---|---|
| Latest release | v0.2.89 (2026-06-01); monthly bot releases only when something merged. No master commit since. |
| Activity | 2025: 78 PRs merged. 2026 to date: 7 of 129 opened PRs merged; 270 open issues, 115 open PRs. |
| Maintainers | ChristopherHX (main dev, last code Dec 2025, still triaging), cplee (creator, merged Mar-2026 security fixes), panekj. |
| Security | Use ≥ v0.2.86: GHSA-x34h-54cw-9825 (cache-server RCE), GHSA-xmgr-9pqc-h5vw (`::set-env::`). |
| Deprecation | None announced; no successor. `gh act` extension still tracks releases. |

"Looks unmaintained" is fair for feature work, not for security fixes: **maintenance mode**.

## What works for our use case (verified)

- `actions/upload-artifact@v4` / `download-artifact@v4` with `--artifact-server-path`; `actions/cache` v4/v6
- `services:` + job `container:`, `matrix`, `needs`, `if: always()`, local composite actions, local reusable workflows
- `--json` (one JSON event per line: job, matrix, step, stepResult, jobResult, msg) and exit code 1 on any job failure
- running act itself in a container (`docker/act/Dockerfile`) with the host socket and the workspace mounted at the
  same absolute path

j2gha's differential trace runs on act: examples 004, 009 (a 26-cell matrix), 012 and others are reported
*equivalent* to their Jenkins reference runs in a few seconds each.

## Known gaps (why it cannot be the final word)

- **Broken with current artifact action majors** (`upload-artifact@v6/v7`, `download-artifact@v7/v8`): issues
  #6114/#6021/#6173 open. j2gha's generator emits `@v4` (pinned to SHAs) so the same YAML runs everywhere.
- Ignores `concurrency`, `permissions`, `environment` (approvals), job `timeout-minutes`, job `continue-on-error`,
  OIDC, problem matchers. Lags new syntax (step-level `parallel:`/`background:` from June 2026).
- Containers ≠ hosted VMs: runner images lack tools, no systemd, different networking.
- Docker Engine 29.5.0/29.5.1/29.7.0 break act (`path escapes from parent`) - this host runs 29.8.1.
- Without `--rm`, failed jobs leave containers running; without `--container-daemon-socket -`, job containers get
  the host Docker socket (j2gha disables it because full-mode runs execute third-party scripts).

## Alternatives considered

| Tool | Assessment |
|---|---|
| **Ephemeral JIT self-hosted runner** (`ghcr.io/actions/actions-runner`) | Highest fidelity short of hosted: real GitHub orchestration, expressions, artifacts, logs; self-hosted minutes are free (the proposed $0.002/min fee was postponed). Needs `runs-on` rewrite. **Adopted as tier 3.** |
| runner.server (ChristopherHX) | actions/runner fork with a local server; reasonable middle tier, not needed given JIT runners. |
| wrkflw (Rust) | Active, but no `services:` and no private remote `uses:` - weaker than act. |
| Local CI (formerly agent-ci) | Promising (real runner binary against an emulated API) but young: no matrix include/exclude, no timeouts. Watch. |
| Gitea/Forgejo runners | act forks - same semantics, no advantage. |
| Official GitHub local runner | None exists (checked changelog through Oct 2026). |

## How j2gha invokes it

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v $WS:$WS -v $OUT/artifacts:$OUT/artifacts -w $WS \
  -v j2gha-act-cache:/root/.cache/act \
  j2gha/act:local push -W .github/workflows/j2gha.yml \
  -P ubuntu-latest=j2gha/act-runner:local -P ubuntu-24.04=j2gha/act-runner:local \
  -P ubuntu-22.04=j2gha/act-runner:local -P ubuntu-24.04-arm=j2gha/act-runner:local \
  --pull=false --rm --json --container-architecture linux/amd64 --action-offline-mode \
  --container-daemon-socket - --artifact-server-path $OUT/artifacts
```

`j2gha/act-runner:local` is `catthehacker/ubuntu:act-latest` plus the Jenkins image's toolchain (built by
`j2gha docker build`). `--action-offline-mode` reuses actions already in the cache volume; for an action pinned to a
commit SHA the cached copy is exactly that version, but one left on a version tag (when `convert` could not resolve
its SHA) may be an older copy of that tag. An action is still downloaded the first time it is used. The harness builds this command in
`j2gha/runners/act.py`; it is shown here for reference.

The workspace is a throw-away git repository whose branch is the scenario branch, so `github.ref_name` and the
pinned `BRANCH_NAME` agree with the Jenkins run.
