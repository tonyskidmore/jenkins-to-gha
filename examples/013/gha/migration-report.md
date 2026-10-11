# Migration report: EclipseNebula/nebula `Jenkinsfile`

- **Classification:** assisted (difficulty 23/100)
- **Convertibility:** automatic
- **Automated mapping (effort estimate, not correctness):** 62.1% (13 mapped, 16 approximated, 8 manual, 2 dropped)
- **Weighted step coverage (analysis):** 76.2%

## Secrets required

| Secret | Purpose |
|---|---|
| `PROJECTS_STORAGE_ECLIPSE_ORG_BOT_SSH` | Jenkins credential 'projects-storage.eclipse.org-bot-ssh' |

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `options: disableConcurrentBuilds` |  |  | concurrency | GHA keeps only the latest pending run per group |
| ✅ mapped | `post always` |  |  | if: always() |  |
| ✅ mapped | `post failure` |  |  | if: failure() |  |
| ✅ mapped | `post cleanup` |  |  | if: always() |  |
| ✅ mapped | `environment MAIN_BRANCH` | 19 |  | env |  |
| ✅ mapped | `parameters: choice BUILD_TYPE` | 23 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: booleanParam ECLIPSE_SIGN` | 32 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: booleanParam PROMOTE` | 41 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `echo` | 73 | Display Parameters | run: echo |  |
| ✅ mapped | `archiveArtifacts` | 91 | Build Nebula | actions/upload-artifact@v4 |  |
| ✅ mapped | `archiveArtifacts` | 105 | Declarative: Post Actions | actions/upload-artifact@v4 |  |
| ✅ mapped | `deleteDir` | 120 | Declarative: Post Actions | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `sh` | 129 | Build Nebula | run |  |
| 🟡 approximated | `tools maven 'apache-maven-latest'` |  |  | runner-provided Maven | GitHub-hosted Ubuntu runners include Maven; pin a version with a setup action if required |
| 🟡 approximated | `tools jdk 'temurin-jdk21-latest'` |  |  | actions/setup-java@v4 | Jenkins tool name mapped by version heuristics |
| ⚪ dropped | `post fixed` |  |  | - | no GHA equivalent |
| 🟡 approximated | `options: timeout` |  |  | timeout-minutes: 60 (per job) | Jenkins timeout covers the whole pipeline |
| ⚪ dropped | `options: buildDiscarder` |  |  | - | use artifact retention-days / repo settings |
| 🟡 approximated | `agent label 'ubuntu-latest'` | 2 | Display Parameters, Build Nebula | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `environment BUILD_TIMESTAMP` | 18 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `script {}` | 51 | Display Parameters | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (env.BRANCH_NAME == env.MAIN_BRANCH)` | 53 | Display Parameters | if: env.BRANCH_NAME == env.MAIN_BRANCH |  |
| 🟡 approximated | `script {}` | 81 | Build Nebula | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (env.PROMOTE == 'true')` | 82 | Build Nebula | if: env.PROMOTE == 'true' |  |
| 🟡 approximated | `sshagent` | 86 | Build Nebula | webfactory/ssh-agent (recommended) | keys exposed as env; load into an agent with an approved action |
| 🟡 approximated | `mvn() (local helper method)` | 87 | Build Nebula | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `mvn() (local helper method)` | 90 | Build Nebula | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `junit` | 100 | Declarative: Post Actions | upload-artifact + step summary | no native test UI; failing tests cannot mark the run UNSTABLE |
| 🟡 approximated | `recordIssues` | 101 | Declarative: Post Actions | echo placeholder | use an approved reporting action (SARIF/coverage) |
| 🟡 approximated | `mail` | 106 | Declarative: Post Actions | notification placeholder | use an approved notification action (e.g. slackapi/slack-github-action) |
| 🟡 approximated | `wrap` | 126 | Build Nebula | body inlined | wrapper semantics not reproduced |
| 🔴 manual | `assign env.BUILD_TYPE = params.BUILD_TYPE` | 52 | Display Parameters | - | Groovy variable assignment |
| 🔴 manual | `assign env.ECLIPSE_SIGN = params.ECLIPSE_SIGN` | 56 | Display Parameters | - | Groovy variable assignment |
| 🔴 manual | `assign env.ECLIPSE_SIGN = False` | 59 | Display Parameters | - | Groovy variable assignment |
| 🔴 manual | `assign env.PROMOTE = params.PROMOTE && (env.ECLIPSE_SIGN ` | 64 | Display Parameters | - | Groovy variable assignment |
| 🔴 manual | `decl description = """
BUILD_TIMESTAMP=${env.BUILD_TIME` | 66 | Display Parameters | - | Groovy variable assignment from a step |
| 🔴 manual | `trim` | 66 | Display Parameters | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `assign currentBuild.description = description.replace(...` | 74 | Display Parameters | - | Groovy variable assignment from a step |
| 🔴 manual | `replace` | 74 | Display Parameters | - | Groovy method / helper call - port logic to a script |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Stage graph

```text
pipeline [declarative] agent: label ubuntu-latest
├── Display Parameters
│   · script, <assign>×4, <if>, <decl>, """
BUILD_TIMESTAMP=${env.BUILD_TIMESTAMP}
BUILD_TYPE=${env.BUILD_TYPE}
ECLIPSE_SIGN=${env.ECLIPSE_SIGN}
PROMOTE=${env.PROMOTE}
BRANCH_NAME=${env.BRANCH_NAME}
""".trim, echo, description.replace
└── Build Nebula
    · script, <if>, sshagent, mvn
post: always, failure, fixed, cleanup
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 6 manual, 🟡 6 approximated): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`environment`** (🟡 1 approximated, ✅ 1 mapped): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
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
- **`post`** (⚪ 1 dropped, ✅ 3 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`buildDiscarder`** (⚪ 1 dropped): no per-count run retention; artifact retention-days and the repository log retention setting.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepswith](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepswith) · [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- **`disableConcurrentBuilds`** (✅ 1 mapped): abortPrevious true -> cancel-in-progress true.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency) · [control-workflow-concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) · [workflow-syntax #concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
- **`parameters`** (✅ 3 mapped): inputs are empty on push/schedule events; choose defaults explicitly.
  - Jenkins: [syntax #parameters](https://www.jenkins.io/doc/book/pipeline/syntax/#parameters)
  - GitHub Actions: [workflow-syntax #onworkflow_dispatchinputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
- **`archiveArtifacts`** (✅ 2 mapped)
  - Jenkins: [step `archiveArtifacts`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data) · [download-workflow-artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
- **`sh`** (✅ 1 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
