# Example 102: local twin of example 002

Derived from [example 002](../002/README.md) (jenkinsci/jenkins, `Jenkinsfile` at `d076aeb`). The original is kept
verbatim in `examples/002/`; this copy is edited only as far as needed for the pipeline to run to completion on the
harness's Jenkins in full mode. Every edited or inserted line is marked `// j2gha-local:` / `# j2gha-local:` in the
Jenkinsfile. Line numbers below are the original's (the twin's in brackets where the inserted lines shift them).

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 17 | `platforms: ['linux', 'windows']` | `platforms: ['linux']` | no Windows agent in the harness: the `windows` cell runs `bat` steps, which fail on Linux. The `if (platform == 'windows' ...)` guards, the `isUnix()` branches and the `bat` steps stay in the code, never selected | the `axes` map, `combinations {}`, the two JDK cells (21, 25) and the closures-in-map `builds[...]` fan-out |
| 24, 79 [80] | `infra.checkoutSCM()` | `checkout scm` | `infra` is the ci.jenkins.io shared library; the harness stubs it, so nothing was checked out and the stand-in build would have had no repository (and no `git` for the changelist) | the `node` per branch, the per-branch Checkout stage; `infra.withArtifactCachingProxy {}` and `infra.maybePublishIncrementals()` stay as stubs |
| - [79] | (none) | `deleteDir()` inserted before the per-branch `checkout scm` | the original branches run on throwaway Kubernetes pods; here every `node` is the built-in node, so the branch that reuses Record build's workspace would find its `launchable-session-*.txt` files, which `git add . && git diff --exit-code HEAD` (line 129, unchanged) would report as a dirty tree | the ATH branch already does `deleteDir(); checkout scm` ("Just to be safe"), so this is the original's own idiom |
| 35, 51, 54, 204 [219] | `launchable verify && launchable record ...` | each command behind `echo` | no Launchable CLI (the full-mode run of 002 stopped here: `launchable: not found`) | the `withCredentials(string ...)` wrappers around them, with the fake `LAUNCHABLE_TOKEN` |
| 42 | `launchable record session ... >${sessionFile}` | `echo launchable record session ... >${sessionFile}` | as above; the redirection is kept so the session file exists for `stash name: sessionFile`, the `unstash` in `dir(tmpDir)` and `readFile(sessionFile).trim()` (the echoed command is the "session id" the Publish stage echoes back) | the stash/unstash hand-off of one file per cell between Record build and the branches |
| 117 | `launchable subset ...` | unchanged | only reached with `env.CHANGE_ID` (pull requests); the harness runs branch scenarios | - |
| 126-131 [127-146] | `realtimeJUnit(healthScaleFactor: 20.0, testResults: '*/target/surefire-reports/*.xml,target/vitest-reports/*.xml') { infra.runMaven(mavenOptions, jdk); if (isUnix()) { sh 'git add . && git diff --exit-code HEAD' } }` | the body runs directly inside `withChecks`, `infra.runMaven` replaced by a `sh` stand-in, followed by `junit healthScaleFactor: 20.0, testResults: <same patterns>` | `realtimeJUnit` is from the junit-realtime-test-reporter plugin, which the controller does not have (the harness stubs an unknown step: no test results would be recorded). `infra.runMaven` would run `mvn clean install` of Jenkins core: hours and gigabytes. The stand-in echoes the `mavenOptions` list and writes exactly what the stage reads afterwards: `core/target/surefire-reports/TEST-jenkins.j2gha.LocalTest.xml` (2 cases) and `target/vitest-reports/vitest.xml` (1 case) for the junit patterns, a `*.dumpstream` for the first `archiveArtifacts`, `war/target/jenkins.war`, the `changelist` file in `tmpDir` that `readFile(changelistF)` reads, and `jenkins-war-2.999<changelist>.war` + `jenkins-core-2.999<changelist>.jar` in `m2repo` for the second `archiveArtifacts` (`**/*$changelist/*$changelist*`). All of it is under `target` (gitignored by the repository), so the unchanged `git add . && git diff --exit-code HEAD` check still passes | `withChecks`, `timeout`, `dir(tmpDir)`, the `mavenOptions` list, the `git diff` cleanliness check, both archives, `recordCoverage`/`recordIssues` (stubbed by the harness on Jenkins) and the `launchable record tests` echo |
| 231 [246-251] | `sh "bash ath.sh ${jdk} ${browser}"` | `echo bash ath.sh ...` plus a one-case `target/ath-reports/TEST-j2gha.AthSmokeTest.xml` | `ath.sh` builds the war and runs the acceptance-test-harness under docker-compose with a Firefox container; no Docker daemon here | the ATH branch's `retry`, `node`, `deleteDir`, `checkout scm`, `withChecks`, `infra.withArtifactCachingProxy {}` and the `junit` |
| 233 [253] | `junit testResults: 'target/ath-reports/TEST-*.xml', testDataPublishers: [[$class: 'AttachmentPublisher']]` | `testDataPublishers` dropped | the junit-attachments plugin is not installed; Jenkins would fail to instantiate the publisher | the `junit` step itself |

Unchanged on purpose: `properties([buildDiscarder(...), disableConcurrentBuilds(...)])` (silent no-op on the controller),
`retry(conditions: [kubernetesAgent(handleNonKubernetes: true), nonresumable()], count: 2)` (the localiser replaces a
`retry` with conditions by a plain body run, and the 002 console never rejected the condition symbols, so `retry(2)`
was not needed), `pwd(tmp: true)`, `timeout`, `withCredentials`, `archiveArtifacts`, `recordCoverage`, the six
`recordIssues`, `discoverGitReferenceBuild` (not reached: `JOB_NAME` has no folder), `builds.failFast` and `parallel
builds`.

What this twin tests: the scripted closures-in-map fan-out (`builds["${platform}-jdk${jdk}"] = { ... }` built inside
`axes.values().combinations {}`, then `parallel builds`), with per-branch `stage()`s named from GStrings, a stash in
one `node` consumed in another branch's `node` under `dir(tmpDir)`, `readFile` of a file the build wrote, `junit` with
two patterns, `archiveArtifacts` with `allowEmptyArchive` inside `dir(m2repo)` (outside the workspace, under `@tmp`),
and `retry` with conditions. In full mode the outputs comparison gets 7 JUnit cases (3 per JDK cell: 2 surefire and
1 vitest; 1 ATH case) and 4 archived files (one `*.dumpstream` per JDK cell; the war and the jar from `m2repo` only
for the JDK 21 cell, because the `m2repo` archive sits inside `if (platform == 'linux' && jdk == axes['jdks'][0])`).

Expected on the converted side (`uv run j2gha convert 102`: 1 job, automation 36.1%): the converter emits only the
*Record build* job; `axes.values().combinations {}` and the closure bodies assigned into `builds[...]` are manual
placeholders, so the three parallel branches (`Linux - JDK 21/25 - Checkout / Build / Test / Publish` and the ATH
branch, which has no stage) are not emitted at all, and `parallel builds` has nothing to fan out. Inside Record
build, the Groovy locals `launchableName`, `platform`, `jdk` and `sessionFile` are manual items left as `${...}` in the
shell text, so the step `echo launchable record session ... >${sessionFile}` fails with an ambiguous redirect and the
following `stash` would look for a file literally named `sessionFile`. **Expected verdict: Jenkins SUCCESS, act
failure at *Record build*, *differs*** (one failing stage plus missing stages), which is the correct statement of the
002 gap: closures-in-map parallel and Groovy-variable interpolation in `sh` are not converted.

Scenario: `uv run j2gha run 102 --tier jenkins,act --mode full` (default branch `master`, so `env.CHANGE_ID` is unset
and the Launchable subset block is skipped). The Jenkins run clones jenkinsci/jenkins four times (Record build and
the three branches, about 60-90 s each) and uses up to three executors at once.

Results: to be recorded by the run.

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **failure** at *Checkout*, verdict **differs**; JUnit cases 7 (Jenkins) / 0 (act), differs; archived files 3 (Jenkins) / 0 (act), differs. The `builds[...]` closures and the `combinations` loop are manual placeholders, so only *Record build* exists on the converted side and its Groovy locals (`sessionFile`) are left as `${...}` in shell text; the Jenkins reference succeeds with 7 JUnit cases and 4 archived files.
