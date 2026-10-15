# Migration report: dvsa/mes-beta-sandbox `autonomous-single-access-mode/Jenkinsfile`

- **Classification:** assisted (difficulty 32/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 24.4% (6 mapped, 3 approximated, 23 manual, 0 dropped)
- **Weighted step coverage (analysis):** 76.3%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 13.0 | 20 |
| step mapping | 5.9 | 25 |
| plugin coupling | 2.2 | 15 |
| library opacity | 9 | 15 |
| runtime coupling | 2.0 | 10 |
| security identity | 0 | 10 |
| control flow | 0.0 | 5 |

- **Hard gates:** none
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `decl branch_name = ${env.BRANCH_NAME}` | 14 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl mobile_config_branch = master` | 17 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `deleteDir` | 22 |  | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `dir` | 35 | install dependencies | working-directory |  |
| ✅ mapped | `dir` | 41 | tests | working-directory |  |
| ✅ mapped | `deleteDir` | 64 |  | run: workspace cleanup | runners are ephemeral; kept for parity |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `agent label 'Globals.NONPROD_BUILDER_TAG'` | 19 | main, checkout, install dependencies, tests, build | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `wrap` | 28 | checkout | body inlined | wrapper semantics not reproduced |
| 🔴 manual | `decl Globals = new Globals(...)` | 8 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `new Globals` | 8 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl CommonFunctions = new CommonFunctions(...)` | 9 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `new CommonFunctions` | 9 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl GitFunctions = new GitFunctions(...)` | 10 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `new GitFunctions` | 10 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl MobileFunctions = new MobileFunctions(...)` | 11 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `new MobileFunctions` | 11 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl NVMFunctions = new NVMFunctions(...)` | 12 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `new NVMFunctions` | 12 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl ionic_app_id = Globals.MOBILE_APP_ID` | 15 |  | - | Groovy variable assignment |
| 🔴 manual | `decl nodejs_installation = Globals.MOBILE_NODE_JS` | 16 |  | - | Groovy variable assignment |
| 🔴 manual | `assign currentBuild.description = BRANCH: ${branch_name}` | 20 |  | - | Groovy variable assignment |
| 🔴 manual | `assign env.WSPACE = pwd(...)` | 24 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `pwd` | 24 |  | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `log` | 30 | checkout | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `git_check_out` | 31 | checkout | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 34 | install dependencies | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `run` | 36 | install dependencies | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `log` | 40 | tests | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `run` | 42 | tests | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (branch_name == "develop" || branch_name == "origin)` | 46 | build | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `shout` | 61 | build | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- line 26: timestamps {} around stage(s) 'checkout', 'install dependencies', 'tests', 'build' dropped (native in GitHub Actions)
- line 27: ansiColor {} around stage(s) 'checkout', 'install dependencies', 'tests', 'build' dropped (native in GitHub Actions)
- line 28: wrap {} around stage(s) 'checkout', 'install dependencies', 'tests', 'build' re-applied inside each enclosed stage and segment
- 13 statement(s) outside any stage kept in source order in 2 unnamed segment(s) (from line(s) 8, 64)

## Stage graph

```text
pipeline [scripted] agent: label Globals.NONPROD_BUILDER_TAG
├── (outside any stage)
│   · <decl>×9, new Globals, new CommonFunctions, new GitFunctions, new MobileFunctions, new NVMFunctions, <assign>×2, deleteDir …
├── checkout
│   · wrap, CommonFunctions.log, GitFunctions.git_check_out
├── install dependencies
│   · wrap, CommonFunctions.log, dir, NVMFunctions.run
├── tests
│   · wrap, CommonFunctions.log, dir, NVMFunctions.run
├── build
│   · wrap, <if>, CommonFunctions.log×2, MobileFunctions.ionic_cli_install, <decl>, GitFunctions.git_get_commit_hash, dir, MobileFunctions.ionic_pro_push …
└── (outside any stage)
    · deleteDir
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 15 manual, ✅ 2 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`agent`** (🟡 1 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`dir`** (✅ 2 mapped)
  - Jenkins: [step `dir`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsworking-directory](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsworking-directory)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
