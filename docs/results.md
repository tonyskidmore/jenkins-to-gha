# Results on the corpus

The corpus is 20 real-world examples (`001`-`020`, the *originals*) spanning all 17 styles, the hand-written
[walkthrough](../examples/000/README.md), and 16 *twins* (`1NN`, [below](#twins-full-mode-against-a-successful-jenkins-reference)).
The live table is [examples/README.md](../examples/README.md), and every result on this page links to a run in its
example's README (see [Reference runs](#reference-runs)). To repeat the originals on act, run
`uv run j2gha pipeline 1-20`.

| Stage | Outcome |
|---|---|
| Analysis | 20/20 parsed with Jenkins' Groovy. Declarative ones were validated against Jenkins 2.580.1. Difficulty ranges from 5 to 58 (scoring as in [scoring.md](scoring.md#migration-difficulty-0-100)). |
| Conversion | 20/20 converted, at 12-87% estimated automation (report items weighted by status: an effort estimate, not a measure of correctness). Every manual item has a source line. |
| Static validation | 20/20 pass actionlint structurally and the j2gha policy, with every scanner run (a scanner that cannot run fails validation). Shellcheck findings in the *original* scripts are reported as SAST. zizmor is clean for 18/20 after SHA-pinning and `persist-credentials: false`; 001 keeps High `unpinned-images` findings inherited from tag-only Jenkins docker-agent images (⚠️ in the summary), and 015 has informational `use-trusted-publishing` findings for its token-based `npm publish`. |
| Jenkins execution (trace) | 18/20 run to completion after automatic localisation. 017 and 018 stop on their own `error()`, in branches decided by values that trace mode stubs. |
| act vs Jenkins (trace) | **15/20 equivalent**: 003, 004, 005, 006, 007, 009 (26-cell matrix), 010, 011, 012, 013, 014 (8-cell matrix), 015, 016, 019, 020. **2 inconclusive** (017, 018). 001, 002 and 008 differ: they fan out stages over runtime-built collections. |
| Real GitHub Actions, self-hosted JIT runners (trace) | **4/4 equivalent** (004, 012, 013, 014), 0 billable minutes. |
| Real GitHub Actions, GitHub-hosted runners (trace) | All 20 (free on the public repository): the same verdicts as act. |
| Real GitHub Actions, full mode | Self-hosted: equivalent for 14 of the 15 originals that have a record (003-007, 009-016, 019, 020); 019 is inconclusive (neither side names a failing stage). GitHub-hosted (013 only): both fail at `Build Nebula`, but the hosted run archived 4863 of Jenkins' 5330 files, so it differs. Most originals fail on Jenkins in the harness, so these compare two failures: the twins below compare successful runs. |
| Walkthrough [000](../examples/000/README.md) | Equivalent on act in trace and full mode for three scenarios (default, snapshot without deploy, integration tests off); full mode also compares the 20-21 JUnit test cases and the archived files. On real GitHub (self-hosted and GitHub-hosted runners) it is equivalent in trace and full mode for the default scenario. Two deliberately broken conversions are caught: a wrong `when` (trace) and a dropped test report (full; both runs still succeed). These runs are an acceptance test: `pytest -m e2e tests/test_walkthrough.py`. |
| Full mode (real commands, 006) | Jenkins built the original repository and failed at `Publish` (no Nexus endpoint locally). The converted workflow first failed one stage earlier, at `Build`: `packname` is built by string concatenation in `script{}`, which the converter did not carry on, and the harness pinpointed the divergence. Since the converter carries such assignments through `$GITHUB_ENV` (2026-10-12), both fail at `Publish`: equivalent on act and self-hosted runners (act gets no credential: the public source is fetched on the host). |

These are trace (control-flow) results, recorded against the current Jenkinsfile, conversion and scenario; runs of
an earlier version are marked stale and not counted. Trace equivalence shows the same stages run the same kinds of
steps in the same order for the scenario that was run - not that the commands or artifacts are equivalent, and not
that the conversion is correct: the harness finds differences, it cannot prove their absence (see
[What the verdicts establish](mechanism.md#what-the-verdicts-establish)).

The analysis predicted where conversion would struggle. The three examples that still differ all carry the
`DynamicParallel` hard gate (stages generated from runtime collections), and the two inconclusive ones branch on
values that trace mode stubs; see the limitations in
[architecture.md](architecture.md#known-limitations-and-where-to-extend).

## Twins: full mode against a successful Jenkins reference

Full mode runs the real commands, and in the harness most originals cannot succeed on Jenkins (they need private
services, credentials, cloud or Windows/ARM nodes), so a full-mode comparison against them mostly compares two
failures. Each original `0NN` has a *twin* `1NN`: a minimally edited copy whose every edit is listed in its `LOCAL.md`
(the cited Jenkinsfile is never edited), made so that Jenkins runs the pipeline to completion. All 16 twins now have a
**SUCCESS** Jenkins full-mode reference; the converted workflow is then compared on act and on real GitHub Actions
(self-hosted JIT runners, whose images carry the Jenkins image's toolchain, and for some GitHub-hosted runners).

| Twin | Jenkins | act | Real GitHub (self-hosted) | GitHub-hosted | What the difference is |
|---|---|---|---|---|---|
| 104, 111, 112, 116, 117 | SUCCESS | equivalent | equivalent | 104, 112: equivalent | - |
| 106, 119 | SUCCESS | equivalent | equivalent | - | before 2026-10-12: Groovy variables set in `script {}` never reached later steps (conversion gap, fixed); 106 also needed `JOB_NAME` pinned to the Jenkins job, 119 the Jenkins stub value for undeclared properties (harness parity, fixed) |
| 114 | SUCCESS | equivalent | equivalent | - | the same gap for two captured `sh` values (`OLD_SHA`/`NEW_SHA`, fixed) |
| 107 | SUCCESS | equivalent | equivalent | - | archive paths contain each run's `BUILD_TAG`: the outputs comparison now treats it as a placeholder (harness, fixed) |
| 115 | SUCCESS | equivalent | equivalent | equivalent | a timing-sensitive unit test failed in every Jenkins reference: a twin edit widens its margin |
| 108 | SUCCESS | equivalent | equivalent | - | its steps run in Docker (`agent { dockerfile }`), which the Jenkins reference ran with `docker` stubbed: since 2026-10-12 full variants run them the same way on runners without a Docker daemon (harness parity, fixed) |
| 109 | SUCCESS | equivalent | equivalent | equivalent | before 2026-10-12: matrix cells did not hand their workspace on, so the post stage found nothing to archive (conversion gap, fixed: cells hand on their changes); the archive paths also hold `BUILD_ID`, now the Jenkins reference's build in the variant, as `JOB_NAME` is (harness parity, fixed) |
| 101 | SUCCESS | differs | differs | - | the `Test and Package` stage is a dynamic `parallel` (the `DynamicParallel` hard gate, reported manual) |
| 102, 118 | SUCCESS | differs | differs | - | values built by dynamic Groovy (tuple destructuring in closures, a `for` loop over repositories), reported manual |
| 103 | SUCCESS | differs | differs | - | `Copy meshes to dist` runs a command built by `collect {}` and `join` (reported manual). It got that far once Docker steps ran as in the reference (as for 108) and a stash name holding a matrix value (`ROBOT_${ROBOT}_urdf`) was evaluated per cell instead of fixed into one literal artifact name (conversion gap, fixed 2026-10-12) |

So the converted workflow showed no difference from the successful Jenkins run for **12 of the 16 twins** on real
GitHub Actions (5 before the fixes of 2026-10-12). The rest are reported, not hidden: 101, 102, 103 and 118 by the
converter's own manual items.

As everywhere on this page, *equivalent* means no difference was found in the scenario that was run (the same
outcome, failing stage, JUnit cases and archived files), not that the conversion is correct. Twins check what the
converted workflow does with the pipeline's own commands; they do not check the edits that made the twin runnable.

## Reference runs

Every result on GitHub Actions on this page is a recorded run, linked from its example's README (the *Converted vs
Jenkins* table) and kept in its `runs/<tier>-<mode>/` record: 76 records across 36 examples, all run from one commit
of the harness, plus the walkthrough's (gitignored) records. Each was run in the scenario its record holds:

| Tier and mode | Examples |
|---|---|
| Self-hosted, trace | 004, 012, 013, 014 |
| Self-hosted, full | 003-007, 009-016, 019, 020, and all 16 twins |
| GitHub-hosted, trace | all 20 originals and all 16 twins |
| GitHub-hosted, full | 013, 104, 109, 112, 115 |

Scenario options: 006 and 106 run trace mode with `--environments`, 013 runs full mode with `--param PROMOTE=false`.
How to repeat them is in [usage.md](usage.md#re-run-the-reference-runs).
