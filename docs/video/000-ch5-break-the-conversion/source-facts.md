# Source facts: chapter five "Break the conversion" (examples/000/README.md Part 8)

Environment: local disposable Jenkins (already running, earlier chapters' jobs present), act via `j2gha run 000 --tier act`.
Capture: captures/break-and-restore.txt (8 steps, one `nx capture` run, each approved command run once). Script: captures/break-and-restore.sh.
Redaction: captures/redact.txt (paths to <repo>). The redact file itself names the owner, so do not publish it as-is.
Re-captured 2026-10-11 with the converter after commit 8a1c549 (2026-10-06, the deploy-gate job) and the harness's edited-model
guard (step 3 now passes `--edited-model`, as README Part 8 does). Redaction file kept outside the repo.
Steps: 0 grep before, 1 sed sabotage, 2 grep after, 3 run (DIFFERS), 4 RESULTS.md grep, 5 convert (restore), 6 grep after restore, 7 run (EQUIVALENT).
Extra read-only commands not in the README: steps 0, 2, 4 (grep), 6 (grep). Pipes `fold -s -w 68` (wrap long lines) and `tail -n 12` on convert
only shorten for the screen; `set -o pipefail` was set silently so a failing command still shows a non-zero code (all were 0).

## Safe claims
- Before sabotage the Deploy condition in the generated model is `env.DEPLOY_ENV != 'none'` (line 1385), in the deploy-gate job's
  stage-entry step (workflow.yml line 2106, job `deploy-gate` "Deploy (when)"). [step 0]
- The sed flips it to `== 'none'`; the grep afterwards proves the file changed. [steps 1, 2]
- Sabotaged run (`--edited-model`): act reports success with 37 trace events and 10 job results; verdict DIFFERS (90.2% step
  similarity); an extra line "[j2gha] not equivalent: 000 act (differs)". The command still exited 0. [step 3] Without the flag the
  harness refuses: "the converted workflow is stale ... changed since `j2gha convert`" (seen on a first attempt, not shown).
  README Part 8: such a record "is marked, shown as stale and never counted".
- RESULTS.md line 158: Deploy: missing-stage - jenkins ['input', 'unstash', 'sh', 'archiveArtifacts'] vs act []. [step 4]
- 37 events is 4 fewer than the original 41, and Deploy's four Jenkins steps are four: consistent (do not state as proven cause beyond the line itself).
- The act run itself succeeded: a green tick alone would not have caught it. [step 3 "success"; README Part 8]
- Restore: `convert 000` regenerates the workflow ("9 job(s); mapped 41, approx 33, manual 1 -> automation 81.0%"); grep shows `!=` again. [steps 5, 6]
- Re-run: 41 trace events, 11 job results, EQUIVALENT (100.0% step similarity). [step 7]
- After the run: git status showed no tracked change except the already-modified README; grep count of the original condition back to 1.

## Differences from the README Part 8 (real behaviour)
- Verdict line: real "[run] 000: act vs jenkins (trace): DIFFERS (90.2% step similarity)"; README "[run] 000: act vs jenkins: DIFFERS (90.2% step similarity)".
  The 90.2% matches. The "(trace)" and the extra lines ("[act] running act (trace) in <path>", "[act] act trace -> success (37 trace events...) in 25.2s",
  "[j2gha] not equivalent: 000 act (differs)") are not in the README (stale or abbreviated README text).
- RESULTS.md line: identical to the README text.
- Restore: README says EQUIVALENT (100.0% step similarity): matches; real line also has "(trace)" and the act/trace-event lines.
- The convert command prints a single summary line (not shown in README).
- `--tier act` alone compares against the earlier Jenkins trace result; this chapter did not re-run Jenkins (the one-line "act vs jenkins" says so by name only).
- Numbers that vary: timings (32.0 s, 36.1 s), line number 158 in RESULTS.md, line 1385 in the model.

## Do not claim
- That this proves the harness catches every kind of defect: it is one deliberate break, one example, in trace mode, on act.
- Anything about GitHub itself (no run on GitHub).
- That the Jenkins side was re-run in this chapter (only act was run).
- That 37 vs 41 is a general rule; it is what this run printed.
- Anything about audio.
