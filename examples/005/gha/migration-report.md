# Migration report: opensearch-project/opensearch-migrations `vars/defaultIntegPipeline.groovy`

- **Classification:** assisted (difficulty 45/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 51.4% (14 mapped, 19 approximated, 17 manual, 1 dropped)
- **Weighted step coverage (analysis):** 70.9%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 16 | 20 |
| step mapping | 7.3 | 25 |
| plugin coupling | 10.5 | 15 |
| library opacity | 4 | 15 |
| runtime coupling | 2.0 | 10 |
| security identity | 5 | 10 |
| control flow | 0.0 | 5 |

- **Hard gates:** none
- **Unknown steps (3):** `checkoutStep`, `cleanupMavenCache`, `configureMavenCache` - plugin or shared-library steps the step catalog does not know, each a manual item below. If every one were mapped, the difficulty would be **30/100 - assisted**.
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Secrets required

| Secret | Purpose |
|---|---|
| `MIGRATIONS_TEST_ACCOUNT_ID` | Jenkins credential 'migrations-test-account-id' |

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `post always` |  |  | if: always() |  |
| ✅ mapped | `post cleanup` |  |  | if: always() |  |
| ✅ mapped | `options: skipDefaultCheckout` |  |  | no checkout step |  |
| ✅ mapped | `parameters: string GIT_REPO_URL` | 31 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string GIT_BRANCH` | 32 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string GIT_COMMIT` | 33 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string STAGE` | 34 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string VERSION` | 35 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `dir` | 138 | Pre-Deploy Cleanup | working-directory |  |
| ✅ mapped | `withCredentials string 'migrations-test-account-id'` | 140 | Pre-Deploy Cleanup | secrets -> step env |  |
| ✅ mapped | `dir` | 160 | Deploy | working-directory |  |
| ✅ mapped | `dir` | 189 | Pre-Integ Test Cleanup | working-directory |  |
| ✅ mapped | `dir` | 207 | Integ Tests | working-directory |  |
| ✅ mapped | `dir` | 237 | Declarative: Post Actions | working-directory |  |
| 🟡 approximated | `options: timeout` |  |  | timeout-minutes: 180 (per job) | Jenkins timeout covers the whole pipeline |
| ⚪ dropped | `options: buildDiscarder` |  |  | - | use artifact retention-days / repo settings |
| 🟡 approximated | `agent label '?:'` | 28 | Checkout, Test Caller Identity, Setup E2E CDK Context, Build, Pre-Deploy Cleanup | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `script {}` | 65 | Checkout | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `echo` | 68 | Checkout | run: echo |  |
| 🟡 approximated | `script {}` | 89 | Test Caller Identity | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `script {}` | 102 | Setup E2E CDK Context | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `timeout` | 118 | Build | timeout-minutes per step | Jenkins timeout covers the whole block |
| 🟡 approximated | `script {}` | 119 | Build | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `timeout` | 137 | Pre-Deploy Cleanup | timeout-minutes per step | Jenkins timeout covers the whole block |
| 🟡 approximated | `script {}` | 139 | Pre-Deploy Cleanup | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `withAWS` | 141 | Pre-Deploy Cleanup | body inlined | configure identity via OIDC / approved action |
| 🟡 approximated | `timeout` | 159 | Deploy | timeout-minutes per step | Jenkins timeout covers the whole block |
| 🟡 approximated | `script {}` | 161 | Deploy | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `timeout` | 188 | Pre-Integ Test Cleanup | timeout-minutes per step | Jenkins timeout covers the whole block |
| 🟡 approximated | `script {}` | 190 | Pre-Integ Test Cleanup | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `timeout` | 206 | Integ Tests | timeout-minutes per step | Jenkins timeout covers the whole block |
| 🟡 approximated | `script {}` | 208 | Integ Tests | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `timeout` | 236 | Declarative: Post Actions | timeout-minutes per step | Jenkins timeout covers the whole block |
| 🟡 approximated | `script {}` | 238 | Declarative: Post Actions | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🔴 manual | `options: lock` |  |  | - | no GHA equivalent |
| 🔴 manual | `triggers: {'step': 'GenericTrigger', 'text': ''}` | 47 |  | - | unsupported trigger |
| 🔴 manual | `triggers: {'step': 'cron', 'text': 'periodicCron(...)'}` | 59 |  | - | unsupported trigger |
| 🔴 manual | `decl checkoutBranch = ?` | 66 | Checkout | - | Groovy variable assignment |
| 🔴 manual | `assign env.CHECKOUT_BRANCH = checkoutBranch` | 67 | Checkout | - | Groovy variable assignment |
| 🔴 manual | `if (config.checkoutStep)` | 78 | Checkout | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (config.awsIdentityCheckStep)` | 91 | Test Caller Identity | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (config.cdkContextStep)` | 104 | Setup E2E CDK Context | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `configureMavenCache` | 120 | Build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (config.buildStep)` | 122 | Build | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Pre-Deploy Cleanup' when` | 134 | Pre-Deploy Cleanup | if: vars.J2GHA_WHEN_L134 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `preDeployStep` | 142 | Pre-Deploy Cleanup | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (config.deployStep)` | 163 | Deploy | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (config.preIntegTestStep)` | 191 | Pre-Integ Test Cleanup | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (config.integTestStep)` | 210 | Integ Tests | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (config.finishStep)` | 240 | Declarative: Post Actions | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `cleanupMavenCache` | 250 | Declarative: Post Actions | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- pipeline {} is defined inside shared-library method 'call()'

## Stage graph

```text
pipeline [declarative] agent: label ?:
├── Checkout
│   · script, <decl>, <assign>, echo, <if>, config.checkoutStep
├── Test Caller Identity
│   · script, <if>, config.awsIdentityCheckStep
├── Setup E2E CDK Context
│   · script, <if>, config.cdkContextStep
├── Build
│   · timeout, script, configureMavenCache, <if>, config.buildStep
├── Pre-Deploy Cleanup  [when]
│   · timeout, dir, script, withCredentials, withAWS, config.preDeployStep
├── Deploy
│   · timeout, dir, script, <if>, config.deployStep
├── Pre-Integ Test Cleanup
│   · timeout, dir, script, <if>, withCredentials, withAWS, config.preIntegTestStep
└── Integ Tests
    · timeout, dir, script, <if>, config.integTestStep
post: always, cleanup
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 10 manual, 🟡 9 approximated): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`lock`** (🔴 1 manual)
  - Jenkins: [step `lock`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency) · [workflow-syntax #jobsjob_idconcurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idconcurrency)
- **`triggers`** (🔴 2 manual): cron has no H; schedules run on the default branch only; pollSCM -> push; upstream -> workflow_run.
  - Jenkins: [syntax #triggers](https://www.jenkins.io/doc/book/pipeline/syntax/#triggers) · [syntax #cron-syntax](https://www.jenkins.io/doc/book/pipeline/syntax/#cron-syntax)
  - GitHub Actions: [events-that-trigger-workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) · [workflow-syntax #onschedule](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule) · [trigger-a-workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- **`when`** (🔴 1 manual): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`timeout`** (🟡 7 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`agent`** (🟡 1 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`buildDiscarder`** (⚪ 1 dropped): no per-count run retention; artifact retention-days and the repository log retention setting.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepswith](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepswith) · [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- **`post`** (✅ 2 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`skipDefaultCheckout`** (✅ 1 mapped): GHA never checks out implicitly; add actions/checkout where Jenkins did.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idsteps](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idsteps)
- **`parameters`** (✅ 5 mapped): inputs are empty on push/schedule events; choose defaults explicitly.
  - Jenkins: [syntax #parameters](https://www.jenkins.io/doc/book/pipeline/syntax/#parameters)
  - GitHub Actions: [workflow-syntax #onworkflow_dispatchinputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
- **`dir`** (✅ 5 mapped)
  - Jenkins: [step `dir`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsworking-directory](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsworking-directory)
- **`withCredentials`** (✅ 1 mapped): file/SSH credentials must be materialised by a step; OIDC replaces long-lived cloud keys.
  - Jenkins: [step `withCredentials`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [use-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) · [secrets](https://docs.github.com/en/actions/concepts/security/secrets) · [secrets](https://docs.github.com/en/actions/reference/security/secrets)
