# Migration report: oracle/weblogic-kubernetes-operator `Jenkinsfile`

- **Classification:** significant-redesign (difficulty 46/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 78.0% (55 mapped, 37 approximated, 7 manual, 0 dropped)
- **Weighted step coverage (analysis):** 76.1%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 10 | 20 |
| step mapping | 6.0 | 25 |
| plugin coupling | 3.0 | 15 |
| library opacity | 0.0 | 15 |
| runtime coupling | 4.0 | 10 |
| security identity | 2 | 10 |
| control flow | 0.0 | 5 |

- **Hard gates:** ExternalGroovyLoad (each forces at least significant-redesign; see *Blocking items*)
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Secrets required

| Secret | Purpose |
|---|---|
| `WKT_OCIR_CREDS_USR` | Jenkins credential 'wkt-ocir-creds' |
| `WKT_OCIR_CREDS_PSW` | Jenkins credential 'wkt-ocir-creds' |

## Blocking items (hard gates)

- line 219: **ExternalGroovyLoad** - evaluate(${def script = ""; params.each { k, v -> script += "env.${k} = '''${v}'''
" }; return script}) → Inline the loaded logic as scripts/composite actions

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `stage 'Run integration tests' post always` |  | Run integration tests | if: (always()) && (steps.s25.outcome == 'success') |  |
| ✅ mapped | `stage 'Filter unwanted branches' post always` |  | Filter unwanted branches | if: (always()) && (steps.s1.outcome == 'success') |  |
| ✅ mapped | `environment ocir_creds` | 49 |  | env |  |
| ✅ mapped | `environment kind_name` | 56 |  | env |  |
| ✅ mapped | `environment kind_network` | 57 |  | env |  |
| ✅ mapped | `environment registry_name` | 58 |  | env |  |
| ✅ mapped | `environment registry_port` | 60 |  | env |  |
| ✅ mapped | `environment wle_download_url` | 63 |  | env |  |
| ✅ mapped | `parameters: choice MAVEN_PROFILE_NAME` | 67 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string IT_TEST` | 77 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string OPERATOR_LOG_LEVEL` | 81 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: choice KIND_VERSION` | 85 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: choice KUBE_VERSION` | 93 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string HELM_VERSION` | 114 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: choice ISTIO_VERSION` | 118 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: booleanParam PARALLEL_RUN` | 131 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string NUMBER_OF_THREADS` | 135 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string WDT_DOWNLOAD_URL` | 139 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string WIT_DOWNLOAD_URL` | 143 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string REMOTECONSOLE_VERSION` | 147 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string TEST_IMAGES_REPO` | 151 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: choice BASE_IMAGES_REPO` | 155 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string WEBLOGIC_IMAGE_NAME` | 159 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string WEBLOGIC_IMAGE_TAG` | 163 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string FMWINFRA_IMAGE_NAME` | 167 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string FMWINFRA_IMAGE_TAG` | 171 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string DB_IMAGE_NAME` | 175 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string DB_IMAGE_TAG` | 179 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string MONITORING_EXPORTER_BRANCH` | 183 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string MONITORING_EXPORTER_WEBAPP_VERSION` | 187 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string PROMETHEUS_CHART_VERSION` | 191 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string GRAFANA_CHART_VERSION` | 195 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: booleanParam COLLECT_LOGS_ON_SUCCESS` | 199 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `stage 'Filter unwanted branches' when` | 208 | Filter unwanted branches | if: (env.CHANGE_ID != '' || env.BRANCH_NAME == 'main' || env.BRANCH_NAME == 'release/4.0' || env.BRANCH_NAME == 'release/3.4') | evaluated once at stage entry against env |
| ✅ mapped | `echo` | 218 | Workaround JENKINS-41929 Parameters bug | run: echo |  |
| ✅ mapped | `sh` | 234 | Echo environment | run |  |
| ✅ mapped | `decl knd = params.KIND_VERSION` | 245 | Echo environment | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl k8s = params.KUBE_VERSION` | 246 | Echo environment | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `sh` | 275 | Build WebLogic Kubernetes Operator | run |  |
| ✅ mapped | `sh` | 283 | Make Workspace bin directory | run |  |
| ✅ mapped | `sh` | 292 | Install Helm | run |  |
| ✅ mapped | `sh` | 306 | Run Helm installation tests | run |  |
| ✅ mapped | `sh` | 320 | Install kubectl | run |  |
| ✅ mapped | `sh` | 334 | Install kind | run |  |
| ✅ mapped | `sh` | 345 | Preparing Integration Test Environment | run |  |
| ✅ mapped | `sh` | 347 | Preparing Integration Test Environment | run |  |
| ✅ mapped | `sh` | 357 | Start registry container | run |  |
| ✅ mapped | `sh` | 380 | Create kind cluster | run |  |
| ✅ mapped | `decl res = 0` | 545 | Run integration tests | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `sh` | 558 | Run integration tests | run |  |
| ✅ mapped | `withCredentials usernamePassword 'wkt-ocir-creds'` | 610 | Run integration tests | secrets -> step env |  |
| ✅ mapped | `sh` | 613 | Run integration tests | run |  |
| ✅ mapped | `sh` | 636 | Run integration tests | run |  |
| ✅ mapped | `archiveArtifacts` | 656 | Run integration tests | actions/upload-artifact@v4 |  |
| ✅ mapped | `sh` | 665 | Filter unwanted branches | run |  |
| 🟡 approximated | `tools maven 'maven-3.8.7'` |  |  | runner-provided Maven | GitHub-hosted Ubuntu runners include Maven; pin a version with a setup action if required |
| 🟡 approximated | `tools jdk 'jdk25'` |  |  | actions/setup-java@v4 | Jenkins tool name mapped by version heuristics |
| 🟡 approximated | `options: timeout` |  |  | timeout-minutes: 800 (per job) | Jenkins timeout covers the whole pipeline |
| 🟡 approximated | `agent label 'large-ol9u4'` | 36 | Filter unwanted branches, Sync | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `environment ocir_host` | 47 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment wko_tenancy` | 48 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment outdir` | 51 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment result_root` | 52 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment pv_root` | 53 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment kubeconfig_file` | 54 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment registry_host` | 59 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment start_time` | 62 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `script {}` | 220 | Workaround JENKINS-41929 Parameters bug | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (env.CHANGE_ID)` | 221 | Workaround JENKINS-41929 Parameters bug | if: env.CHANGE_ID != '' |  |
| 🟡 approximated | `environment runtime_path` | 231 | Echo environment | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `script {}` | 244 | Echo environment | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `echo` | 261 | Echo environment | run: echo |  |
| 🟡 approximated | `if (env.JOB_NAME == 'wko-kind-k8sversion')` | 262 | Echo environment | if: env.JOB_NAME == 'wko-kind-k8sversion' |  |
| 🟡 approximated | `withMaven` | 274 | Build WebLogic Kubernetes Operator | body inlined | wrapper semantics not reproduced |
| 🟡 approximated | `sh` | 282 | Make Workspace bin directory | run |  |
| 🟡 approximated | `environment runtime_path` | 289 | Install Helm | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `withMaven` | 305 | Run Helm installation tests | body inlined | wrapper semantics not reproduced |
| 🟡 approximated | `environment runtime_path` | 316 | Install kubectl | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment KUBE_VERSION` | 317 | Install kubectl | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment runtime_path` | 331 | Install kind | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `echo` | 346 | Preparing Integration Test Environment | run: echo |  |
| 🟡 approximated | `echo` | 348 | Preparing Integration Test Environment | run: echo |  |
| 🟡 approximated | `environment runtime_path` | 354 | Start registry container | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment runtime_path` | 376 | Create kind cluster | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment kind_image` | 377 | Create kind cluster | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment runtime_path` | 540 | Run integration tests | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `script {}` | 543 | Run integration tests | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `assign res = sh(...)` | 546 | Run integration tests | run step (captured output not propagated) | write values to $GITHUB_OUTPUT/$GITHUB_ENV |
| 🟡 approximated | `sh` | 546 | Run integration tests | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `withMaven` | 609 | Run integration tests | body inlined | wrapper semantics not reproduced |
| 🟡 approximated | `junit` | 658 | Run integration tests | upload-artifact + step summary | no native test UI; failing tests cannot mark the run UNSTABLE |
| 🟡 approximated | `stage 'Sync' when` | 684 | Sync | if: ((env.BRANCH_NAME == 'main' || env.BRANCH_NAME == 'release/4.0' || env.BRANCH_NAME == 'release/3.4')) && ((!(github.event_name == 'schedule') || (startsWith(env.TAG_NAME, 'v') && !contains(env.TAG_NAME, '/')))) | evaluated once at stage entry against env |
| 🔴 manual | `evaluate` | 219 | Workaround JENKINS-41929 Parameters bug | placeholder step | dynamic step with no deterministic mapping |
| 🔴 manual | `assign env.MONITORING_EXPORTER_WEBAPP_VERSION = default_m` | 224 | Workaround JENKINS-41929 Parameters bug | - | Groovy variable assignment |
| 🔴 manual | `if (knd != null && k8s != null)` | 247 | Echo environment | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `assign currentBuild.description = ${GIT_BRANCH} ${KUBE_VE` | 263 | Echo environment | - | Groovy variable assignment |
| 🔴 manual | `assign currentBuild.description = ${GIT_BRANCH} ${MAVEN_P` | 265 | Echo environment | - | Groovy variable assignment |
| 🔴 manual | `if (res != 0 )` | 552 | Run integration tests | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `build job: wkt-sync` | 695 | Sync | workflow_call / workflow_dispatch | downstream Jenkins job must be migrated; trigger with `gh workflow run` or a reusable workflow |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Stage graph

```text
pipeline [declarative] agent: label large-ol9u4
├── Filter unwanted branches  [when; post: always]
│   ├── Workaround JENKINS-41929 Parameters bug
│   │   · echo, evaluate, script, <if>, <assign>
│   ├── Echo environment
│   │   · sh, script, <decl>×3, <if>×4, kind_k8s_map.get, <assign>×3, k8s_map.get, error …
│   ├── Build WebLogic Kubernetes Operator
│   │   · withMaven, sh
│   ├── Make Workspace bin directory
│   │   · sh×2
│   ├── Install Helm
│   │   · sh
│   ├── Run Helm installation tests
│   │   · withMaven, sh
│   ├── Install kubectl
│   │   · sh
│   ├── Install kind
│   │   · sh
│   ├── Preparing Integration Test Environment
│   │   · sh×2, echo×2
│   ├── Start registry container
│   │   · sh
│   ├── Create kind cluster
│   │   · sh
│   └── Run integration tests  [post: always]
│       · script, <decl>, <assign>×2, sh×3, <if>, error, withMaven, withCredentials
└── Sync  [when]
    · build
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 5 manual, 🟡 6 approximated, ✅ 3 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`build`** (🔴 1 manual): downstream job -> reusable workflow call (wait) or workflow_dispatch via API (fire-and-forget).
  - Jenkins: [step `build`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [reuse-workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch) · [events-that-trigger-workflows #workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- **`environment`** (🟡 17 approximated, ✅ 6 mapped): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
- **`when`** (🟡 1 approximated, ✅ 1 mapped): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`sh`** (🟡 2 approximated, ✅ 15 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`tools`** (🟡 2 approximated): tool installers -> actions/setup-* (setup-java, setup-node...) with built-in caching.
  - Jenkins: [syntax #tools](https://www.jenkins.io/doc/book/pipeline/syntax/#tools)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions) · [java-with-maven](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-maven) · [dependency-caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`agent`** (🟡 1 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`junit`** (🟡 1 approximated): no built-in test report UI; upload results + a reporting action or job summary.
  - Jenkins: [step `junit`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`post`** (✅ 2 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`parameters`** (✅ 25 mapped): inputs are empty on push/schedule events; choose defaults explicitly.
  - Jenkins: [syntax #parameters](https://www.jenkins.io/doc/book/pipeline/syntax/#parameters)
  - GitHub Actions: [workflow-syntax #onworkflow_dispatchinputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
- **`withCredentials`** (✅ 1 mapped): file/SSH credentials must be materialised by a step; OIDC replaces long-lived cloud keys.
  - Jenkins: [step `withCredentials`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [use-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) · [secrets](https://docs.github.com/en/actions/concepts/security/secrets) · [secrets](https://docs.github.com/en/actions/reference/security/secrets)
- **`archiveArtifacts`** (✅ 1 mapped)
  - Jenkins: [step `archiveArtifacts`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data) · [download-workflow-artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
