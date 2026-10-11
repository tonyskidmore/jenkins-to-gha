# Migration report: owen2016/devops-practices `jenkins/pipeline/jenkinsfile-1`

- **Classification:** straightforward (difficulty 5/100)
- **Convertibility:** automatic
- **Automated mapping (effort estimate, not correctness):** 87.2% (17 mapped, 8 approximated, 0 manual, 0 dropped)
- **Weighted step coverage (analysis):** 100.0%

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `environment M2_HOME` | 12 |  | env |  |
| ✅ mapped | `parameters: string PERSON` | 18 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `stage 'Init' when` | 25 | Init | if: env.BRANCH == 'develop' | evaluated once at stage entry against env |
| ✅ mapped | `stage 'Parallel Stage' when` | 44 | Parallel Stage | if: env.BRANCH == 'develop' | evaluated once at stage entry against env |
| ✅ mapped | `echo` | 51 | Branch A | run: echo |  |
| ✅ mapped | `echo` | 56 | Branch B | run: echo |  |
| ✅ mapped | `environment M2_HOME` | 65 | Build | env |  |
| ✅ mapped | `echo` | 73 | Build | run: echo |  |
| ✅ mapped | `echo` | 75 | Build | run: echo |  |
| ✅ mapped | `echo` | 77 | Build | run: echo |  |
| ✅ mapped | `sh` | 79 | Build | run |  |
| ✅ mapped | `sh` | 80 | Build | run |  |
| ✅ mapped | `echo` | 81 | Build | run: echo |  |
| ✅ mapped | `echo` | 86 | Deploy | run: echo |  |
| ✅ mapped | `sh` | 87 | Deploy | run |  |
| ✅ mapped | `sh` | 88 | Deploy | run |  |
| ✅ mapped | `sh` | 90 | Deploy | run |  |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `agent label 'java'` | 3 | Init | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `environment BRANCH` | 11 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `environment PATH` | 14 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `stage 'Init' input` | 27 | Init | job environment 'Init' | configure required reviewers on the environment; input parameters are not supported |
| 🟡 approximated | `stage 'Parallel Stage' failFast` | 41 | Parallel Stage | - | GHA cannot cancel sibling jobs outside a matrix; consider strategy.fail-fast |
| 🟡 approximated | `stage 'Parallel Stage' parallel (2 branches)` | 41 | Parallel Stage | parallel jobs with needs | branches run as separate jobs: the pipeline workspace is handed on to them and from them to later stages (j2gha-ws-* artifacts), but branches running at the same time do not see each other's files, and a file two branches write takes the later branch's version |
| 🟡 approximated | `stage 'Build' options: timeout` | 62 | Build | timeout-minutes: 60 per step | Jenkins times out the whole stage |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Workspace hand-off

Jenkins runs every stage without an agent of its own in one workspace; the converted jobs hand it on as `j2gha-ws-<job>` artifacts (an archive per job, kept one day) and restore it instead of checking out (`J2GHA_WORKSPACE_HANDOFF=0` converts without).

- **Handed on by:** `init`, `parallel-stage-branch-a`, `parallel-stage-branch-b`. **Merged after running concurrently:** `parallel-stage-branch-a`, `parallel-stage-branch-b` (each later branch's own changes are replayed onto the first one's workspace).
- **Runtime requirements:** bash, GNU tar, findutils, coreutils and sed on the runner and in job containers: GitHub's Linux runners and Debian/Ubuntu-based images. busybox/Alpine images fail at the hand-off steps.
- **Same as Jenkins:** the files, directories, modes, symbolic and hard links every stage starts with, provided concurrent branches change different paths.
- **Approximated:** concurrent branches do not see each other's files while they run; a path two of them change takes the later branch's version (in Jenkins: whichever wrote last); changes of timestamps alone and matrix cells' changes are not handed on.
- **Fails instead:** an entry the job's user cannot read, a workspace that did not arrive from a job that ran - a nearest one or one the restore falls back on because a nearer job was skipped. Where that job's result is not visible to the restoring job (it is not one it needs directly), a missing workspace is taken as skipped, with a warning.

## Stage graph

```text
pipeline [declarative] agent: label java
├── Init  [when; input]
├── Parallel Stage  [when; parallel]
│   ├── Branch A
│   │   · echo
│   └── Branch B
│       · echo
├── Build
│   · echo×4, sh×2
└── Deploy
    · echo, sh×3
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. Jobs on the pipeline agent hand its workspace on (see *Workspace hand-off*); jobs with an agent of their own do not share it (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`environment`** (🟡 2 approximated, ✅ 2 mapped): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
- **`timeout`** (🟡 2 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`agent`** (🟡 1 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`input`** (🟡 1 approximated): input/submitter -> environment with required reviewers (no free-form input parameters at approval time).
  - Jenkins: [syntax #input](https://www.jenkins.io/doc/book/pipeline/syntax/#input)
  - GitHub Actions: [deployment-environments](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments) · [review-deployments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments) · [deployments-and-environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- **`parallel`** (🟡 2 approximated): parallel stages -> independent jobs; failFast -> strategy.fail-fast only applies within a matrix.
  - Jenkins: [syntax #parallel](https://www.jenkins.io/doc/book/pipeline/syntax/#parallel)
  - GitHub Actions: [use-jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs) · [workflow-syntax #jobsjob_idneeds](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
- **`parameters`** (✅ 1 mapped): inputs are empty on push/schedule events; choose defaults explicitly.
  - Jenkins: [syntax #parameters](https://www.jenkins.io/doc/book/pipeline/syntax/#parameters)
  - GitHub Actions: [workflow-syntax #onworkflow_dispatchinputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
- **`when`** (✅ 2 mapped): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`sh`** (✅ 5 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
