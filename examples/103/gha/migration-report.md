# Migration report: frankarobotics/franka_description `Jenkinsfile`

- **Classification:** significant-redesign (difficulty 55/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 69.0% (41 mapped, 43 approximated, 13 manual, 1 dropped)
- **Weighted step coverage (analysis):** 72.8%

## Blocking items (hard gates)

- line ?: **SharedLibrary** - fe-gitlab-pipeline-steps@lts-2.2 → Library steps are opaque to static analysis; map them to composite actions/reusable workflows

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `post always` |  |  | final job if: always() |  |
| ✅ mapped | `post (workspace-dependent steps)` |  |  | final job | cleanWs run in the restored pipeline workspace (j2gha-ws-* artifacts) |
| ✅ mapped | `environment DEPENDENCIES_DIR` | 14 |  | env |  |
| ✅ mapped | `environment ARTIFACT_FILENAME` | 16 |  | env |  |
| ✅ mapped | `environment DIST_DIR` | 17 |  | env |  |
| ✅ mapped | `decl commitMsg = sh(returnStdout: true, script: 'git lo` | 37 | Check Commit Message | run step; its output goes to $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `sh` | 53 | Get Ready | run |  |
| ✅ mapped | `sh` | 65 | Run URDF tests | run |  |
| ✅ mapped | `stage 'Build robot URDFs and SRDFs' matrix (ROBOT[5])` | 70 | Build robot URDFs and SRDFs | strategy.matrix |  |
| ✅ mapped | `dir` | 81 | Build URDF and SRDF | working-directory |  |
| ✅ mapped | `stage 'Build End Effector URDFs' matrix (EE[2])` | 92 | Build End Effector URDFs | strategy.matrix |  |
| ✅ mapped | `dir` | 103 | Build URDF | working-directory |  |
| ✅ mapped | `agent docker 'franka/build/ubuntu-24.04:0.27.0'` | 113 | Archive URDFs and SRDFs | job container | job containers run as root; reuseNode has no equivalent |
| ✅ mapped | `sh` | 123 | Cleanup | run |  |
| ✅ mapped | `dir` | 138 | Arm3R | working-directory |  |
| ✅ mapped | `sh` | 141 | Arm3R | run |  |
| ✅ mapped | `sh` | 142 | Arm3R | run |  |
| ✅ mapped | `dir` | 149 | Arm3P | working-directory |  |
| ✅ mapped | `sh` | 152 | Arm3P | run |  |
| ✅ mapped | `sh` | 153 | Arm3P | run |  |
| ✅ mapped | `dir` | 160 | Arm3Rv2 | working-directory |  |
| ✅ mapped | `sh` | 163 | Arm3Rv2 | run |  |
| ✅ mapped | `sh` | 164 | Arm3Rv2 | run |  |
| ✅ mapped | `dir` | 171 | Arm3Rv2.1 | working-directory |  |
| ✅ mapped | `sh` | 174 | Arm3Rv2.1 | run |  |
| ✅ mapped | `sh` | 175 | Arm3Rv2.1 | run |  |
| ✅ mapped | `dir` | 182 | TMRv0.2 | working-directory |  |
| ✅ mapped | `sh` | 185 | TMRv0.2 | run |  |
| ✅ mapped | `sh` | 186 | TMRv0.2 | run |  |
| ✅ mapped | `sh` | 214 | cobot_pump | run |  |
| ✅ mapped | `sh` | 222 | franka_hand | run |  |
| ✅ mapped | `dir` | 232 | Unstash URDF | working-directory |  |
| ✅ mapped | `sh` | 234 | Unstash URDF | run |  |
| ✅ mapped | `dir` | 236 | Unstash URDF | working-directory |  |
| ✅ mapped | `sh` | 238 | Unstash URDF | run |  |
| ✅ mapped | `dir` | 249 | Create archive | working-directory |  |
| ✅ mapped | `sh` | 250 | Create archive | run |  |
| ✅ mapped | `archiveArtifacts` | 260 | Create archive | actions/upload-artifact@v4 |  |
| ✅ mapped | `sh` | 311 | Declarative: Post Actions | run |  |
| ✅ mapped | `cleanWs` | 312 | Declarative: Post Actions | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `sh` | 313 | Declarative: Post Actions | run |  |
| 🟡 approximated | `options: timeout` |  |  | timeout-minutes: 120 (per job) | Jenkins timeout covers the whole pipeline |
| ⚪ dropped | `options: buildDiscarder` |  |  | - | use artifact retention-days / repo settings |
| 🟡 approximated | `agent label 'docker'` | 7 | Check Commit Message, Get Ready | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `script {}` | 36 | Check Commit Message | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `sh` | 37 | Check Commit Message | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `script {}` | 49 | Get Ready | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `agent dockerfile 'Dockerfile'` | 58 | Run URDF tests | docker build + docker run wrapper | steps run via `docker run` in the built image |
| 🟡 approximated | `sh` | 80 | Build URDF and SRDF | run |  |
| 🟡 approximated | `stash 'ROBOT_${ROBOT}_urdf'` | 82 | Build URDF and SRDF | actions/upload-artifact@v4 | artifact hand-off between jobs; file permissions are not preserved; no matching files fails the step, as the stash does in Jenkins (if-no-files-found: error) |
| 🟡 approximated | `stash 'ROBOT_${ROBOT}_srdf'` | 83 | Build URDF and SRDF | actions/upload-artifact@v4 | artifact hand-off between jobs; file permissions are not preserved; no matching files fails the step, as the stash does in Jenkins (if-no-files-found: error) |
| 🟡 approximated | `sh` | 102 | Build URDF | run |  |
| 🟡 approximated | `stash 'EE_${EE}_urdf'` | 104 | Build URDF | actions/upload-artifact@v4 | artifact hand-off between jobs; file permissions are not preserved; no matching files fails the step, as the stash does in Jenkins (if-no-files-found: error) |
| 🟡 approximated | `sh` | 128 | Create directory structure | run |  |
| 🟡 approximated | `sh` | 129 | Create directory structure | run |  |
| 🟡 approximated | `sh` | 130 | Create directory structure | run |  |
| 🟡 approximated | `stage 'Move robot urdfs and srdfs into correct robot arm directory' nested parallel` | 133 | Move robot urdfs and srdfs into correct robot arm directory | sequential steps | nested parallel branches serialised inside one job |
| 🟡 approximated | `sh` | 137 | Arm3R | run |  |
| 🟡 approximated | `unstash 'ROBOT_fr3_urdf'` | 139 | Arm3R | actions/download-artifact@v4 |  |
| 🟡 approximated | `unstash 'ROBOT_fr3_srdf'` | 140 | Arm3R | actions/download-artifact@v4 |  |
| 🟡 approximated | `sh` | 148 | Arm3P | run |  |
| 🟡 approximated | `unstash 'ROBOT_fp3_urdf'` | 150 | Arm3P | actions/download-artifact@v4 |  |
| 🟡 approximated | `unstash 'ROBOT_fp3_srdf'` | 151 | Arm3P | actions/download-artifact@v4 |  |
| 🟡 approximated | `sh` | 159 | Arm3Rv2 | run |  |
| 🟡 approximated | `unstash 'ROBOT_fr3v2_urdf'` | 161 | Arm3Rv2 | actions/download-artifact@v4 |  |
| 🟡 approximated | `unstash 'ROBOT_fr3v2_srdf'` | 162 | Arm3Rv2 | actions/download-artifact@v4 |  |
| 🟡 approximated | `sh` | 170 | Arm3Rv2.1 | run |  |
| 🟡 approximated | `unstash 'ROBOT_fr3v2_1_urdf'` | 172 | Arm3Rv2.1 | actions/download-artifact@v4 |  |
| 🟡 approximated | `unstash 'ROBOT_fr3v2_1_srdf'` | 173 | Arm3Rv2.1 | actions/download-artifact@v4 |  |
| 🟡 approximated | `sh` | 181 | TMRv0.2 | run |  |
| 🟡 approximated | `unstash 'ROBOT_tmrv0_2_urdf'` | 183 | TMRv0.2 | actions/download-artifact@v4 |  |
| 🟡 approximated | `unstash 'ROBOT_tmrv0_2_srdf'` | 184 | TMRv0.2 | actions/download-artifact@v4 |  |
| 🟡 approximated | `script {}` | 194 | Copy meshes to dist | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `sh` | 195 | Copy meshes to dist | run |  |
| 🟡 approximated | `sh` | 198 | Copy meshes to dist | run |  |
| 🟡 approximated | `sh` | 206 | Create End Effector directories | run |  |
| 🟡 approximated | `sh` | 207 | Create End Effector directories | run |  |
| 🟡 approximated | `stage 'Copy meshes' nested parallel` | 210 | Copy meshes | sequential steps | nested parallel branches serialised inside one job |
| 🟡 approximated | `unstash 'EE_cobot_pump_urdf'` | 233 | Unstash URDF | actions/download-artifact@v4 |  |
| 🟡 approximated | `unstash 'EE_franka_hand_urdf'` | 237 | Unstash URDF | actions/download-artifact@v4 |  |
| 🟡 approximated | `sh` | 246 | Create archive | run |  |
| 🟡 approximated | `sh` | 247 | Create archive | run |  |
| 🟡 approximated | `stage 'Publish to artifactory' when` | 266 | Publish to artifactory | if: (!((job.status) == ('UNSTABLE'))) && ((env.TAG_NAME != '' || env.BRANCH_NAME == env.BRANCH_NAME)) | evaluated once at stage entry against env |
| 🟡 approximated | `stage 'Trigger upstream franka_ros2_ws builds' parallel (2 branches)` | 283 | Trigger upstream franka_ros2_ws builds | parallel jobs with needs | branches run as separate jobs: the pipeline workspace is handed on to them and from them to later stages (j2gha-ws-* artifacts), but branches running at the same time do not see each other's files, and a file two branches write takes the later branch's version |
| 🟡 approximated | `script {}` | 314 | Declarative: Post Actions | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🔴 manual | `options: gitLabConnection` |  |  | - | no GHA equivalent |
| 🔴 manual | `environment VERSION = feDetermineVersionFromGit(...)` | 15 |  | env | value computed by a library/plugin function - compute in a step and write to $GITHUB_ENV |
| 🔴 manual | `decl skipKeywords = [wip, [skip ci], [skip-ci], [ci ski` | 38 | Check Commit Message | - | Groovy variable assignment |
| 🔴 manual | `if (skipKeywords.any { commitMsg.toLowerCase().contain)` | 39 | Check Commit Message | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `notifyBitbucket` | 50 | Get Ready | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl robs = [fp3, fr3, fr3v2, fr3v2_1, tmrv0_2]` | 196 | Copy meshes to dist | - | Groovy variable assignment |
| 🔴 manual | `decl copyCmd = robs.collect { "cp -r meshes/robots/${it` | 197 | Copy meshes to dist | - | Groovy variable assignment from a step |
| 🔴 manual | `collect` | 197 | Copy meshes to dist | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `fePublishOpkg` | 276 | Publish to artifactory | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `fePublishBuildInfo` | 277 | Publish to artifactory | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `build job: FCI/franka_ros2_ws/humble` | 287 | humble | workflow_call / workflow_dispatch | downstream Jenkins job must be migrated; trigger with `gh workflow run` or a reusable workflow |
| 🔴 manual | `build job: FCI/franka_ros2_ws/jazzy` | 295 | jazzy | workflow_call / workflow_dispatch | downstream Jenkins job must be migrated; trigger with `gh workflow run` or a reusable workflow |
| 🔴 manual | `feNotifySCM` | 315 | Declarative: Post Actions | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Workspace hand-off

Jenkins runs every stage without an agent of its own in one workspace; the converted jobs hand it on as `j2gha-ws-<job>` artifacts (an archive per job, kept one day) and restore it instead of checking out (`J2GHA_WORKSPACE_HANDOFF=0` converts without).

- **Handed on by:** `check-commit-message`, `run-urdf-tests`, `archive-urdfs-and-srdfs`, `trigger-upstream-franka_ros2_ws-builds-h`, `trigger-upstream-franka_ros2_ws-builds-j`. **Merged after running concurrently:** `trigger-upstream-franka_ros2_ws-builds-h`, `trigger-upstream-franka_ros2_ws-builds-j` (each later branch's own changes are replayed onto the first one's workspace).
- **Runtime requirements:** bash, GNU tar, findutils, coreutils and sed on the runner and in job containers: GitHub's Linux runners and Debian/Ubuntu-based images. busybox/Alpine images fail at the hand-off steps.
- **Same as Jenkins:** the files, directories, modes, symbolic and hard links every stage starts with, provided concurrent branches change different paths.
- **Approximated:** concurrent branches do not see each other's files while they run; a path two of them change takes the later branch's version (in Jenkins: whichever wrote last); changes of timestamps alone and matrix cells' changes are not handed on.
- **Fails instead:** an entry the job's user cannot read, a workspace that did not arrive from a job that ran - a nearest one or one the restore falls back on because a nearer job was skipped. Where that job's result is not visible to the restoring job (it is not one it needs directly), a missing workspace is taken as skipped, with a warning.

## Stage graph

```text
pipeline [declarative] agent: label docker
├── Check Commit Message
│   · script, <decl>×2, sh, <if>, <assign>, error
├── Get Ready
│   · script, notifyBitbucket, sh
├── Run URDF tests  [agent dockerfile]
│   · sh
├── Build robot URDFs and SRDFs  [matrix ROBOT[5]]
│   └── Build URDF and SRDF
│       · sh, dir, stash×2
├── Build End Effector URDFs  [matrix EE[2]]
│   └── Build URDF
│       · sh, dir, stash
├── Archive URDFs and SRDFs  [agent docker]
│   ├── Cleanup
│   │   · sh
│   ├── Create directory structure
│   │   · sh×3
│   ├── Move robot urdfs and srdfs into correct robot arm directory  [parallel]
│   │   ├── Arm3R
│   │   │   · sh×3, dir, unstash×2
│   │   ├── Arm3P
│   │   │   · sh×3, dir, unstash×2
│   │   ├── Arm3Rv2
│   │   │   · sh×3, dir, unstash×2
│   │   ├── Arm3Rv2.1
│   │   │   · sh×3, dir, unstash×2
│   │   └── TMRv0.2
│   │       · sh×3, dir, unstash×2
│   ├── Copy meshes to dist
│   │   · script, sh×2, <decl>×2, robs.collect, <expr>
│   ├── Extract End Effector URDFs
│   │   ├── Create End Effector directories
│   │   │   · sh×2
│   │   ├── Copy meshes  [parallel]
│   │   │   ├── cobot_pump
│   │   │   │   · sh
│   │   │   └── franka_hand
│   │   │       · sh
│   │   └── Unstash URDF
│   │       · dir×2, unstash×2, sh×2
│   ├── Create archive
│   │   · sh×3, dir, archiveArtifacts
│   └── Publish to artifactory  [when]
│       · fePublishOpkg, fePublishBuildInfo
└── Trigger upstream franka_ros2_ws builds  [parallel]
    ├── humble
    │   · build
    └── jazzy
        · build
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

- **`environment`** (🔴 1 manual, ✅ 3 mapped): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
- **`scripted`** (🔴 4 manual, 🟡 4 approximated, ✅ 1 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`options`** (🔴 1 manual)
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
- **`build`** (🔴 2 manual): downstream job -> reusable workflow call (wait) or workflow_dispatch via API (fire-and-forget).
  - Jenkins: [step `build`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [reuse-workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch) · [events-that-trigger-workflows #workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- **`sh`** (🟡 17 approximated, ✅ 20 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`agent`** (🟡 2 approximated, ✅ 1 mapped): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`stash`** (🟡 3 approximated): stash/unstash between stages on different agents -> upload-artifact/download-artifact between jobs (file permissions are lost).
  - Jenkins: [step `stash`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`parallel`** (🟡 3 approximated): parallel stages -> independent jobs; failFast -> strategy.fail-fast only applies within a matrix.
  - Jenkins: [syntax #parallel](https://www.jenkins.io/doc/book/pipeline/syntax/#parallel)
  - GitHub Actions: [use-jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs) · [workflow-syntax #jobsjob_idneeds](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
- **`unstash`** (🟡 12 approximated)
  - Jenkins: [step `unstash`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`when`** (🟡 1 approximated): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`buildDiscarder`** (⚪ 1 dropped): no per-count run retention; artifact retention-days and the repository log retention setting.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepswith](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepswith) · [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- **`post`** (✅ 2 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`matrix`** (✅ 2 mapped): excludes with notValues must be expanded explicitly; matrix job limit per workflow run.
  - Jenkins: [syntax #declarative-matrix](https://www.jenkins.io/doc/book/pipeline/syntax/#declarative-matrix)
  - GitHub Actions: [run-job-variations](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations) · [workflow-syntax #jobsjob_idstrategymatrix](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstrategymatrix)
- **`dir`** (✅ 10 mapped)
  - Jenkins: [step `dir`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsworking-directory](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsworking-directory)
- **`archiveArtifacts`** (✅ 1 mapped)
  - Jenkins: [step `archiveArtifacts`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data) · [download-workflow-artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
