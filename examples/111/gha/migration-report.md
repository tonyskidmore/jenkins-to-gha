# Migration report: oneanupam/jenkins-shared-libs `vars/pipeline.groovy`

- **Classification:** straightforward (difficulty 8/100)
- **Convertibility:** automatic
- **Automated mapping (effort estimate, not correctness):** 87.5% (12 mapped, 2 approximated, 1 manual, 1 dropped)
- **Weighted step coverage (analysis):** 94.3%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 6.0 | 20 |
| step mapping | 1.4 | 25 |
| plugin coupling | 0.8 | 15 |
| library opacity | 0.0 | 15 |
| runtime coupling | 0.0 | 10 |
| security identity | 0 | 10 |
| control flow | 0.0 | 5 |

- **Hard gates:** none
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `options: disableConcurrentBuilds` |  |  | concurrency | GHA keeps only the latest pending run per group |
| ✅ mapped | `post always` |  |  | if: always() |  |
| ✅ mapped | `post failure` |  |  | if: failure() |  |
| ✅ mapped | `post success` |  |  | if: success() |  |
| ✅ mapped | `options: skipDefaultCheckout` |  |  | no checkout step |  |
| ✅ mapped | `checkout scm` | 23 | Checkout | actions/checkout@v4 |  |
| ✅ mapped | `sh` | 29 | Install | run |  |
| ✅ mapped | `sh` | 35 | Test | run |  |
| ✅ mapped | `sh` | 41 | Build | run |  |
| ✅ mapped | `archiveArtifacts` | 49 | Declarative: Post Actions | actions/upload-artifact@v4 |  |
| ✅ mapped | `echo` | 52 | Declarative: Post Actions | run: echo |  |
| ✅ mapped | `echo` | 55 | Declarative: Post Actions | run: echo |  |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| ⚪ dropped | `options: timestamps` |  |  | - | native in GitHub Actions |
| 🟡 approximated | `junit` | 48 | Declarative: Post Actions | upload-artifact + step summary | no native test UI; failing tests cannot mark the run UNSTABLE |
| 🔴 manual | `environment APPLICATION_NAME` | 17 |  | env | runtime Groovy expression `application` - compute in a step and write to $GITHUB_ENV |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- pipeline {} is defined inside shared-library method 'call()'

## Stage graph

```text
pipeline [declarative] agent: any
├── Checkout
│   · checkout
├── Install
│   · sh
├── Test
│   · sh
└── Build
    · sh
post: always, success, failure
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`environment`** (🔴 1 manual): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`junit`** (🟡 1 approximated): no built-in test report UI; upload results + a reporting action or job summary.
  - Jenkins: [step `junit`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`timestamps`** (⚪ 1 dropped): GHA logs are always timestamped - drop it.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [use-workflow-run-logs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs)
- **`disableConcurrentBuilds`** (✅ 1 mapped): abortPrevious true -> cancel-in-progress true.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency) · [control-workflow-concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) · [workflow-syntax #concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
- **`post`** (✅ 3 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`skipDefaultCheckout`** (✅ 1 mapped): GHA never checks out implicitly; add actions/checkout where Jenkins did.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idsteps](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idsteps)
- **`checkout`** (✅ 1 mapped, ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
- **`sh`** (✅ 3 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`archiveArtifacts`** (✅ 1 mapped)
  - Jenkins: [step `archiveArtifacts`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data) · [download-workflow-artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
