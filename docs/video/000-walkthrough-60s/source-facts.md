# Source facts: 60 s walkthrough of examples/000 (reference project)

Every number or claim on screen or in the narration should trace to a line here. Re-check them after each capture:
the live clips are real runs, so the text around them must agree with what they show.

## Act 1: Jenkins baseline (live clip `jenkins_run`)

| Claim | Source | Status |
|---|---|---|
| Job `inventory-service`, build #1, SUCCESS, Jenkins 2.580.1 | capture `timeline.json` (`job`, `build`, `result`, `jenkins`) | verified 2026-10-10 |
| Input "Deploy this inventory-service release?", `CHANGE_TICKET` typed as CHG-1234, approved by admin on camera | capture events `input-pending`, `input-typed`, `approve-click` | verified |
| Quality runs unit tests, lint and integration tests in parallel | `examples/000/Jenkinsfile` stage Quality | verified |
| Matrix = backend (memory, sqlite) × report format (text, json), memory+text excluded: 3 cells | Jenkinsfile stage Compatibility | verified |
| Tarball `inventory-service-1.4.0.tar.gz` (RELEASE_VERSION default 1.4.0), `BUILD_INFO.txt` | build #1 artifacts (`/job/inventory-service/1/api/json?tree=artifacts[fileName]`) | verified |
| 21 passed, 0 failures | build #1 `testReport/api/json` | verified |
| Stages at 3×, waits cut | `edit.json` `jenkins_run` | shown by the speed badge |

## Act 2: analyse, convert, validate (static)

| Claim | Source | Status |
|---|---|---|
| Difficulty 23 / 100 | `examples/000/analysis/analysis.json` `complexity.score` | verified |
| 9 Actions jobs (the matrix expands to 3 runs, so a run shows 11) | `examples/000/gha/workflow.yml` jobs | verified |
| `j2gha-ws-*` workspace hand-off tarballs | CLAUDE.md, `convert/workspace.py` | verified |
| actionlint 0, zizmor 0, policy 1 warning (untranslated Groovy in the post job), validate OK | `uv run j2gha validate 000`, 2026-10-11 (chapter 2 capture parts-2-4 #2) | verified |
| 9 Actions jobs, coverage 78.5%, workflow file `gha/workflow.yml` | `j2gha convert 000` / `analyze 000` output, 2026-10-11 | verified |

## Act 3: differential trace (static)

| Claim | Source | Status |
|---|---|---|
| 41 trace events, 100.0% step similarity, EQUIVALENT | `examples/000/runs/*-trace/result.json` (41 traces each); j2gha verdict line of the act 4 run | verified |
| The two panes: 7 of the 41 events (2, 5, 12, 13, 24, 35, 36), the same on both sides, times since each run's first event | `examples/000/runs/jenkins-trace/console.log`, `runs/act-trace/act.jsonl`, 2026-10-11 | verified (the invented lines of the first draft are gone) |
| 10 / 10 stages matched, 0 divergences | chapter 3 capture trace-checks #2; verdict EQUIVALENT | verified |
| Gap note: act's deploy record has `"approver": "unknown"`, Jenkins' has `admin` | chapter 3 capture full-checks #6, #7 | verified (full mode) |

## Act 4: real GitHub Actions (live clip `gha_run`)

| Claim | Source | Status |
|---|---|---|
| Run #<n> (id <id>), self-hosted JIT runners, all 11 jobs success, Success in 1m 43s | capture `timeline.json` (`runNumber`, `runId`, `jobs`), the run page | verified 2026-10-10 |
| 0 billable minutes, 41 trace events, EQUIVALENT (100.0% step similarity) | capture `j2gha.log` | verified |
| Scorecard: Run Time 1m 43s; Validators 0 / 0 (policy 1 warning) | the run page in the capture; `j2gha validate 000` | verified (replaced the unbacked "Artifact Integrity 100% SHA" tile) |
| 13× while jobs run, finished page at 1× | `edit.json` `gha_run` | shown by the speed badge |
| Account name, run number and commit id hidden; URL bar shows `<owner>/<repo>`/`<run>` | `edit.json` `gha_run.mask`, act 4 composition | checked on rendered frames |

## Do not claim

- That the conversion is production-ready: one example, one run per tier, a private test repository.
- That self-hosted runs are free in general: 0 billable minutes is what j2gha reported for these runners.
- Anything about how the narration sounds: a person has to listen.
