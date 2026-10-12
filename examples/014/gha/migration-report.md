# Migration report: The-OpenROAD-Project/OpenLane `Jenkinsfile`

- **Classification:** straightforward (difficulty 20/100)
- **Convertibility:** automatic
- **Automated mapping (effort estimate, not correctness):** 82.5% (18 mapped, 14 approximated, 0 manual, 0 dropped)
- **Weighted step coverage (analysis):** 78.5%

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `stage 'Test' post failure` |  | Test | if: (always()) && (steps.s11.outcome == 'success') && ((steps.s12.outcome == 'failure' || steps.s13.outcome == 'failure' || steps.s14.outcome == 'failure' || steps.s15.outcome == 'failure' || steps.s16.outcome == 'failure' || steps.s17.outcome == 'failure' || steps.s18.outcome == 'failure' || steps.s19.outcome == 'failure')) |  |
| ✅ mapped | `post failure` |  |  | final job if: always() && (contains(needs.*.result, 'failure') || failure()) |  |
| ✅ mapped | `environment ROUTING_CORES` | 10 |  | env |  |
| ✅ mapped | `checkout scm` | 17 | Update OpenROAD to HEAD of master branch | actions/checkout@v4 |  |
| ✅ mapped | `sh` | 30 | Build Docker OpenLane image with openroad_app master | run |  |
| ✅ mapped | `sh` | 31 | Build Docker OpenLane image with openroad_app master | run |  |
| ✅ mapped | `assign NEW_SHA = sh (returnStdout: true, script: "python3` | 32 | Build Docker OpenLane image with openroad_app master | run step; its output goes to $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `sh` | 33 | Build Docker OpenLane image with openroad_app master | run |  |
| ✅ mapped | `sh` | 34 | Build Docker OpenLane image with openroad_app master | run |  |
| ✅ mapped | `sleep` | 38 | Build Docker OpenLane image with openroad_app master | run: sleep |  |
| ✅ mapped | `sh` | 39 | Build Docker OpenLane image with openroad_app master | run |  |
| ✅ mapped | `stage 'Run Tests' matrix (DESIGN[22])` | 47 | Run Tests | strategy.matrix |  |
| ✅ mapped | `sh` | 81 | ${DESIGN} - Install PDK | run |  |
| ✅ mapped | `sh` | 82 | ${DESIGN} - Install PDK | run |  |
| ✅ mapped | `sh` | 83 | ${DESIGN} - Install PDK | run |  |
| ✅ mapped | `sh` | 87 | ${DESIGN} - Import Docker image | run |  |
| ✅ mapped | `assign OLD_SHA = sh (returnStdout: true, script: "python3` | 90 | ${DESIGN} - Update OpenROAD commit | run step; its output goes to $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `archiveArtifacts` | 100 | Test | actions/upload-artifact@v4 |  |
| 🟡 approximated | `options: timeout` |  |  | timeout-minutes: 480 (per job) | Jenkins timeout covers the whole pipeline |
| 🟡 approximated | `script {}` | 27 | Build Docker OpenLane image with openroad_app master | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `retry` | 28 | Build Docker OpenLane image with openroad_app master | shell retry loop | only run steps are retried |
| 🟡 approximated | `try/catch/finally (line 29)` | 29 | Build Docker OpenLane image with openroad_app master | steps; catch -> if: a try step failed; finally -> if: always() once entered | exception types are not distinguished |
| 🟡 approximated | `script {}` | 32 | Build Docker OpenLane image with openroad_app master | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `sh` | 32 | Build Docker OpenLane image with openroad_app master | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `stash 'data'` | 35 | Build Docker OpenLane image with openroad_app master | actions/upload-artifact@v4 | artifact hand-off between jobs; file permissions are not preserved; no matching files fails the step, as the stash does in Jenkins (if-no-files-found: error) |
| 🟡 approximated | `script {}` | 79 | Test | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `unstash 'data'` | 86 | ${DESIGN} - Import Docker image | actions/download-artifact@v4 |  |
| 🟡 approximated | `script {}` | 90 | ${DESIGN} - Update OpenROAD commit | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `sh` | 90 | ${DESIGN} - Update OpenROAD commit | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 91 | ${DESIGN} - Update OpenROAD commit | run |  |
| 🟡 approximated | `sh` | 94 | ${DESIGN} - Run test | run |  |
| 🟡 approximated | `emailext` | 112 | Declarative: Post Actions | notification placeholder | use an approved notification action (e.g. slackapi/slack-github-action) |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Workspace hand-off

Jenkins runs every stage without an agent of its own in one workspace; the converted jobs hand it on as `j2gha-ws-<job>` artifacts (an archive per job, kept one day) and restore it instead of checking out (`J2GHA_WORKSPACE_HANDOFF=0` converts without).

- **Handed on by:** `update-openroad-to-head-of-master-branch`. **Merged after running concurrently:** none (each later branch's own changes are replayed onto the first one's workspace).
- **Runtime requirements:** bash, GNU tar, findutils, coreutils and sed on the runner and in job containers: GitHub's Linux runners and Debian/Ubuntu-based images. busybox/Alpine images fail at the hand-off steps.
- **Same as Jenkins:** the files, directories, modes, symbolic and hard links every stage starts with, provided concurrent branches change different paths.
- **Approximated:** concurrent branches do not see each other's files while they run; a path two of them change takes the later branch's version (in Jenkins: whichever wrote last); changes of timestamps alone and matrix cells' changes are not handed on.
- **Fails instead:** an entry the job's user cannot read, a workspace that did not arrive from a job that ran - a nearest one or one the restore falls back on because a nearer job was skipped. Where that job's result is not visible to the restoring job (it is not one it needs directly), a missing workspace is taken as skipped, with a warning.

## Stage graph

```text
pipeline [declarative] agent: any
├── Update OpenROAD to HEAD of master branch
│   · checkout
├── Build Docker OpenLane image with openroad_app master
│   · script×2, retry, <try>, sh×5, <assign>, stash
└── Run Tests  [matrix DESIGN[22]]
    └── Test  [agent any; post: failure]
        · script×2, stage×4, sh×7, unstash, <assign>
post: failure
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. Jobs on the pipeline agent hand its workspace on (see *Workspace hand-off*); jobs with an agent of their own do not share it (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`sh`** (🟡 4 approximated, ✅ 9 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`scripted`** (🟡 5 approximated, ✅ 2 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`retry`** (🟡 1 approximated): no native step retry; use a shell loop or a retry action.
  - Jenkins: [step `retry`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepscontinue-on-error](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepscontinue-on-error)
- **`stash`** (🟡 1 approximated): stash/unstash between stages on different agents -> upload-artifact/download-artifact between jobs (file permissions are lost).
  - Jenkins: [step `stash`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`unstash`** (🟡 1 approximated)
  - Jenkins: [step `unstash`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`post`** (✅ 2 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`environment`** (✅ 1 mapped): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
- **`checkout`** (✅ 1 mapped, ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
- **`matrix`** (✅ 1 mapped): excludes with notValues must be expanded explicitly; matrix job limit per workflow run.
  - Jenkins: [syntax #declarative-matrix](https://www.jenkins.io/doc/book/pipeline/syntax/#declarative-matrix)
  - GitHub Actions: [run-job-variations](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations) · [workflow-syntax #jobsjob_idstrategymatrix](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstrategymatrix)
- **`archiveArtifacts`** (✅ 1 mapped)
  - Jenkins: [step `archiveArtifacts`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data) · [download-workflow-artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
