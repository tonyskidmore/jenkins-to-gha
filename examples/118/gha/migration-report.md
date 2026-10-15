# Migration report: dvsa/olcs-ci `pipelines/app_release_package/Jenkinsfile`

- **Classification:** assisted (difficulty 23/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 60.3% (38 mapped, 11 approximated, 25 manual, 0 dropped)
- **Weighted step coverage (analysis):** 76.1%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 13.0 | 20 |
| step mapping | 6.0 | 25 |
| plugin coupling | 3.0 | 15 |
| library opacity | 0.0 | 15 |
| runtime coupling | 0.0 | 10 |
| security identity | 0 | 10 |
| control flow | 1.0 | 5 |

- **Hard gates:** none
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `parameters: booleanParam DRYRUN` | 10 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string VERSION` | 11 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string olcs_transxchange_version` | 12 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `parameters: string olcs_auth_version` | 13 |  | on.workflow_dispatch.inputs |  |
| ✅ mapped | `decl defaultS3Bucket = devapp-olcs-pri-olcs-deploy-s3/` | 21 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl templateS3Bucket = devapp-shd-pri-file-deploy-s3/` | 22 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl ldifLabel = olcs-dir-ldif-version` | 23 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl txcLabel = olcs-transxchange-version` | 24 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl txcFile = txc` | 25 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl authLabel = olcs_auth_version` | 26 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl authFile = openam` | 27 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl appVersionFile = ` | 28 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = App Branch Close and Tag (not currentl` | 49 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Get Repos` | 58 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `deleteDir` | 61 | Get Repos | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `assign stageName = Get App Release Tags` | 81 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `dir` | 101 | Get App Release Tags | working-directory |  |
| ✅ mapped | `sh` | 102 | Get App Release Tags | run |  |
| ✅ mapped | `assign appVersionFile = ${txcLabel} : '${params.olcs_tran` | 108 | Get App Release Tags | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign appVersionFile = ${authLabel} : '${params.olcs_aut` | 111 | Get App Release Tags | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Check and Build Release Artefacts` | 117 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl message = ` | 119 | Check and Build Release Artefacts | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Check Artefacts from Input Params` | 150 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl message = ` | 152 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl cmd = echo "2018-03-29 13:20      1024   s3://${de` | 155 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl cmd2 = grep ${authFile}-${params.olcs_auth_version` | 158 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl cmd3 = echo "2018-03-29 13:20      1024   s3://${d` | 174 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl cmd4 = grep ${txcFile}-${params.olcs_transxchange_` | 177 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Check App Version against Built artefa` | 195 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Create and Push Release Manifest` | 209 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `dir` | 214 | Create and Push Release Manifest | working-directory |  |
| ✅ mapped | `deleteDir` | 215 | Create and Push Release Manifest | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `checkout scm` | 217 | Create and Push Release Manifest | actions/checkout@v4 |  |
| ✅ mapped | `sh` | 223 | Create and Push Release Manifest | run |  |
| ✅ mapped | `sh` | 224 | Create and Push Release Manifest | run |  |
| ✅ mapped | `sh` | 226 | Create and Push Release Manifest | run |  |
| ✅ mapped | `sh` | 227 | Create and Push Release Manifest | run |  |
| ✅ mapped | `sh` | 229 | Create and Push Release Manifest | run |  |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `agent label 'master'` | 17 | main, App Branch Close and Tag (not currently integrated), Get Repos, Get App Release Tags | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `sh` | 156 | Check Artefacts from Input Params | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 159 | Check Artefacts from Input Params | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 175 | Check Artefacts from Input Params | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 178 | Check Artefacts from Input Params | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `if (params.DRYRUN)` | 197 | Check App Version against Built artefacts | if: env.DRYRUN == 'true' |  |
| 🟡 approximated | `if (params.DRYRUN)` | 211 | Create and Push Release Manifest | if: env.DRYRUN == 'true' |  |
| 🟡 approximated | `sh` | 216 | Create and Push Release Manifest | run |  |
| 🟡 approximated | `writeFile` | 225 | Create and Push Release Manifest | run: heredoc |  |
| 🟡 approximated | `sh` | 228 | Create and Push Release Manifest | run |  |
| 🔴 manual | `decl VERSION = params.VERSION` | 19 |  | - | Groovy variable assignment |
| 🔴 manual | `decl GitRepo = file://${env.WORKSPACE}/.gitlab/` | 20 |  | - | Groovy variable assignment |
| 🔴 manual | `decl repos = [[olcs-ssweb-version, olcs/olcs-selfserve,` | 36 |  | - | Groovy variable assignment |
| 🔴 manual | `for (int i = 0; i < repos.size; i++)` | 63 | Get Repos | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `for (int i = 0; i < repos.size; i++)` | 83 | Get App Release Tags | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `decl version = readFile('result').trim(...)` | 103 | Get App Release Tags | - | Groovy variable assignment from a step |
| 🔴 manual | `readFile` | 103 | Get App Release Tags | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `assign appVersionFile = ${ldifLabel} : '${version}'
` | 104 | Get App Release Tags | - | Groovy variable assignment |
| 🔴 manual | `print` | 113 | Get App Release Tags | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `for (int i = 0; i < repos.size; i++)` | 120 | Check and Build Release Artefacts | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `print` | 147 | Check and Build Release Artefacts | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `print` | 157 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `decl file = readFile('result2').trim(...)` | 160 | Check Artefacts from Input Params | - | Groovy variable assignment from a step |
| 🔴 manual | `readFile` | 160 | Check Artefacts from Input Params | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `print` | 161 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (file.contains(authFile + '-' + params.olcs_auth_ve)` | 162 | Check Artefacts from Input Params | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `print` | 176 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `decl file2 = readFile('result2').trim(...)` | 179 | Check Artefacts from Input Params | - | Groovy variable assignment from a step |
| 🔴 manual | `readFile` | 179 | Check Artefacts from Input Params | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `print` | 180 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (file2.contains(txcFile + '-' + params.olcs_transxc)` | 181 | Check Artefacts from Input Params | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `print` | 192 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `print` | 198 | Check App Version against Built artefacts | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `build job: Check App Release Tags` | 201 | Check App Version against Built artefacts | workflow_call / workflow_dispatch | downstream Jenkins job must be migrated; trigger with `gh workflow run` or a reusable workflow |
| 🔴 manual | `print` | 212 | Create and Push Release Manifest | - | Groovy method / helper call - port logic to a script |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- 18 statement(s) outside any stage kept in source order in 7 unnamed segment(s) (from line(s) 19, 58, 81, 117, 150, 195, 209)

## Stage graph

```text
pipeline [scripted] agent: label master
├── (outside any stage)
│   · <decl>×11, <assign>
├── App Branch Close and Tag (not currently integrated)
├── (outside any stage)
│   · <assign>
├── Get Repos
│   · deleteDir, <for>, dir, sh×2, checkout, <decl>, readFile, <assign>
├── (outside any stage)
│   · <assign>
├── Get App Release Tags
│   · <for>, <if>×2, <assign>×5, dir, sh, <decl>, readFile, print
├── (outside any stage)
│   · <assign>
├── Check and Build Release Artefacts
│   · <decl>×4, <for>, sh×2, print×4, readFile, <if>, <assign>
├── (outside any stage)
│   · <assign>
├── Check Artefacts from Input Params
│   · <decl>×7, sh×4, print×5, readFile×2, <if>×2, <assign>×2
├── (outside any stage)
│   · <assign>
├── Check App Version against Built artefacts
│   · <if>, print
├── (outside any stage)
│   · <assign>
└── Create and Push Release Manifest
    · <if>, print
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 12 manual, 🟡 2 approximated, ✅ 23 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`build`** (🔴 1 manual): downstream job -> reusable workflow call (wait) or workflow_dispatch via API (fire-and-forget).
  - Jenkins: [step `build`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [reuse-workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch) · [events-that-trigger-workflows #workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- **`sh`** (🟡 6 approximated, ✅ 6 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`agent`** (🟡 1 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`parameters`** (✅ 4 mapped): inputs are empty on push/schedule events; choose defaults explicitly.
  - Jenkins: [syntax #parameters](https://www.jenkins.io/doc/book/pipeline/syntax/#parameters)
  - GitHub Actions: [workflow-syntax #onworkflow_dispatchinputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs) · [events-that-trigger-workflows #workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
- **`dir`** (✅ 2 mapped)
  - Jenkins: [step `dir`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsworking-directory](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsworking-directory)
- **`checkout`** (✅ 1 mapped, ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
