# Source facts: chapter four "Real GitHub Actions" (examples/000/README.md Part 7, plus "Where the results are")

Environment: private test repository `<owner>/<repo>` (the harness repo), converted workflow for example 000 (converter after commit
8a1c549: 9 jobs, 11 with the matrix expanded), local Jenkins 2.580.1 already running.
Re-recorded 2026-10-11. The first recording (2026-10-04) had 10 jobs, 13 -> 23 of 2000 minutes and incomplete usage data.
Captures (all via `nx capture local`, NX_REDACT=<redact file kept outside the repo>; scripts in captures/*.sh):
- budget-before, run-selfhosted (7.1), run-selfhosted-full (7.1 optional), run-hosted (7.2, approved by the user for this
  recording), budget-after, gh-runs (`gh run list --limit 5`), local-checks (read-only: saved result.json/logs.json under
  examples/000/runs).
Redaction: owner/repo -> <owner>/<repo>, run ids in URLs and "run N" -> <id>, commit shas -> <sha>, home path -> ~, the budget's
"by repository" line. Screenshots (shots/, `nx shots`, read-only signed-in profile outside the repo; spec shape in
shots.example.json): the owner shown as "owner", run number and short commit id removed. 04-artifacts was taken at 1440x1240 so
all 17 artifacts fit.
Order the commands ran: budget, selfhosted trace, selfhosted full, hosted (first attempt refused, see below; second allowed),
budget, gh run list, local-checks.

## Safe claims
- Budget before: 144 / 3000 min used (4.8%); usage data complete (billing API); 2256 min available to the harness after the 20%
  reserve; ledger 10 reconciled runs, 64 billable min. [budget-before]
- Self-hosted trace: pushed a j2gha/run/000-trace-selfhosted-<timestamp> branch, started eleven JIT runner containers
  j2gha-<label>-1 to -11, run -> success (41 trace events, 0 billable min), verdict EQUIVALENT (100.0% step similarity).
  Command 123.1 s; run itself 115.9 s; run page "1m 49s". [run-selfhosted; local-checks #0; shots/01]
- 11 jobs, all success, labelled self-hosted plus a per-run label: Prepare sources/Build, Quality (Unit tests, Lint, Integration
  tests), Compatibility (three cells), Publish, Deploy (when), Deploy, post. [local-checks #0; shots/01]
- "Deploy (when)" is the gate job added by commit 8a1c549 (2026-10-06): a `beforeInput` stage's `when` is decided once in its own
  job (`convert/generator.py` `_gate_plan`).
- Full mode on self-hosted: success, 0 trace events, 0 billable min, verdict "EQUIVALENT (jenkins SUCCESS at None, selfhosted
  success at None)". Command 187.9 s; run itself 176.4 s; run page "2m 47s", 17 artifacts. [run-selfhosted-full; shots/03]
- JUnit summary on the full run page: 5 tests, 0 failures, 0 errors, 0 skipped. [shots/03]
- That full run's log shows 17 distinct artifacts uploaded: artifacts-23, -41, -47, html-report-18, six j2gha-ws-* (workspace
  hand-off), stash-dist, stash-sources, test-reports-17, -30, three test-reports-37-<backend>-<format>. [local-checks #2, #3; shots/04]
- Hosted run: first attempt with the README's `--max-minutes 50` was REFUSED before anything ran ("worst case 55 min exceeds the
  per-run cap of 50 min"; seen, not in the capture). With `--max-minutes 60`: ALLOW, estimate typical 11, worst_case 55,
  reserved 55 min, run -> success (41 trace events, 11 billable min), EQUIVALENT (100.0%). Command 64.6 s; run itself 60.4 s;
  run page "52s". [run-hosted; local-checks #1; shots/05]
- 11 hosted jobs, all success, label ubuntu-latest; the run page's notices mention the ubuntu-latest label. [local-checks #1; shots/05]
- Budget after: 155 / 3000 min used (5.2%) (144 -> 155 = the eleven minutes); ledger 11 reconciled runs, 75 billable min this
  month. [budget-after]
- gh run list: five runs, all success: the hosted trace, the self-hosted full and three self-hosted trace runs of examples/000
  (two of them from earlier recordings). [gh-runs]

## Live footage (scene 05d-live)
- Another self-hosted trace run, recorded the day before: run id <id>, 2026-10-10, success, 1m 43s on the run page,
  11 jobs, 0 billable minutes, EQUIVALENT. [hyperframes-walkthrough capture `.cache/video/000-walkthrough-60s/capture/gha`
  timeline.json and j2gha.log; docs/video/000-walkthrough-60s/source-facts.md Act 4]
- Shown at 7x, last page at 1x (labelled on screen). Masked in every frame: the account name, run number and commit id.

## Differences from the README (real behaviour)
Note: README Parts 3, 6 and 7.2 (and the job counts in 5 and 7.1) were corrected on 2026-10-11, after these captures;
the items below describe the README as it was when recording.
- README 7.1/7.2 say 10 jobs and "about 10 billable minutes"; the current conversion has 11 jobs and the hosted run billed 11.
- README 7.2's `--max-minutes 50` is refused now (worst case 55 = 11 jobs x 5 min); 60 was used.
- README 7.2 describes J2GHA_ALLOW_INCOMPLETE_USAGE=1 for incomplete usage data; not needed here (usage data complete).
- Verdict lines carry the mode: "... (trace): EQUIVALENT ..."; README shows no "(trace)".
- Self-hosted full: README expects `SAME OUTCOME`; real is `EQUIVALENT (jenkins SUCCESS at None, selfhosted success at None)`.
- Artifact numbers vary per run (README: artifacts-30, -34; here 41 and 47) and there are 17, not 11 (the six j2gha-ws-* hand-offs
  are new since the README was written).
- `--yes` was used (README mentions it for non-terminals); no prompt was shown.
- Not verified: README's statement that `docker ps` lists the runners (they exit after one job; not captured).

## Do not claim
- That this proves the converted workflow is production-ready: one example, one run per tier, a private test repository.
- That minutes are free for everyone: 0 billable min is what the tool reported for self-hosted runs in this setup; hosted cost 11 here.
- That GitHub-hosted billing will always be 11 minutes: it depends on plan, repo visibility and job count.
- Anything about audio (not generated).
- Anything about the owner, repo name or run ids.
