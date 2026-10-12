# Migration report: fabiojose/platform-as-code-example `Jenkinsfile`

- **Classification:** assisted (difficulty 42/100)
- **Convertibility:** automatic
- **Automated mapping (effort estimate, not correctness):** 70.2% (18 mapped, 26 approximated, 4 manual, 1 dropped)
- **Weighted step coverage (analysis):** 52.6%

## Secrets required

| Secret | Purpose |
|---|---|
| `NEXUS_CREDENTIAL_USR` | Jenkins credential 'nexus-credential' |
| `NEXUS_CREDENTIAL_PSW` | Jenkins credential 'nexus-credential' |
| `RUNDECK_CREDENTIAL_USR` | Jenkins credential 'rundeck-credential' |
| `RUNDECK_CREDENTIAL_PSW` | Jenkins credential 'rundeck-credential' |

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `post aborted` |  |  | final job if: always() && contains(needs.*.result, 'cancelled') |  |
| ✅ mapped | `post failure` |  |  | final job if: always() && (contains(needs.*.result, 'failure') || failure()) |  |
| ✅ mapped | `post success` |  |  | final job if: !failure() && !cancelled() && !contains(needs.*.result, 'failure') && !contains(needs.*.result, 'cancelled') |  |
| ✅ mapped | `assign oversion = sh(script: "jq -r '.variable.iac_versio` | 21 | Setup | run step; its output goes to $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign version = ${oversion.take(...)}-${env.BUILD_NUMBER` | 24 | Setup | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign oversion = oversion.take(...)` | 25 | Setup | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign iacname = env.JOB_NAME` | 26 | Setup | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign prjname = oss-opensource` | 29 | Setup | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign packname = ${iacname}-v${version}.tar.gz` | 32 | Setup | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign publish_url = ${env.NEXUS_URL }/repository/raw-ter` | 35 | Setup | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `sh` | 43 | Build | run |  |
| ✅ mapped | `sh` | 47 | Build | run |  |
| ✅ mapped | `withCredentials usernamePassword 'nexus-credential'` | 62 | Publish | secrets -> step env |  |
| ✅ mapped | `withCredentials usernamePassword 'rundeck-credential'` | 71 | DEV Deploy | secrets -> step env |  |
| ✅ mapped | `withCredentials usernamePassword 'rundeck-credential'` | 91 | PRE Deploy | secrets -> step env |  |
| ✅ mapped | `sh` | 112 | Acceptance Test | run |  |
| ✅ mapped | `sh` | 113 | Acceptance Test | run |  |
| ✅ mapped | `withCredentials usernamePassword 'rundeck-credential'` | 137 | PRO Deploy | secrets -> step env |  |
| ⚪ dropped | `post unstable` |  |  | - | no GHA equivalent |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `script {}` | 8 | Setup | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (env.GIT_BRANCH == 'origin/develop' || env.GIT_BRAN) assigning target` | 10 | Setup | run: bash if/elif -> $GITHUB_ENV + job outputs | Java regexes run as POSIX ERE; later `when`/`if` read env.target |
| 🟡 approximated | `sh` | 21 | Setup | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 44 | Build | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 45 | Build | run |  |
| 🟡 approximated | `sh` | 46 | Build | run |  |
| 🟡 approximated | `sh` | 48 | Build | run |  |
| 🟡 approximated | `sh` | 49 | Build | run |  |
| 🟡 approximated | `sh` | 50 | Build | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 53 | Build | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 56 | Build | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 64 | Publish | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `configFileProvider` | 77 | DEV Deploy | body inlined | wrapper semantics not reproduced |
| 🟡 approximated | `sh` | 79 | DEV Deploy | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `stage 'PRE Deploy' when` | 88 | PRE Deploy | if: env.target == 'pre' || env.target == 'pro' | evaluated once at stage entry against env |
| 🟡 approximated | `configFileProvider` | 92 | PRE Deploy | body inlined | wrapper semantics not reproduced |
| 🟡 approximated | `sh` | 93 | PRE Deploy | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `stage 'Acceptance Test' when` | 102 | Acceptance Test | if: env.target == 'pro' | evaluated once at stage entry against env |
| 🟡 approximated | `agent label 'openshift_cli'` | 106 | Acceptance Test | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `stage 'Approval' when` | 122 | Approval | if: env.target == 'pro' | evaluated once at stage entry against env |
| 🟡 approximated | `timeout` | 126 | Approval | timeout-minutes per step | Jenkins timeout covers the whole block |
| 🟡 approximated | `input` | 127 | Approval | environment protection | split the workflow at the gate; inline input step replaced by a notice |
| 🟡 approximated | `stage 'PRO Deploy' when` | 134 | PRO Deploy | if: env.target == 'pro' | evaluated once at stage entry against env |
| 🟡 approximated | `configFileProvider` | 138 | PRO Deploy | body inlined | wrapper semantics not reproduced |
| 🟡 approximated | `sh` | 139 | PRO Deploy | run | Groovy interpolation of non-env values needs review |
| 🔴 manual | `cucumber` | 116 | Acceptance Test | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `rocketSend` | 150 | Declarative: Post Actions | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `rocketSend` | 173 | Declarative: Post Actions | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `rocketSend` | 219 | Declarative: Post Actions | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Workspace hand-off

Jenkins runs every stage without an agent of its own in one workspace; the converted jobs hand it on as `j2gha-ws-<job>` artifacts (an archive per job, kept one day) and restore it instead of checking out (`J2GHA_WORKSPACE_HANDOFF=0` converts without).

- **Handed on by:** `setup`, `approval`. **Merged after running concurrently:** none (each later branch's own changes are replayed onto the first one's workspace).
- **Runtime requirements:** bash, GNU tar, findutils, coreutils and sed on the runner and in job containers: GitHub's Linux runners and Debian/Ubuntu-based images. busybox/Alpine images fail at the hand-off steps.
- **Same as Jenkins:** the files, directories, modes, symbolic and hard links every stage starts with, provided concurrent branches change different paths.
- **Approximated:** concurrent branches do not see each other's files while they run; a path two of them change takes the later branch's version (matrix cells: the later cell's, by name; in Jenkins: whichever wrote last); changes of timestamps alone are not handed on.
- **Fails instead:** an entry the job's user cannot read, a workspace that did not arrive from a job that ran - a nearest one or one the restore falls back on because a nearer job was skipped. Where that job's result is not visible to the restoring job (it is not one it needs directly), a missing workspace is taken as skipped, with a warning.

## Stage graph

```text
pipeline [declarative] agent: any
├── Setup
│   · script, <if>, <assign>×8, sh, oversion.take
├── Build
│   · sh×10
├── Publish
│   · withCredentials, sh
├── DEV Deploy
│   · withCredentials, configFileProvider, sh
├── PRE Deploy  [when]
│   · withCredentials, configFileProvider, sh
├── Acceptance Test  [when; agent label]
│   · sh×2, cucumber
├── Approval  [when]
│   · timeout, input
└── PRO Deploy  [when]
    · withCredentials, configFileProvider, sh
post: success, failure, unstable, aborted
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. Jobs on the pipeline agent hand its workspace on (see *Workspace hand-off*); jobs with an agent of their own do not share it (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🟡 2 approximated, ✅ 7 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`sh`** (🟡 13 approximated, ✅ 4 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`timeout`** (🟡 2 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`when`** (🟡 4 approximated): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`agent`** (🟡 1 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`input`** (🟡 1 approximated): input/submitter -> environment with required reviewers (no free-form input parameters at approval time).
  - Jenkins: [syntax #input](https://www.jenkins.io/doc/book/pipeline/syntax/#input)
  - GitHub Actions: [deployment-environments](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments) · [review-deployments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments) · [deployments-and-environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- **`post`** (⚪ 1 dropped, ✅ 3 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`withCredentials`** (✅ 4 mapped): file/SSH credentials must be materialised by a step; OIDC replaces long-lived cloud keys.
  - Jenkins: [step `withCredentials`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [use-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) · [secrets](https://docs.github.com/en/actions/concepts/security/secrets) · [secrets](https://docs.github.com/en/actions/reference/security/secrets)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
