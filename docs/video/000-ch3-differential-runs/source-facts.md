# Source facts: chapter three "Differential runs" (examples/000/README.md Parts 5 and 6)

Environment: local disposable Jenkins 2.580.1 (already running, chapter 1 jobs present), act via `j2gha run --tier jenkins,act`.
Captures (nx capture local): run-trace, run-full (the two approved runs), trace-checks and full-checks (read-only follow-ups).
Screenshots: shots/01, 03, 04 (spec shots/shots.json; 02-trace-build.png taken but unused). Job numbers on screen (trace #50, full #25)
depend on history (the controller is shared with other recordings and tests). Re-captured and re-shot 2026-10-11 with the
converter after commit 8a1c549 (2026-10-06); the first recording (trace #8, full #2) had 10 act job results.
Capture scripts: captures/*.sh. Paths in captures are redacted to <repo>; the run-trace capture was redacted afterwards with the
same substitution (sed), not by re-running.

## Safe claims
- Trace run: jenkins SUCCESS 41 trace events; act success, 41 events, 11 job results (the 11th is the deploy-gate job); verdict
  EQUIVALENT 100.0% step similarity. [run-trace]
- auto-repair line for PYTHON_VERSION appears. [run-trace; README Part 5]
- 41 J2GHA-TRACE lines in the Jenkins console; markers carry stage and step kind. [trace-checks #0,#1; shots/01]
- Per-stage comparison: 10 rows, all `match`, including "Declarative: Post Actions" and "Contract tests". [trace-checks #2]
- Localised Jenkinsfile: agent label -> any, buildDiscarder and triggers replaced by comments, 5 lines changed/removed, 91 added, stubs after line 483.
  [trace-checks #3-#5]
- Full run: both SUCCESS, 0 trace events, act 11 job results; verdict EQUIVALENT (not SAME OUTCOME). [run-full]
- act artifacts: three artifacts-N folders (23 lint, 41 release, 47 deploy) plus six j2gha-ws-* workspace hand-offs; release zip has
  dist/BUILD_INFO.txt, dist/*.tar.gz, dist/*.sha256 (Jenkins archive paths kept); sha256sum OK; python=3.12.3 on act; build label ...-b1.
  [full-checks #0-#5]
- act staging.json: change none, approver unknown. Jenkins staging.json: change none, approver admin. Jenkins python=3.13.5,
  build label ...-b25. [full-checks #6-#8]
- Jenkins full build page: 5 artifacts, tests no failures, "approved by user admin", all stages green. [shots/03, 04]

## Differences from the README (real behaviour)
Note: README Parts 3, 6 and 7.2 (and the job counts in 5 and 7.1) were corrected on 2026-10-11, after these captures;
the items below describe the README as it was when recording.
- Part 5 Expected: real output has two extra lines ("provisioned: []" and "running act (trace) in <path>"); verdict line reads
  "act vs jenkins (trace): EQUIVALENT"; README shows "act vs jenkins: EQUIVALENT". Timing 39.1 s (varies); README says "<seconds>".
- Part 6 Expected: verdict is "EQUIVALENT (jenkins SUCCESS at None, act success at None)", README says "SAME OUTCOME (...)". Extra "running act (full)" line.
  Act took 121.0 s here; whole command 136 s.
- Part 6 commands: artifact ids are artifacts-41 (release) and artifacts-47 (deploy); README says artifacts-35 and artifacts-40. Ids vary by run.
- Part 6 commands: the zips now keep the Jenkins archive paths, so the files are in release/dist/ and deploy/deploy/; the README's
  `(cd release && sha256sum -c ...)` and `cat deploy/staging.json` fail as written. The capture uses the real paths.
- Part 6: README's `ls "$A"` (shown here as `ls -C -T 0 -w 68`, columns to fit the screen) lists stash-*, test-reports-*, html-report-*; real also has artifacts-23 (lint.txt, Lint stage) and
  j2gha-ws-* (workspace hand-off).
- Part 6 Expected: matches (checksum OK; python differs 3.12.3 vs 3.13.5; staging.json change none, approver unknown).
- Part 5 python snippet: output is correct but lines are cut with `| cut -c1-70` in the capture command to fit the screen. staging.json is shown through
  `python3 -m json.tool` instead of `cat` (README) for line length.
- Extra, not in the README: Jenkins-side staging.json and BUILD_INFO.txt fetched read-only from the local controller for the side-by-side table.
- Numbers that vary: timings, job/build numbers, artifact ids, timestamps.

## Do not claim
- That act equals GitHub: no run on GitHub (hosted or self-hosted) was made.
- That the approver gap is fixed or has a chosen replacement; README says whoever migrates must decide.
- That trace-mode match proves the real commands behave the same (that is full mode, one run).
- That the verdict word "EQUIVALENT" in full mode means more than the tool printed; do not explain "at None".
- Anything about audio (not generated).
