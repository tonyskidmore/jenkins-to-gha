# Migration report: TheHPXProject/hpx `.jenkins/lsu/Jenkinsfile`

- **Classification:** straightforward (difficulty 10/100)
- **Convertibility:** automatic
- **Automated mapping (effort estimate, not correctness):** 78.9% (11 mapped, 4 approximated, 2 manual, 1 dropped)
- **Weighted step coverage (analysis):** 89.3%

## Secrets required

| Secret | Purpose |
|---|---|
| `STELLARBOT_GITHUB_TOKEN` | Jenkins credential 'STELLARBOT_GITHUB_TOKEN' |

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `post always` |  |  | final job if: always() |  |
| ✅ mapped | `post (workspace-dependent steps)` |  |  | final job | archiveArtifacts run in the restored pipeline workspace (j2gha-ws-* artifacts) |
| ✅ mapped | `environment GITHUB_TOKEN = credentials('STELLARBOT_GITHUB_TOKEN')` | 24 |  | env from secrets.STELLARBOT_GITHUB_TOKEN | create the repository/environment secret |
| ✅ mapped | `dir` | 48 | checkout | working-directory |  |
| ✅ mapped | `checkout scm` | 49 | checkout | actions/checkout@v4 |  |
| ✅ mapped | `echo` | 50 | checkout | run: echo |  |
| ✅ mapped | `stage 'build' matrix (configuration_name[13] x build_type[2])` | 55 | build | strategy.matrix |  |
| ✅ mapped | `dir` | 69 | build | working-directory |  |
| ✅ mapped | `sh` | 70 | build | run (shell: bash -l {0}) |  |
| ✅ mapped | `archiveArtifacts` | 88 | Declarative: Post Actions | actions/upload-artifact@v4 | fingerprinting has no equivalent |
| ✅ mapped | `archiveArtifacts` | 89 | Declarative: Post Actions | actions/upload-artifact@v4 | fingerprinting has no equivalent |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| ⚪ dropped | `options: buildDiscarder` |  |  | - | use artifact retention-days / repo settings |
| 🟡 approximated | `script {}` | 39 | checkout | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (env.BRANCH_NAME)` | 40 | checkout | if: env.BRANCH_NAME != '' |  |
| 🟡 approximated | `milestone` | 45 | checkout | concurrency | use workflow/job concurrency groups |
| 🔴 manual | `decl buildNumber = as` | 41 | checkout | - | Groovy variable assignment |
| 🔴 manual | `if (buildNumber > 1)` | 42 | checkout | placeholder | condition depends on Groovy runtime state |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Workspace hand-off

Jenkins runs every stage without an agent of its own in one workspace; the converted jobs hand it on as `j2gha-ws-<job>` artifacts (an archive per job, kept one day) and restore it instead of checking out (`J2GHA_WORKSPACE_HANDOFF=0` converts without).

- **Handed on by:** `checkout`, `build`. **Merged after running concurrently:** none (each later branch's own changes are replayed onto the first one's workspace).
- **Matrix jobs:** `build` hand on each cell's own changes (`j2gha-ws-<job>.<cell>`), replayed in cell-name order onto the workspace the matrix started from.
- **Runtime requirements:** bash, GNU tar, findutils, coreutils and sed on the runner and in job containers: GitHub's Linux runners and Debian/Ubuntu-based images. busybox/Alpine images fail at the hand-off steps.
- **Same as Jenkins:** the files, directories, modes, symbolic and hard links every stage starts with, provided concurrent branches change different paths.
- **Approximated:** concurrent branches do not see each other's files while they run; a path two of them change takes the later branch's version (matrix cells: the later cell's, by name; in Jenkins: whichever wrote last); changes of timestamps alone are not handed on.
- **Fails instead:** an entry the job's user cannot read, a workspace that did not arrive from a job that ran - a nearest one or one the restore falls back on because a nearer job was skipped. Where that job's result is not visible to the restoring job (it is not one it needs directly), a missing workspace is taken as skipped, with a warning.

## Stage graph

```text
pipeline [declarative] agent: any
├── checkout
│   · script, <if>×2, <decl>, milestone×2, dir, checkout, echo
└── build  [matrix configuration_name[13] × build_type[2]]
    └── build
        · dir, sh
post: always
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. Jobs on the pipeline agent hand its workspace on (see *Workspace hand-off*); jobs with an agent of their own do not share it (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 2 manual, 🟡 2 approximated): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`milestone`** (🟡 1 approximated)
  - Jenkins: [step `milestone`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency)
- **`buildDiscarder`** (⚪ 1 dropped): no per-count run retention; artifact retention-days and the repository log retention setting.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepswith](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepswith) · [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- **`post`** (✅ 2 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`environment`** (✅ 1 mapped): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
- **`dir`** (✅ 2 mapped)
  - Jenkins: [step `dir`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsworking-directory](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsworking-directory)
- **`checkout`** (✅ 1 mapped, ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
- **`matrix`** (✅ 1 mapped): excludes with notValues must be expanded explicitly; matrix job limit per workflow run.
  - Jenkins: [syntax #declarative-matrix](https://www.jenkins.io/doc/book/pipeline/syntax/#declarative-matrix)
  - GitHub Actions: [run-job-variations](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations) · [workflow-syntax #jobsjob_idstrategymatrix](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstrategymatrix)
- **`sh`** (✅ 1 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`archiveArtifacts`** (✅ 2 mapped)
  - Jenkins: [step `archiveArtifacts`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data) · [download-workflow-artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
