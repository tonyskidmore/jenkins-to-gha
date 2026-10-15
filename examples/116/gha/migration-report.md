# Migration report: dvsa/cvs-auto-mobile-app-retired `Jenkinsfile`

- **Classification:** assisted (difficulty 45/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 51.0% (6 mapped, 7 approximated, 7 manual, 0 dropped)
- **Weighted step coverage (analysis):** 57.9%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 13.0 | 20 |
| step mapping | 10.5 | 25 |
| plugin coupling | 9.8 | 15 |
| library opacity | 0.0 | 15 |
| runtime coupling | 8.0 | 10 |
| security identity | 4 | 10 |
| control flow | 0.0 | 5 |

- **Hard gates:** none
- **Unknown steps (2):** `browserstack`, `withFolderProperties` - plugin or shared-library steps the step catalog does not know, each a manual item below. If every one were mapped, the difficulty would be **36/100 - assisted**.
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Secrets required

| Secret | Purpose |
|---|---|
| `JENKINS_IAM_USR` | Jenkins credential 'jenkins-iam' |
| `JENKINS_IAM_PSW` | Jenkins credential 'jenkins-iam' |
| `BROWSERSTACK_UPLOADER` | Jenkins credential 'browserstack-uploader' |

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `assign APP_ID = ` | 12 |  | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `checkout scm` | 15 | checkout | actions/checkout@v4 |  |
| ✅ mapped | `withCredentials usernamePassword 'jenkins-iam'` | 19 | Get IPA from AWS S3 | secrets -> step env |  |
| ✅ mapped | `withCredentials usernameColonPassword 'browserstack-uploader'` | 26 | install ipa in browserstack | secrets -> step env |  |
| ✅ mapped | `assign APP_ID = sh(script: 'test -n "$BROWSERSTACK_CREDS"` | 27 | install ipa in browserstack | run step; its output goes to $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `sh` | 38 | create report | run |  |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `node (in steps)` | 5 |  | inlined | nested agent allocation flattened |
| 🟡 approximated | `sh` | 20 | Get IPA from AWS S3 | run |  |
| 🟡 approximated | `sh` | 25 | install ipa in browserstack | run |  |
| 🟡 approximated | `sh` | 27 | install ipa in browserstack | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `sh` | 33 | test | run |  |
| 🟡 approximated | `publishHTML` | 39 | create report | actions/upload-artifact@v4 | HTML report published as artifact |
| 🔴 manual | `decl label = jenkins-node-${UUID.randomUUID().toString(` | 1 |  | - | Groovy variable assignment |
| 🔴 manual | `podTemplate` | 2 |  | placeholder step | redesign step with no deterministic mapping |
| 🔴 manual | `container (kubernetes)` | 6 |  | steps inlined | map the pod container image to a job container or docker run |
| 🔴 manual | `withFolderProperties` | 8 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign LBRANCH = "${env.BRANCH}".toLowerCase(...)` | 9 |  | - | Groovy variable assignment from a step |
| 🔴 manual | `toLowerCase` | 9 |  | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `browserstack` | 32 | test | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- line 2: stage(s) 'checkout', 'Get IPA from AWS S3', 'install ipa in browserstack', 'test', 'create report' nested in 'podTemplate' (plugin/library block) kept as its nested steps, in an unnamed segment
- 2 statement(s) outside any stage kept in source order in 1 unnamed segment(s) (from line(s) 1)
- no stage() blocks found - structure is opaque (library call or custom DSL)

## Stage graph

```text
pipeline [scripted]
└── (outside any stage)
    · <decl>, podTemplate, node, container, withFolderProperties, <assign>×3, "${env.BRANCH}".toLowerCase, stage×5 …
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 2 manual, ✅ 2 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`podTemplate`** (🔴 2 manual): Kubernetes pod agents -> ARC runner scale sets, or job container + services.
  - Jenkins: [step `podTemplate`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [actions-runner-controller](https://docs.github.com/en/actions/concepts/runners/actions-runner-controller) · [use-arc-in-a-workflow](https://docs.github.com/en/actions/how-tos/manage-runners/use-actions-runner-controller/use-arc-in-a-workflow) · [workflow-syntax #jobsjob_idservices](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idservices)
- **`sh`** (🟡 4 approximated, ✅ 1 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`node`** (🟡 1 approximated)
  - Jenkins: [step `node`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [self-hosted-runners](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners)
- **`checkout`** (✅ 1 mapped, ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
- **`withCredentials`** (✅ 2 mapped): file/SSH credentials must be materialised by a step; OIDC replaces long-lived cloud keys.
  - Jenkins: [step `withCredentials`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [use-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) · [secrets](https://docs.github.com/en/actions/concepts/security/secrets) · [secrets](https://docs.github.com/en/actions/reference/security/secrets)
