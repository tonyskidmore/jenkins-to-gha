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
| "0 syntax errors", "0 security findings" (actionlint, zizmor) | not re-checked: `uv run j2gha validate 000` | NOT verified; the migration report says zizmor flags actions pinned by tag |

## Act 3: differential trace (static)

| Claim | Source | Status |
|---|---|---|
| 41 trace events, 100.0% step similarity, EQUIVALENT | `examples/000/runs/*-trace/result.json` (41 traces each); j2gha verdict line of the act 4 run | verified |
| Trace lines scrolling in the two panes | composition text | DO NOT REUSE: the lines (`matrix_axis: python=3.10`, `artifact_created: tarball (SHA: 4a9f...)`, `TODO_currentResult`) are invented; real events are `{"stage", "step"}` pairs |

## Act 4: real GitHub Actions (live clip `gha_run`)

| Claim | Source | Status |
|---|---|---|
| Run #148 (id 38066767284), self-hosted JIT runners, all 11 jobs success, Success in 1m 43s | capture `timeline.json` (`runNumber`, `runId`, `jobs`), the run page | verified 2026-10-10 |
| 0 billable minutes, 41 trace events, EQUIVALENT (100.0% step similarity) | capture `j2gha.log` | verified |
| Scorecard "Artifact Integrity 100% SHA / exact binary checksum parity" | composition text | NOT shown by a trace run (no artifacts are compared in trace mode); reword or back it with a full-mode run |
| 13× while jobs run, finished page at 1× | `edit.json` `gha_run` | shown by the speed badge |

## Do not claim

- That the conversion is production-ready: one example, one run per tier, a private test repository.
- That self-hosted runs are free in general: 0 billable minutes is what j2gha reported for these runners.
- Anything about how the narration sounds: a person has to listen.
