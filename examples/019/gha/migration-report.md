# Migration report: dvsa/dvsa-mobile-pipeline `ops/mobile_build.groovy`

- **Classification:** assisted (difficulty 36/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 25.9% (14 mapped, 9 approximated, 52 manual, 0 dropped)
- **Weighted step coverage (analysis):** 69.1%

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `assign branch = ${GIT_BRANCH}` | 13 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign target_location = ${TARGET_LOCATION}` | 14 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign git_repo_url = ${GIT_REPO_URL}` | 15 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign plugin_check = ${PLUGIN}` | 16 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign bucket = ${BUCKET}` | 24 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign file = ${IPA_FILE_NAME}` | 25 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign integration_test_check = ${INTEGRATION_TEST_CHECK}` | 26 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `deleteDir` | 41 |  | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `dir` | 71 |  | working-directory |  |
| ✅ mapped | `deleteDir` | 82 |  | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `decl mac_workspace = pwd(...)` | 84 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `dir` | 90 | NPM Install | working-directory |  |
| ✅ mapped | `dir` | 158 | Build | working-directory |  |
| ✅ mapped | `deleteDir` | 185 |  | run: workspace cleanup | runners are ephemeral; kept for parity |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `agent label 'master'` | 40 | main, Git Checkout | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `parallel (step)` | 48 | Git Checkout | sequential steps | scripted parallel branches serialised; split into jobs/matrix for real parallelism |
| 🟡 approximated | `stash '${target_location}'` | 73 |  | actions/upload-artifact@v4 | artifact hand-off between jobs; file permissions are not preserved; allowEmpty: no artifact is created when nothing matches (if-no-files-found: ignore) and the matching unstash then restores nothing (download by pattern) |
| 🟡 approximated | `agent label 'mac'` | 81 | main, NPM Install, Security Check, SonarQube, Unit Tests, NPM Build, Cordova Platform | runs-on: macos-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `unstash '${target_location}'` | 87 |  | actions/download-artifact@v4 | the stash was declared allowEmpty: downloaded by pattern, so an absent (empty) stash restores nothing and succeeds, while any other download error still fails the step |
| 🟡 approximated | `stash 'build'` | 168 |  | actions/upload-artifact@v4 | artifact hand-off between jobs; file permissions are not preserved; no matching files fails the step, as the stash does in Jenkins (if-no-files-found: error) |
| 🟡 approximated | `agent label 'master'` | 184 | main, Upload to S3, Generate bucket URL | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `unstash 'build'` | 187 |  | actions/download-artifact@v4 |  |
| 🔴 manual | `decl Globals = new Globals(...)` | 8 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `new Globals` | 8 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl CommonFunctions = new CommonFunctions(...)` | 9 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `new CommonFunctions` | 9 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl MobileCoreFunctions = new MobileCoreFunctions(...)` | 10 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `new MobileCoreFunctions` | 10 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl GitFunctions = new GitFunctions(...)` | 11 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `new GitFunctions` | 11 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (plugin_check.toString() == 'Yes')` | 18 |  | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (integration_test_check.toString() == 'Yes')` | 28 |  | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `log` | 47 | Git Checkout | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `git_check_out` | 50 | Git Checkout | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (plugin_check == 'Yes')` | 53 | Git Checkout | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (plugin_check == 'Yes')` | 59 | Git Checkout | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `log` | 66 | Git Checkout | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl WORKSPACE = pwd(...)` | 69 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `pwd` | 69 |  | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `log` | 72 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 74 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 86 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 88 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 95 | NPM Install | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `install` | 96 | NPM Install | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 97 | NPM Install | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 104 | Security Check | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `security` | 105 | Security Check | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 106 | Security Check | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 113 | SonarQube | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `sonar` | 114 | SonarQube | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 115 | SonarQube | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 122 | Unit Tests | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `testing` | 123 | Unit Tests | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 124 | Unit Tests | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 131 | NPM Build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `npmBuild` | 132 | NPM Build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 133 | NPM Build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 136 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (plugin_check == 'Yes')` | 137 |  | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `log` | 152 | Cordova Platform | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `configure` | 153 | Cordova Platform | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 154 | Cordova Platform | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 163 | Build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `build` | 164 | Build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 165 | Build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 170 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (integration_test_check == 'Yes')` | 171 |  | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `log` | 193 | Upload to S3 | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `upload` | 194 | Upload to S3 | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 195 | Upload to S3 | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 202 | Generate bucket URL | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `publish` | 203 | Generate bucket URL | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 204 | Generate bucket URL | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- line 34: timestamps {} around stage(s) 'Git Checkout', 'NPM Install', 'Security Check', 'SonarQube', 'Unit Tests', 'NPM Build', ... dropped (native in GitHub Actions)
- line 35: ansiColor {} around stage(s) 'Git Checkout', 'NPM Install', 'Security Check', 'SonarQube', 'Unit Tests', 'NPM Build', ... dropped (native in GitHub Actions)
- line 90: dir {} around stage(s) 'NPM Install', 'Security Check', 'SonarQube', 'Unit Tests', 'NPM Build', 'Configure Plugin', ... re-applied inside each enclosed stage and segment
- line 137: top-level if controls pipeline structure (dynamic): stage(s) 'Configure Plugin' kept as its nested steps, in an unnamed segment
- line 158: dir {} around stage(s) 'Build', 'Integration Tests' re-applied inside each enclosed stage and segment
- line 171: top-level if controls pipeline structure (dynamic): stage(s) 'Integration Tests' kept as its nested steps, in an unnamed segment
- 28 statement(s) outside any stage kept in source order in 6 unnamed segment(s) (from line(s) 8, 69, 82, 136, 168, 185)

## Stage graph

```text
pipeline [scripted] agent: label master
├── (outside any stage)
│   · <decl>×4, new Globals, new CommonFunctions, new MobileCoreFunctions, new GitFunctions, <assign>×12, <if>×2, deleteDir
├── Git Checkout
│   · CommonFunctions.log×3, parallel, GitFunctions.git_check_out×2, <if>×2, sh
├── (outside any stage)
│   · <decl>, pwd, dir, CommonFunctions.log×2, stash
├── (outside any stage)  [agent label]
│   · deleteDir, <decl>, pwd, CommonFunctions.log×2, unstash
├── NPM Install  [agent label]
│   · dir, CommonFunctions.log×2, MobileCoreFunctions.install
├── Security Check  [agent label]
│   · dir, CommonFunctions.log×2, MobileCoreFunctions.security
├── SonarQube  [agent label]
│   · dir, CommonFunctions.log×2, MobileCoreFunctions.sonar
├── Unit Tests  [agent label]
│   · dir, CommonFunctions.log×2, MobileCoreFunctions.testing
├── NPM Build  [agent label]
│   · dir, CommonFunctions.log×2, MobileCoreFunctions.npmBuild
├── (outside any stage)  [agent label]
│   · dir, CommonFunctions.log×3, <if>, stage, MobileCoreFunctions.configurePlugin
├── Cordova Platform  [agent label]
│   · dir, CommonFunctions.log×2, MobileCoreFunctions.configure
├── Build  [agent label]
│   · dir, CommonFunctions.log×2, MobileCoreFunctions.build
├── (outside any stage)  [agent label]
│   · dir, stash, CommonFunctions.log×3, <if>, stage, MobileCoreFunctions.testing
├── (outside any stage)  [agent label]
│   · deleteDir, unstash
├── Upload to S3  [agent label]
│   · CommonFunctions.log×2, MobileCoreFunctions.upload
└── Generate bucket URL  [agent label]
    · CommonFunctions.log×2, MobileCoreFunctions.publish
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 15 manual, ✅ 8 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`build`** (🔴 1 manual): downstream job -> reusable workflow call (wait) or workflow_dispatch via API (fire-and-forget).
  - Jenkins: [step `build`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [reuse-workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch) · [events-that-trigger-workflows #workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`agent`** (🟡 3 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`parallel`** (🟡 1 approximated): parallel stages -> independent jobs; failFast -> strategy.fail-fast only applies within a matrix.
  - Jenkins: [syntax #parallel](https://www.jenkins.io/doc/book/pipeline/syntax/#parallel)
  - GitHub Actions: [use-jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs) · [workflow-syntax #jobsjob_idneeds](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
- **`stash`** (🟡 2 approximated): stash/unstash between stages on different agents -> upload-artifact/download-artifact between jobs (file permissions are lost).
  - Jenkins: [step `stash`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`unstash`** (🟡 2 approximated)
  - Jenkins: [step `unstash`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`dir`** (✅ 3 mapped)
  - Jenkins: [step `dir`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsworking-directory](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsworking-directory)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
