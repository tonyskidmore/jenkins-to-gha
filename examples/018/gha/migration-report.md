# Migration report: dvsa/olcs-ci `pipelines/app_release_package/Jenkinsfile`

- **Classification:** assisted (difficulty 22/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 56.4% (28 mapped, 6 approximated, 22 manual, 0 dropped)
- **Weighted step coverage (analysis):** 75.6%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 13.0 | 20 |
| step mapping | 6.1 | 25 |
| plugin coupling | 2.2 | 15 |
| library opacity | 0.0 | 15 |
| runtime coupling | 0.0 | 10 |
| security identity | 0 | 10 |
| control flow | 1.0 | 5 |

- **Hard gates:** none
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `decl VERSION = params.VERSION` | 13 |  | - | the environment variable already has this value |
| ✅ mapped | `decl GitRepo = git@repo.shd.ci.nonprod.dvsa.aws:` | 14 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl defaultS3Bucket = devapp-olcs-pri-olcs-deploy-s3/` | 15 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl templateS3Bucket = devapp-shd-pri-file-deploy-s3/` | 16 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl ldifLabel = olcs-dir-ldif-version` | 17 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl txcLabel = olcs-transxchange-version` | 18 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl txcFile = txc` | 19 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl authLabel = olcs_auth_version` | 20 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl authFile = openam` | 21 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl appVersionFile = ` | 22 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = App Branch Close and Tag (not currentl` | 43 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Get Repos` | 52 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `deleteDir` | 55 | Get Repos | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `assign stageName = Get App Release Tags` | 74 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `dir` | 94 | Get App Release Tags | working-directory |  |
| ✅ mapped | `sh` | 95 | Get App Release Tags | run |  |
| ✅ mapped | `assign appVersionFile = ${txcLabel} : '${params.olcs_tran` | 101 | Get App Release Tags | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign appVersionFile = ${authLabel} : '${params.olcs_aut` | 104 | Get App Release Tags | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Check and Build Release Artefacts` | 110 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl message = ` | 112 | Check and Build Release Artefacts | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Check Artefacts from Input Params` | 143 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl message = ` | 145 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl cmd = s3cmd ls s3://${defaultS3Bucket}openam/ > re` | 148 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl cmd2 = grep ${authFile}-${params.olcs_auth_version` | 151 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl cmd3 = s3cmd ls s3://${defaultS3Bucket}api/ > resu` | 167 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl cmd4 = grep ${txcFile}-${params.olcs_transxchange_` | 170 | Check Artefacts from Input Params | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Check App Version against Built artefa` | 188 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign stageName = Create and Push Release Manifest` | 202 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `agent label 'master'` | 11 | main, App Branch Close and Tag (not currently integrated), Get Repos, Get App Release Tags | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `sh` | 149 | Check Artefacts from Input Params | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 152 | Check Artefacts from Input Params | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 168 | Check Artefacts from Input Params | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 171 | Check Artefacts from Input Params | run | Groovy interpolation of non-env values needs review |
| 🔴 manual | `decl repos = [[olcs-ssweb-version, olcs/olcs-selfserve,` | 30 |  | - | Groovy variable assignment |
| 🔴 manual | `for (int i = 0; i < repos.size; i++)` | 57 | Get Repos | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `for (int i = 0; i < repos.size; i++)` | 76 | Get App Release Tags | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `decl version = readFile('result').trim(...)` | 96 | Get App Release Tags | - | Groovy variable assignment from a step |
| 🔴 manual | `readFile` | 96 | Get App Release Tags | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `assign appVersionFile = ${ldifLabel} : '${version}'
` | 97 | Get App Release Tags | - | Groovy variable assignment |
| 🔴 manual | `print` | 106 | Get App Release Tags | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `for (int i = 0; i < repos.size; i++)` | 113 | Check and Build Release Artefacts | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `print` | 140 | Check and Build Release Artefacts | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `print` | 150 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `decl file = readFile('result2').trim(...)` | 153 | Check Artefacts from Input Params | - | Groovy variable assignment from a step |
| 🔴 manual | `readFile` | 153 | Check Artefacts from Input Params | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `print` | 154 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (file.contains(authFile + '-' + params.olcs_auth_ve)` | 155 | Check Artefacts from Input Params | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `print` | 169 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `decl file2 = readFile('result2').trim(...)` | 172 | Check Artefacts from Input Params | - | Groovy variable assignment from a step |
| 🔴 manual | `readFile` | 172 | Check Artefacts from Input Params | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `print` | 173 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (file2.contains(txcFile + '-' + params.olcs_transxc)` | 174 | Check Artefacts from Input Params | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `print` | 185 | Check Artefacts from Input Params | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (params.DRYRUN)` | 190 | Check App Version against Built artefacts | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (params.DRYRUN)` | 204 | Create and Push Release Manifest | placeholder | condition depends on Groovy runtime state |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- 18 statement(s) outside any stage kept in source order in 7 unnamed segment(s) (from line(s) 13, 52, 74, 110, 143, 188, 202)

## Stage graph

```text
pipeline [scripted] agent: label master
├── (outside any stage)
│   · <decl>×11, <assign>
├── App Branch Close and Tag (not currently integrated)
├── (outside any stage)
│   · <assign>
├── Get Repos
│   · deleteDir, <for>, dir, checkout, sh, <decl>, readFile, <assign>
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

- **`scripted`** (🔴 12 manual, ✅ 25 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`sh`** (🟡 4 approximated, ✅ 1 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`agent`** (🟡 1 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`dir`** (✅ 1 mapped)
  - Jenkins: [step `dir`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsworking-directory](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsworking-directory)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
