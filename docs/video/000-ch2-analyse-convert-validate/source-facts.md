# Source facts: chapter "Analyse, Convert, Validate" (examples/000/README.md Parts 2 to 4)

Captured with `nx capture local` on this machine (Jenkins controller running, local Docker images). Captures:
captures/parts-2-4.txt (the three README commands) and captures/supporting.txt (read-only greps of generated files).

## Safe claims
- Analyse: parses the Jenkinsfile with Jenkins' own Groovy, builds an intermediate model, scores the migration. Real output:
  declarative, difficulty 23 (assisted), coverage 78.5%, convertibility automatic. [README Part 2; capture parts-2-4 #0]
- Findings the analysis lists (RESULTS.md Analysis section): GroovyWhenExpression (3), InputGate (line 204),
  PostConditionGap, ScriptBlocks, HashedCron (H 2 * * 1-5), CredentialBinding (2). [capture supporting #0]
- Convert: 9 jobs; REAL counts 41 mapped, 33 approximated, 1 manual (3 dropped) -> automation 81.0%. [capture parts-2-4 #1;
  report header, which now reads "Automated mapping (effort estimate, not correctness)"]. README Part 3 shows the same figures
  (an older README said 49 / 30 / 83.6%). Re-captured 2026-10-11 after commit 8a1c549 (2026-10-06); the first
  recording said 8 jobs, 42 / 31 / 81.8%.
- Job plan: prepare-sources, quality-unit-tests, quality-lint, quality-integration-tests, compatibility, publish, deploy-gate,
  deploy, post. [capture supporting #1; README Part 3 table, which lists deploy-gate since 2026-10-11]
- deploy-gate ("Deploy (when)"): Deploy's `when` has `beforeInput true`; the gate decides it once "so a skipped stage asks for no
  approval". [migration-report.md row `stage 'Deploy' beforeInput`; Jenkinsfile lines 200-202]
- Jobs hand the workspace on as `j2gha-ws-<job>` artifacts (why the workflow is ~2600 lines). [workflow.yml; CLAUDE.md]
- Deploy job uses `environment: Deploy`; required reviewers must be added to that environment by a person. [README Part 3; workflow.yml line 2115]
- `when not expression endsWith -SNAPSHOT` becomes an `if:` using endsWith. [capture supporting #2]
- Hashed cron becomes fixed `7 2 * * 1-5`. Three secrets listed in the report. [README Part 3; workflow.yml; report]
- Dropped: post unstable, buildDiscarder, timestamps. Manual: currentBuild.displayName assignment. [report]
- Validate: actionlint 0 (0 shellcheck), zizmor 0, policy 1 -> OK. [capture parts-2-4 #2]
- The one policy warning: untranslated Groovy in the post job's echo step. Real workflow text contains
  `${J2GHA_TODO_currentBuild_currentResult}` (README Part 4 shows the same). [capture supporting #4; validation.json]

## Do not claim
- That the converted workflow behaves the same as the Jenkinsfile: that is proven only by the differential run (Parts 5 to 7), not covered here.
- That it has been run on GitHub, or that the deploy approval is configured: reviewers must be added by a person.
- Counts from older README versions (49, 30, 83.6%; 42, 31, 81.8%).
- "Every action is pinned to a SHA": only partly checked (spot check of upload/download-artifact); zizmor reported 0 findings.
- That zero validator findings means correct: they check structure and security, not behaviour.
- That the post job's warning is the only thing needing human attention: the approximated and manual items need review too.
