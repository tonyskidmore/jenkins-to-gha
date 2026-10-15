# Migration report: jenkinsci/jenkins `Jenkinsfile`

- **Classification:** significant-redesign (difficulty 56/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 31.4% (6 mapped, 7 approximated, 21 manual, 1 dropped)
- **Weighted step coverage (analysis):** 64.5%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 13.0 | 20 |
| step mapping | 8.9 | 25 |
| plugin coupling | 15 | 15 |
| library opacity | 4 | 15 |
| runtime coupling | 6.0 | 10 |
| security identity | 6 | 10 |
| control flow | 3.0 | 5 |

- **Hard gates:** DynamicParallel (each forces at least significant-redesign; see *Blocking items*)
- **Unknown steps (3):** `discoverGitReferenceBuild`, `realtimeJUnit`, `withChecks` - plugin or shared-library steps the step catalog does not know, each a manual item below. If every one were mapped, the difficulty would be **46/100 - significant-redesign**.
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Secrets required

| Secret | Purpose |
|---|---|
| `LAUNCHABLE_JENKINS_JENKINS` | Jenkins credential 'launchable-jenkins-jenkins' |
| `LAUNCHABLE_JENKINS_ACCEPTANCE_TEST_HARNESS` | Jenkins credential 'launchable-jenkins-acceptance-test-harness' |
| `LAUNCHABLE_JENKINS_BOM` | Jenkins credential 'launchable-jenkins-bom' |

## Blocking items (hard gates)

- line 251: **DynamicParallel** - parallel(builds) → Emit a bounded matrix from a planning job (fromJSON) instead of runtime fan-out

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `options: disableConcurrentBuilds` |  |  | concurrency | GHA keeps only the latest pending run per group |
| ✅ mapped | `withCredentials string 'launchable-jenkins-jenkins'` | 29 | Record build | secrets -> step env |  |
| ✅ mapped | `withCredentials string 'launchable-jenkins-acceptance-test-harness'` | 50 | Record build | secrets -> step env |  |
| ✅ mapped | `sh` | 51 | Record build | run |  |
| ✅ mapped | `withCredentials string 'launchable-jenkins-bom'` | 53 | Record build | secrets -> step env |  |
| ✅ mapped | `sh` | 54 | Record build | run |  |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| ⚪ dropped | `options: buildDiscarder` |  |  | - | use artifact retention-days / repo settings |
| 🟡 approximated | `retry` | 22 | Record build | shell retry loop | only run steps are retried |
| 🟡 approximated | `node (in steps)` | 23 | Record build | inlined | nested agent allocation flattened |
| 🟡 approximated | `sh` | 35 | Record build | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 42 | Record build | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `stash 'sessionFile'` | 43 | Record build | actions/upload-artifact@v4 | artifact hand-off between jobs; file permissions are not preserved; no matching files fails the step, as the stash does in Jenkins (if-no-files-found: error) |
| 🟡 approximated | `parallel (step)` | 251 |  | sequential steps | scripted parallel branches serialised; split into jobs/matrix for real parallelism |
| 🔴 manual | `decl failFast = False` | 8 |  | - | Groovy variable assignment |
| 🔴 manual | `decl numBuildToKeep = ?` | 9 |  | - | Groovy variable assignment |
| 🔴 manual | `decl axes = [platforms: [linux, windows], jdks: [21, 25` | 16 |  | - | Groovy variable assignment |
| 🔴 manual | `checkoutSCM` | 24 | Record build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl launchableName = env.BUILD_TAG.replaceAll(...)` | 34 | Record build | - | Groovy variable assignment from a step |
| 🔴 manual | `replaceAll` | 34 | Record build | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `combinations` | 36 | Record build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl ( = it` | 37 | Record build | - | Groovy variable assignment |
| 🔴 manual | `if (platform == 'windows' && jdk != axes.jdks.last())` | 38 | Record build | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `decl sessionFile = launchable-session-${platform}-jdk${` | 41 | Record build | - | Groovy variable assignment |
| 🔴 manual | `decl builds = []` | 60 |  | - | Groovy variable assignment |
| 🔴 manual | `combinations` | 62 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl ( = it` | 63 |  | - | Groovy variable assignment |
| 🔴 manual | `if (platform == 'windows' && jdk != axes.jdks.last())` | 64 |  | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `assign builds["${platform}-jdk${jdk}"] = ` | 67 |  | - | Groovy variable assignment |
| 🔴 manual | `decl athAxes = [platforms: [linux], jdks: [21], browser` | 215 |  | - | Groovy variable assignment |
| 🔴 manual | `combinations` | 220 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl ( = it` | 221 |  | - | Groovy variable assignment |
| 🔴 manual | `assign builds["ath-${platform}-jdk${jdk}-${browser}"] = ` | 222 |  | - | Groovy variable assignment |
| 🔴 manual | `assign builds.failFast = failFast` | 250 |  | - | Groovy variable assignment |
| 🔴 manual | `maybePublishIncrementals` | 252 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- line 62: stage(s) '${platform.capitalize()} - JDK ${jdk} - Checkout', '${platform.capitalize()} - JDK ${jdk} - Build / Test', '${platform.capitalize()} - JDK ${jdk} - Publish' nested in 'combinations' (plugin/library block) kept as its nested steps, in an unnamed segment
- line 251: parallel() over a runtime-built map 'builds' (dynamic fan-out)
- 10 statement(s) outside any stage kept in source order in 2 unnamed segment(s) (from line(s) 8, 60)

## Stage graph

```text
pipeline [scripted]
├── (outside any stage)
│   · <decl>×3
├── Record build
│   · retry, node, infra.checkoutSCM, withCredentials×3, <decl>×3, env.BUILD_TAG.replaceAll, sh×4, axes.values.combinations …
└── (outside any stage)
    · <decl>×4, axes.values.combinations, <if>, <return>, <assign>×3, athAxes.values.combinations, parallel, infra.maybePublishIncrementals
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 15 manual): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`sh`** (🟡 2 approximated, ✅ 2 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`retry`** (🟡 1 approximated): no native step retry; use a shell loop or a retry action.
  - Jenkins: [step `retry`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepscontinue-on-error](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepscontinue-on-error)
- **`node`** (🟡 1 approximated)
  - Jenkins: [step `node`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [self-hosted-runners](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners)
- **`stash`** (🟡 1 approximated): stash/unstash between stages on different agents -> upload-artifact/download-artifact between jobs (file permissions are lost).
  - Jenkins: [step `stash`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`parallel`** (🟡 1 approximated): parallel stages -> independent jobs; failFast -> strategy.fail-fast only applies within a matrix.
  - Jenkins: [syntax #parallel](https://www.jenkins.io/doc/book/pipeline/syntax/#parallel)
  - GitHub Actions: [use-jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs) · [workflow-syntax #jobsjob_idneeds](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
- **`buildDiscarder`** (⚪ 1 dropped): no per-count run retention; artifact retention-days and the repository log retention setting.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepswith](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepswith) · [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- **`disableConcurrentBuilds`** (✅ 1 mapped): abortPrevious true -> cancel-in-progress true.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency) · [control-workflow-concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) · [workflow-syntax #concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
- **`withCredentials`** (✅ 3 mapped): file/SSH credentials must be materialised by a step; OIDC replaces long-lived cloud keys.
  - Jenkins: [step `withCredentials`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [use-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) · [secrets](https://docs.github.com/en/actions/concepts/security/secrets) · [secrets](https://docs.github.com/en/actions/reference/security/secrets)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
