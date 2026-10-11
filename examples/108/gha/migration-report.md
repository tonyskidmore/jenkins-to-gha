# Migration report: h2oai/h2o-3 `docker/Jenkinsfile-build-docker`

- **Classification:** significant-redesign (difficulty 60/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 42.6% (17 mapped, 15 approximated, 29 manual, 0 dropped)
- **Weighted step coverage (analysis):** 74.1%

## Secrets required

| Secret | Purpose |
|---|---|
| `H2O_AWS_CT_JENKINS_SHARED_SERVICE_PROD_USR` | Jenkins credential 'H2O-AWS_CT-JENKINS-SHARED-SERVICE-PROD' |
| `H2O_AWS_CT_JENKINS_SHARED_SERVICE_PROD_PSW` | Jenkins credential 'H2O-AWS_CT-JENKINS-SHARED-SERVICE-PROD' |

## Blocking items (hard gates)

- line ?: **SharedLibrary** - test-shared-library@dai-updated → Library steps are opaque to static analysis; map them to composite actions/reusable workflows
- line 97: **ExternalGroovyLoad** - load(scripts/jenkins/groovy/pipelineContext.groovy) → Inline the loaded logic as scripts/composite actions
- line 174: **DynamicParallel** - parallel(targets.collectEntries(...)) → Emit a bounded matrix from a planning job (fromJSON) instead of runtime fan-out

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `parameters: booleanParam forceBuild` | 15 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: booleanParam publish` | 16 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string h2oBranch` | 17 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: booleanParam noCache` | 18 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `cleanWs` | 94 | Checkout and Init | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `checkout scm` | 95 | Checkout and Init | actions/checkout@v4 |  |
| ✅ mapped | `dir` | 111 | Checkout and Init | working-directory |  |
| ✅ mapped | `withCredentials aws 'H2O-AWS_CT-JENKINS-SHARED-SERVICE-PROD'` | 112 | Checkout and Init | secrets -> step env |  |
| ✅ mapped | `sh` | 114 | Checkout and Init | run |  |
| ✅ mapped | `sh` | 115 | Checkout and Init | run |  |
| ✅ mapped | `sh` | 116 | Checkout and Init | run |  |
| ✅ mapped | `sh` | 117 | Checkout and Init | run |  |
| ✅ mapped | `sh` | 118 | Checkout and Init | run |  |
| ✅ mapped | `sh` | 119 | Checkout and Init | run |  |
| ✅ mapped | `sh` | 120 | Checkout and Init | run |  |
| ✅ mapped | `sh` | 121 | Checkout and Init | run |  |
| ✅ mapped | `sh` | 122 | Checkout and Init | run |  |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `node (in steps)` | 92 | Checkout and Init | inlined | nested agent allocation flattened |
| 🟡 approximated | `docker.image().inside` | 113 | Checkout and Init | docker run wrapper | consider a job container instead |
| 🟡 approximated | `stash 'docker-sources'` | 125 | Checkout and Init | actions/upload-artifact@v4 | artifact hand-off between jobs; file permissions are not preserved; no matching files fails the step, as the stash does in Jenkins (if-no-files-found: error) |
| 🟡 approximated | `buildInParallel() (local helper method)` | 133 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext substituted |
| 🟡 approximated | `buildInParallel() (local helper method)` | 134 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext substituted |
| 🟡 approximated | `buildInParallel() (local helper method)` | 136 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext substituted |
| 🟡 approximated | `buildInParallel() (local helper method)` | 141 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext, targets substituted |
| 🟡 approximated | `buildInParallel() (local helper method)` | 143 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext substituted |
| 🟡 approximated | `buildInParallel() (local helper method)` | 152 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext, targets substituted |
| 🟡 approximated | `buildInParallel() (local helper method)` | 154 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext substituted |
| 🟡 approximated | `buildInParallel() (local helper method)` | 155 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext substituted |
| 🟡 approximated | `buildInParallel() (local helper method)` | 156 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext substituted |
| 🟡 approximated | `buildInParallel() (local helper method)` | 169 |  | inlined | body of the Jenkinsfile helper method inlined with pipelineContext, targets substituted |
| 🟡 approximated | `parallel (step)` | 174 |  | sequential steps | scripted parallel branches serialised; split into jobs/matrix for real parallelism |
| 🔴 manual | `decl _ = <not implemented yet for class: org.codehaus.g` | 1 |  | - | Groovy variable assignment |
| 🔴 manual | `assign DEFAULT_LABEL = h2o3_linux` | 4 |  | - | Groovy variable assignment |
| 🔴 manual | `assign H2O_ECR = 353750902984.dkr.ecr.us-east-1.amazonaws` | 6 |  | - | Groovy variable assignment |
| 🔴 manual | `buildSummary` | 9 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `addStagesSummary` | 11 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign JDK_VERSIONS = [8, 11, 17]` | 24 |  | - | Groovy variable assignment |
| 🔴 manual | `assign JDK_VERSIONS_PY_R = [8, 11, 17]` | 25 |  | - | Groovy variable assignment |
| 🔴 manual | `decl pipelineContext = <not implemented yet for class: ` | 86 |  | - | Groovy variable assignment |
| 🔴 manual | `decl checkoutStageName = Checkout and Init` | 90 |  | - | Groovy variable assignment |
| 🔴 manual | `refreshStage` | 93 | Checkout and Init | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl scmEnv = checkout(...)` | 95 | Checkout and Init | - | Groovy variable assignment from a step |
| 🔴 manual | `decl pipelineContextFactory = load(...)` | 97 | Checkout and Init | - | Groovy variable assignment from a step |
| 🔴 manual | `load` | 97 | Checkout and Init | placeholder step | dynamic step with no deterministic mapping |
| 🔴 manual | `assign pipelineContext = pipelineContextFactory(...)` | 98 | Checkout and Init | - | Groovy variable assignment from a step |
| 🔴 manual | `pipelineContextFactory` | 98 | Checkout and Init | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl currentVersion = pipelineContext.getBuildConfig().` | 99 | Checkout and Init | - | Groovy variable assignment from a step |
| 🔴 manual | `getDefaultImageVersion` | 99 | Checkout and Init | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign currentBuild.displayName = v${currentVersion} #${c` | 100 | Checkout and Init | - | Groovy variable assignment |
| 🔴 manual | `assign PYTHON_VERSIONS = pipelineContext.getBuildConfig()` | 130 |  | - | Groovy variable assignment |
| 🔴 manual | `assign R_VERSIONS = pipelineContext.getBuildConfig().R_VE` | 131 |  | - | Groovy variable assignment |
| 🔴 manual | `decl pythonImages = []` | 137 |  | - | Groovy variable assignment |
| 🔴 manual | `each` | 138 |  | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `decl componentImages = []` | 144 |  | - | Groovy variable assignment |
| 🔴 manual | `each` | 145 |  | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `each` | 148 |  | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `assign componentImages = dev-mojocompat` | 151 |  | - | Groovy variable assignment |
| 🔴 manual | `decl componentJdkImages = []` | 158 |  | - | Groovy variable assignment |
| 🔴 manual | `each` | 159 |  | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `each` | 164 |  | - | Groovy method / helper call - port logic to a script |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- line 88: ansiColor {} around stage(s) 'checkoutStageName' dropped (native in GitHub Actions)
- line 89: timestamps {} around stage(s) 'checkoutStageName' dropped (native in GitHub Actions)
- 30 statement(s) outside any stage kept in source order in 2 unnamed segment(s) (from line(s) 1, 130)

## Stage graph

```text
pipeline [scripted]
├── (outside any stage)
│   · <decl>×3, <assign>×4, buildSummary, buildSummary.get.addStagesSummary
├── Checkout and Init
│   · node, buildSummary.refreshStage, cleanWs, <decl>×3, checkout, load, <assign>×2, pipelineContextFactory …
└── (outside any stage)
    · <assign>×8, buildInParallel×10, <decl>×3, PYTHON_VERSIONS.each×2, R_VERSIONS.each×2, JDK_VERSIONS.each, JDK_VERSIONS_PY_R.each×2
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 23 manual, 🟡 10 approximated): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`node`** (🟡 1 approximated)
  - Jenkins: [step `node`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [self-hosted-runners](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners)
- **`docker`** (🟡 1 approximated)
  - Jenkins: [docker](https://www.jenkins.io/doc/book/pipeline/docker/)
  - GitHub Actions: [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container) · [use-docker-service-containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers) · [publish-docker-images](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- **`stash`** (🟡 1 approximated): stash/unstash between stages on different agents -> upload-artifact/download-artifact between jobs (file permissions are lost).
  - Jenkins: [step `stash`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`parallel`** (🟡 1 approximated): parallel stages -> independent jobs; failFast -> strategy.fail-fast only applies within a matrix.
  - Jenkins: [syntax #parallel](https://www.jenkins.io/doc/book/pipeline/syntax/#parallel)
  - GitHub Actions: [use-jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs) · [workflow-syntax #jobsjob_idneeds](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
- **`parameters`** (✅ 4 mapped): inputs are empty on push/schedule events; choose defaults explicitly.
  - Jenkins: [syntax #parameters](https://www.jenkins.io/doc/book/pipeline/syntax/#parameters)
  - GitHub Actions: [workflow-syntax #onworkflow_dispatchinputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
- **`checkout`** (✅ 1 mapped, ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
- **`dir`** (✅ 1 mapped)
  - Jenkins: [step `dir`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsworking-directory](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsworking-directory)
- **`withCredentials`** (✅ 1 mapped): file/SSH credentials must be materialised by a step; OIDC replaces long-lived cloud keys.
  - Jenkins: [step `withCredentials`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [use-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) · [secrets](https://docs.github.com/en/actions/concepts/security/secrets) · [secrets](https://docs.github.com/en/actions/reference/security/secrets)
- **`sh`** (✅ 9 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
