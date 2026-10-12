# Migration report: EclipseFdn/open-vsx.org `Jenkinsfile`

- **Classification:** assisted (difficulty 28/100)
- **Convertibility:** automatic
- **Automated mapping (effort estimate, not correctness):** 75.6% (24 mapped, 9 approximated, 6 manual, 2 dropped)
- **Weighted step coverage (analysis):** 70.5%

## Secrets required

| Secret | Purpose |
|---|---|
| `JENKINS_OPENVSX_AWS_KEY_ID` | Jenkins credential 'jenkins-openvsx-aws-key-id' |
| `JENKINS_OPENVSX_AWS_SECRET_KEY` | Jenkins credential 'jenkins-openvsx-aws-secret-key' |

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `post failure` |  |  | final job if: always() && (contains(needs.*.result, 'failure') || failure()) |  |
| ✅ mapped | `post cleanup` |  |  | final job if: always() |  |
| ✅ mapped | `post (workspace-dependent steps)` |  |  | final job | deleteDir run in the restored pipeline workspace (j2gha-ws-* artifacts) |
| ✅ mapped | `environment APP_NAME` | 49 |  | env |  |
| ✅ mapped | `environment NAMESPACE` | 50 |  | env |  |
| ✅ mapped | `environment IMAGE_NAME` | 51 |  | env |  |
| ✅ mapped | `environment CONTAINER_NAME` | 52 |  | env |  |
| ✅ mapped | `sh` | 76 | Build docker image | run |  |
| ✅ mapped | `sh` | 88 | Push docker image | run |  |
| ✅ mapped | `stage 'Deploy test' when` | 97 | Deploy test | if: env.BRANCH_NAME == 'test' | evaluated once at stage entry against env |
| ✅ mapped | `sh` | 102 | Deploy test | run |  |
| ✅ mapped | `stage 'Deploy staging' when` | 112 | Deploy staging | if: env.BRANCH_NAME == 'main' | evaluated once at stage entry against env |
| ✅ mapped | `sh` | 117 | Deploy staging | run |  |
| ✅ mapped | `stage 'Deploy production' when` | 127 | Deploy production | if: env.BRANCH_NAME == 'production' | evaluated once at stage entry against env |
| ✅ mapped | `sh` | 132 | Deploy production | run |  |
| ✅ mapped | `stage 'Deploy aws-staging' when` | 142 | Deploy aws-staging | if: env.BRANCH_NAME == 'aws-main' | evaluated once at stage entry against env |
| ✅ mapped | `withCredentials string 'jenkins-openvsx-aws-key-id'` | 146 | Deploy aws-staging | secrets -> step env |  |
| ✅ mapped | `withCredentials string 'jenkins-openvsx-aws-secret-key'` | 146 | Deploy aws-staging | secrets -> step env |  |
| ✅ mapped | `sh` | 150 | Deploy aws-staging | run |  |
| ✅ mapped | `stage 'Deploy aws-production' when` | 164 | Deploy aws-production | if: env.BRANCH_NAME == 'aws-production' | evaluated once at stage entry against env |
| ✅ mapped | `withCredentials string 'jenkins-openvsx-aws-key-id'` | 168 | Deploy aws-production | secrets -> step env |  |
| ✅ mapped | `withCredentials string 'jenkins-openvsx-aws-secret-key'` | 168 | Deploy aws-production | secrets -> step env |  |
| ✅ mapped | `sh` | 172 | Deploy aws-production | run |  |
| ✅ mapped | `deleteDir` | 198 | Declarative: Post Actions | run: workspace cleanup | runners are ephemeral; kept for parity |
| ⚪ dropped | `post fixed` |  |  | - | no GHA equivalent |
| ⚪ dropped | `options: buildDiscarder` |  |  | - | use artifact retention-days / repo settings |
| 🟡 approximated | `options: timeout` |  |  | timeout-minutes: 30 (per job) | Jenkins timeout covers the whole pipeline |
| 🟡 approximated | `environment IMAGE_TAG` | 53 |  | evaluated by shell at runtime | pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step |
| 🟡 approximated | `agent label 'docker-build'` | 72 | Build docker image | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `agent label 'docker-build'` | 83 | Push docker image | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `docker registry login` | 87 | Push docker image | docker/login-action (recommended) |  |
| 🟡 approximated | `withKubeConfig` | 101 | Deploy test | body inlined | configure identity via OIDC / approved action |
| 🟡 approximated | `withKubeConfig` | 116 | Deploy staging | body inlined | configure identity via OIDC / approved action |
| 🟡 approximated | `withKubeConfig` | 131 | Deploy production | body inlined | configure identity via OIDC / approved action |
| 🟡 approximated | `mail` | 186 | Declarative: Post Actions | notification placeholder | use an approved notification action (e.g. slackapi/slack-github-action) |
| 🔴 manual | `agent kubernetes` | 2 | Deploy test, Deploy staging, Deploy production, Deploy aws-staging, Deploy aws-production | runs-on: ubuntu-latest | pod templates need job containers/services or ARC runner scale sets |
| 🔴 manual | `container (kubernetes)` | 100 | Deploy test | steps inlined | map the pod container image to a job container or docker run |
| 🔴 manual | `container (kubernetes)` | 115 | Deploy staging | steps inlined | map the pod container image to a job container or docker run |
| 🔴 manual | `container (kubernetes)` | 130 | Deploy production | steps inlined | map the pod container image to a job container or docker run |
| 🔴 manual | `container (kubernetes)` | 145 | Deploy aws-staging | steps inlined | map the pod container image to a job container or docker run |
| 🔴 manual | `container (kubernetes)` | 167 | Deploy aws-production | steps inlined | map the pod container image to a job container or docker run |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Workspace hand-off

Jenkins runs every stage without an agent of its own in one workspace; the converted jobs hand it on as `j2gha-ws-<job>` artifacts (an archive per job, kept one day) and restore it instead of checking out (`J2GHA_WORKSPACE_HANDOFF=0` converts without).

- **Handed on by:** `deploy-test`. **Merged after running concurrently:** none (each later branch's own changes are replayed onto the first one's workspace).
- **Runtime requirements:** bash, GNU tar, findutils, coreutils and sed on the runner and in job containers: GitHub's Linux runners and Debian/Ubuntu-based images. busybox/Alpine images fail at the hand-off steps.
- **Same as Jenkins:** the files, directories, modes, symbolic and hard links every stage starts with, provided concurrent branches change different paths.
- **Approximated:** concurrent branches do not see each other's files while they run; a path two of them change takes the later branch's version (matrix cells: the later cell's, by name; in Jenkins: whichever wrote last); changes of timestamps alone are not handed on.
- **Fails instead:** an entry the job's user cannot read, a workspace that did not arrive from a job that ran - a nearest one or one the restore falls back on because a nearer job was skipped. Where that job's result is not visible to the restoring job (it is not one it needs directly), a missing workspace is taken as skipped, with a warning.

## Stage graph

```text
pipeline [declarative] agent: kubernetes kubedeploy-agent
├── Build docker image  [agent label]
│   · sh
├── Push docker image  [agent label]
│   · withDockerRegistry, sh
├── Deploy test  [when]
│   · container, withKubeConfig, sh
├── Deploy staging  [when]
│   · container, withKubeConfig, sh
├── Deploy production  [when]
│   · container, withKubeConfig, sh
├── Deploy aws-staging  [when]
│   · container, withCredentials, sh
└── Deploy aws-production  [when]
    · container, withCredentials, sh
post: failure, fixed, cleanup
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. Jobs on the pipeline agent hand its workspace on (see *Workspace hand-off*); jobs with an agent of their own do not share it (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`agent`** (🔴 1 manual, 🟡 2 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`podTemplate`** (🔴 5 manual): Kubernetes pod agents -> ARC runner scale sets, or job container + services.
  - Jenkins: [step `podTemplate`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [actions-runner-controller](https://docs.github.com/en/actions/concepts/runners/actions-runner-controller) · [use-arc-in-a-workflow](https://docs.github.com/en/actions/how-tos/manage-runners/use-actions-runner-controller/use-arc-in-a-workflow) · [workflow-syntax #jobsjob_idservices](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idservices)
- **`environment`** (🟡 1 approximated, ✅ 4 mapped): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`docker`** (🟡 1 approximated)
  - Jenkins: [docker](https://www.jenkins.io/doc/book/pipeline/docker/)
  - GitHub Actions: [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container) · [use-docker-service-containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers) · [publish-docker-images](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- **`post`** (⚪ 1 dropped, ✅ 3 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`buildDiscarder`** (⚪ 1 dropped): no per-count run retention; artifact retention-days and the repository log retention setting.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepswith](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepswith) · [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- **`sh`** (✅ 7 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`when`** (✅ 5 mapped): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`withCredentials`** (✅ 4 mapped): file/SSH credentials must be materialised by a step; OIDC replaces long-lived cloud keys.
  - Jenkins: [step `withCredentials`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [use-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) · [secrets](https://docs.github.com/en/actions/concepts/security/secrets) · [secrets](https://docs.github.com/en/actions/reference/security/secrets)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
