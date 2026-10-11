# Migration report: IBM/cloudant-node-sdk `Jenkinsfile`

- **Classification:** significant-redesign (difficulty 56/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 43.1% (20 mapped, 27 approximated, 37 manual, 0 dropped)
- **Weighted step coverage (analysis):** 43.7%

## Secrets required

| Secret | Purpose |
|---|---|
| `ARTIFACTORY` | Jenkins credential 'artifactory' |
| `CONTAINER_TEST_SERVER_USR` | Jenkins credential 'container-test-server' |
| `CONTAINER_TEST_SERVER_PSW` | Jenkins credential 'container-test-server' |
| `ARTIFACTORY_USR` | Jenkins credential 'artifactory' |
| `ARTIFACTORY_PSW` | Jenkins credential 'artifactory' |
| `NPM_MAIL` | Jenkins credential 'npm-mail' |
| `NPM_CREDS_USR` | Jenkins credential 'npm-creds' |
| `NPM_CREDS_PSW` | Jenkins credential 'npm-creds' |

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `stage 'QA' post always` |  | QA | if: (always()) && (steps.s2.outcome == 'success') |  |
| ✅ mapped | `stage 'Publish[staging]' post always` |  | Publish[staging] | if: (always()) && (steps.s12.outcome == 'success') |  |
| ✅ mapped | `environment ARTIFACTORY_CREDS = credentials('artifactory')` | 17 |  | env from secrets.ARTIFACTORY | create the repository/environment secret |
| ✅ mapped | `withEnv` | 39 | QA | step env |  |
| ✅ mapped | `withCredentials usernamePassword 'container-test-server'` | 45 | QA | secrets -> step env |  |
| ✅ mapped | `sh` | 51 | QA | run |  |
| ✅ mapped | `sh` | 52 | QA | run |  |
| ✅ mapped | `stage 'Publish[staging]' when` | 94 | Publish[staging] | if: !(env.TAG_NAME != '') | evaluated once at stage entry against env |
| ✅ mapped | `sh` | 116 | Publish[staging] | run |  |
| ✅ mapped | `stage 'Run Gauge tests' when` | 123 | Run Gauge tests | if: !(env.TAG_NAME != '') | evaluated once at stage entry against env |
| ✅ mapped | `sh` | 189 | Update version and tag | run |  |
| ✅ mapped | `withCredentials usernamePassword 'artifactory'` | 380 | QA | secrets -> step env |  |
| ✅ mapped | `sh` | 383 | QA | run |  |
| ✅ mapped | `sh` | 384 | QA | run |  |
| ✅ mapped | `withCredentials usernamePassword 'artifactory'` | 391 | Publish[staging] | secrets -> step env |  |
| ✅ mapped | `withCredentials string 'npm-mail'` | 401 | Publish[repository] | secrets -> step env |  |
| ✅ mapped | `withCredentials usernamePassword 'npm-creds'` | 401 | Publish[repository] | secrets -> step env |  |
| ✅ mapped | `sh` | 410 | Publish[staging] | run |  |
| ✅ mapped | `sh` | 411 | Publish[staging] | run |  |
| ✅ mapped | `sh` | 415 | Publish[repository] | run |  |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `parameters: validatingString TARGET_VERSION` | 10 |  | on.workflow_dispatch.inputs | validatingString parameters have no workflow_dispatch equivalent |
| 🟡 approximated | `script {}` | 30 | Init | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `defaultInit() (local helper method)` | 31 | Init | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `applyCustomizations() (local helper method)` | 32 | Init | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `script {}` | 50 | QA | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `runTests() (local helper method)` | 54 | QA | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `junit` | 61 | QA | upload-artifact + step summary | no native test UI; failing tests cannot mark the run UNSTABLE |
| 🟡 approximated | `environment STAGE_ROOT` | 99 | Publish[staging] | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `withEnv` | 104 | Publish[staging] | step env + shell exports | LIB_NAME evaluated by the shell in run steps (Groovy values need review); TYPE evaluated by the shell in run steps (Groovy values need review); ARTIFACT_URL evaluated by the shell in run steps (Groovy values need review); MODULE_ID evaluated by the shell in run steps (Groovy values need review); BUILD_NAME evaluated by the shell in run steps |
| 🟡 approximated | `publishStaging() (local helper method)` | 109 | Publish[staging] | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `script {}` | 128 | Run Gauge tests | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (env.TAG_NAME || env.BRANCH_IS_PRIMARY)` | 138 | Run Gauge tests | if: env.TAG_NAME != '' || env.BRANCH_IS_PRIMARY != '' |  |
| 🟡 approximated | `try/catch/finally (line 142)` | 142 | Run Gauge tests | steps; catch -> if: a try step failed; finally -> if: always() once entered | exception types are not distinguished |
| 🟡 approximated | `stage 'Mend scan' when` | 163 | Mend scan | if: env.BRANCH_IS_PRIMARY != '' | evaluated once at stage entry against env |
| 🟡 approximated | `environment WS_PROJECTNAME` | 166 | Mend scan | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `stage 'Update version and tag' when` | 176 | Update version and tag | if: (env.BRANCH_NAME == 'main' && !((env.TARGET_VERSION) == ('NONE'))) | evaluated once at stage entry against env |
| 🟡 approximated | `publishPublic() (local helper method)` | 205 | Publish[repository] | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `publishDocs() (local helper method)` | 207 | Publish[repository] | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `withEnv` | 372 | QA | step env + shell exports | NPMRC_REGISTRY evaluated by the shell in run steps (Groovy values need review); NPM_CONFIG_REGISTRY evaluated by the shell in run steps (Groovy values need review) |
| 🟡 approximated | `withEnv` | 381 | QA | step env + shell exports | NPMRC_EMAIL evaluated by the shell in run steps |
| 🟡 approximated | `withNpmEnv() (local helper method)` | 382 | QA | inlined | body of the Jenkinsfile helper method inlined with registry substituted |
| 🟡 approximated | `withEnv` | 392 | Publish[staging] | step env + shell exports | NPMRC_EMAIL evaluated by the shell in run steps |
| 🟡 approximated | `withNpmEnv() (local helper method)` | 393 | Publish[staging] | inlined | body of the Jenkinsfile helper method inlined with registry substituted |
| 🟡 approximated | `publishNpm() (local helper method)` | 394 | Publish[staging] | inlined | body of the Jenkinsfile helper method inlined with registry substituted |
| 🟡 approximated | `withNpmEnv() (local helper method)` | 403 | Publish[repository] | inlined | body of the Jenkinsfile helper method inlined with registry substituted |
| 🟡 approximated | `publishNpm() (local helper method)` | 404 | Publish[repository] | inlined | body of the Jenkinsfile helper method inlined with registry, tag substituted |
| 🔴 manual | `agent kubernetes` | 4 | Detect Secrets, Init, QA, SonarQube analysis, Publish[staging], Run Gauge tests, Mend scan | runs-on: ubuntu-latest | pod templates need job containers/services or ARC runner scale sets |
| 🔴 manual | `environment ARTIFACTORY_URL_UP` | 18 |  | env | runtime Groovy expression `${Artifactory.server('taas-artifactory-upload').getUrl()}` - compute in a step and write to $GITHUB_ENV |
| 🔴 manual | `environment ARTIFACTORY_URL_DOWN` | 19 |  | env | runtime Groovy expression `${Artifactory.server('taas-artifactory').getUrl()}` - compute in a step and write to $GITHUB_ENV |
| 🔴 manual | `detectSecrets` | 24 | Detect Secrets | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign commitHash = ${env.GIT_COMMIT.take(7)}` | 33 | Init | - | Groovy variable assignment |
| 🔴 manual | `environment scannerHome = tool(...)` | 70 | SonarQube analysis | env | value computed by a library/plugin function - compute in a step and write to $GITHUB_ENV |
| 🔴 manual | `stage 'SonarQube analysis' when` | 74 | SonarQube analysis | if: ((env.CHANGE_ID != '' || env.BRANCH_IS_PRIMARY != '')) && (!(((env.CHANGE_ID != '' && ((startsWith(env.CHANGE_BRANCH, 'dependabot') && !contains(env.CHANGE_BRANCH, '/')))) && !((env.CHANGE_ID != '' && (vars.J2GHA_WHEN_L82 == 'true')))))) | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `scanCode` | 88 | SonarQube analysis | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `bumpVersion` | 102 | Publish[staging] | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `customizePublishingInfo` | 103 | Publish[staging] | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `publishArtifactoryBuildInfo` | 110 | Publish[staging] | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign buildResults = null` | 129 | Run Gauge tests | - | Groovy variable assignment |
| 🔴 manual | `assign gaugeBranchName = env.BRANCH_NAME` | 133 | Run Gauge tests | - | Groovy variable assignment |
| 🔴 manual | `assign fallbackBranchName = ?:` | 134 | Run Gauge tests | - | Groovy variable assignment |
| 🔴 manual | `assign gaugeBranchName = env.TARGET_GAUGE_RELEASE_BRANCH_` | 139 | Run Gauge tests | - | Groovy variable assignment |
| 🔴 manual | `assign fallbackBranchName = ?:` | 140 | Run Gauge tests | - | Groovy variable assignment |
| 🔴 manual | `assign buildResults = build(...)` | 143 | Run Gauge tests | - | Groovy variable assignment from a step |
| 🔴 manual | `build job: /${env.SDKS_GAUGE_PIPELINE_PROJECT}/${gaugeBranchName}` | 143 | Run Gauge tests | workflow_call / workflow_dispatch | downstream Jenkins job must be migrated; trigger with `gh workflow run` or a reusable workflow |
| 🔴 manual | `if (ae.getMessage().contains("No item named /${env.SDK)` | 148 | Run Gauge tests | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `mendScan` | 169 | Mend scan | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `gitsh` | 185 | Update version and tag | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `bumpVersion` | 187 | Update version and tag | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `stage 'Publish[repository]' when` | 197 | Publish[repository] | if: (env.TAG_NAME != '' && (vars.J2GHA_WHEN_L200 == 'true')) | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `gitsh` | 206 | Publish[repository] | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign bumpVersion = ` | 231 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign doVersionBump = ` | 238 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign getNewVersion = ` | 242 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign getTargetVersion = ` | 247 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign getDevVersion = ` | 258 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign customizeVersion = ` | 276 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign publishArtifactoryBuildInfoScript = ` | 280 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign publishArtifactoryBuildInfo = ` | 285 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign scanCode = ` | 303 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign libName = node` | 318 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign bumpVersion = ` | 319 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign customizeVersion = ` | 336 | Init | - | Groovy variable assignment |
| 🔴 manual | `assign customizePublishingInfo = ` | 342 | Init | - | Groovy variable assignment |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Stage graph

```text
pipeline [declarative] agent: kubernetes
├── Detect Secrets
│   · detectSecrets
├── Init
│   · script, defaultInit, applyCustomizations, <assign>
├── QA  [post: always]
│   · withEnv, withCredentials, script, sh×2, runTests
├── SonarQube analysis  [when]
│   · scanCode
├── Publish[staging]  [when; post: always]
│   · bumpVersion, customizePublishingInfo, withEnv, publishStaging, publishArtifactoryBuildInfo
├── Run Gauge tests  [when]
│   · script, <assign>×6, <if>, <try>, build
├── Mend scan  [when]
│   · mendScan
├── Update version and tag  [when]
│   · gitsh, bumpVersion, sh
└── Publish[repository]  [when]
    · publishPublic, gitsh, publishDocs
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`environment`** (🔴 3 manual, 🟡 2 approximated, ✅ 1 mapped): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
- **`when`** (🔴 2 manual, 🟡 2 approximated, ✅ 2 mapped): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`scripted`** (🔴 21 manual, 🟡 16 approximated): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`agent`** (🔴 1 manual): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`build`** (🔴 1 manual): downstream job -> reusable workflow call (wait) or workflow_dispatch via API (fire-and-forget).
  - Jenkins: [step `build`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [reuse-workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch) · [events-that-trigger-workflows #workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- **`withEnv`** (🟡 4 approximated, ✅ 1 mapped)
  - Jenkins: [step `withEnv`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsenv](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsenv) · [workflow-commands #setting-an-environment-variable](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#setting-an-environment-variable)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`parameters`** (🟡 1 approximated): inputs are empty on push/schedule events; choose defaults explicitly.
  - Jenkins: [syntax #parameters](https://www.jenkins.io/doc/book/pipeline/syntax/#parameters)
  - GitHub Actions: [workflow-syntax #onworkflow_dispatchinputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
- **`junit`** (🟡 1 approximated): no built-in test report UI; upload results + a reporting action or job summary.
  - Jenkins: [step `junit`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`post`** (✅ 2 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`withCredentials`** (✅ 5 mapped): file/SSH credentials must be materialised by a step; OIDC replaces long-lived cloud keys.
  - Jenkins: [step `withCredentials`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [use-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) · [secrets](https://docs.github.com/en/actions/concepts/security/secrets) · [secrets](https://docs.github.com/en/actions/reference/security/secrets)
- **`sh`** (✅ 9 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
