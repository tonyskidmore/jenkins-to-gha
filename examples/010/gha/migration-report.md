# Migration report: apicollective/apibuilder `Jenkinsfile`

- **Classification:** significant-redesign (difficulty 67/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 32.4% (5 mapped, 3 approximated, 13 manual, 0 dropped)
- **Weighted step coverage (analysis):** 32.9%

## Secrets required

| Secret | Purpose |
|---|---|
| `JENKINS_ARGOCD_TOKEN` | Jenkins credential 'jenkins-argocd-token' |

## Blocking items (hard gates)

- line ?: **SharedLibrary** - lib-jenkins-pipeline → Library steps are opaque to static analysis; map them to composite actions/reusable workflows

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `echo` | 18 | Checkout | run: echo |  |
| ✅ mapped | `checkout scm` | 19 | Checkout | actions/checkout@v4 |  |
| ✅ mapped | `withCredentials string 'jenkins-argocd-token'` | 41 |  | secrets -> step env |  |
| ✅ mapped | `cleanWs` | 66 |  | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `echo` | 67 |  | run: echo |  |
| 🟡 approximated | `(no pipeline timeout)` |  |  | timeout-minutes: 60 | explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change |
| 🟡 approximated | `node (in steps)` | 13 |  | inlined | nested agent allocation flattened |
| 🟡 approximated | `try/catch/finally (line 14)` | 14 |  | steps; catch -> if: a try step failed; finally -> if: always() once entered | exception types are not distinguished |
| 🔴 manual | `decl _ = <not implemented yet for class: org.codehaus.g` | 1 |  | - | Groovy variable assignment |
| 🔴 manual | `decl sbtOnMain = no` | 3 |  | - | Groovy variable assignment |
| 🔴 manual | `decl podLabel = Jenkinsfile-apibuilder` | 8 |  | - | Groovy variable assignment |
| 🔴 manual | `podTemplate` | 9 |  | placeholder step | redesign step with no deterministic mapping |
| 🔴 manual | `checkoutWithTags` | 15 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign semversion = taggingv2(...)` | 24 | tagging | - | Groovy variable assignment from a step |
| 🔴 manual | `taggingv2` | 24 | tagging | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `println` | 25 | tagging | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `checkoutWithTags` | 29 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl jsondata = 
      [{"serviceName": "apibuilder-api` | 31 |  | - | Groovy variable assignment |
| 🔴 manual | `mainJenkinsBuildArgo` | 42 |  | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign currentBuild.result = FAILURE` | 62 |  | - | Groovy variable assignment |
| 🔴 manual | `throw (throw e)` | 63 |  | placeholder | Groovy control flow requires manual migration |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Interpretation notes

How the Jenkinsfile was read before conversion (scripted structure, approximations, statements the IR could not place):

- line 9: stage(s) 'Checkout', 'tagging' nested in 'podTemplate' (plugin/library block) kept as its nested steps, in an unnamed segment
- 4 statement(s) outside any stage kept in source order in 1 unnamed segment(s) (from line(s) 1)
- no stage() blocks found - structure is opaque (library call or custom DSL)

## Stage graph

```text
pipeline [scripted]
└── (outside any stage)
    · <decl>×4, podTemplate, node, <try>, checkoutWithTags×2, stage×2, echo, checkout …
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 6 manual, 🟡 1 approximated): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`podTemplate`** (🔴 1 manual): Kubernetes pod agents -> ARC runner scale sets, or job container + services.
  - Jenkins: [step `podTemplate`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [actions-runner-controller](https://docs.github.com/en/actions/concepts/runners/actions-runner-controller) · [use-arc-in-a-workflow](https://docs.github.com/en/actions/how-tos/manage-runners/use-actions-runner-controller/use-arc-in-a-workflow) · [workflow-syntax #jobsjob_idservices](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idservices)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`node`** (🟡 1 approximated)
  - Jenkins: [step `node`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [self-hosted-runners](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners)
- **`checkout`** (✅ 1 mapped, ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
- **`withCredentials`** (✅ 1 mapped): file/SSH credentials must be materialised by a step; OIDC replaces long-lived cloud keys.
  - Jenkins: [step `withCredentials`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [use-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) · [secrets](https://docs.github.com/en/actions/concepts/security/secrets) · [secrets](https://docs.github.com/en/actions/reference/security/secrets)
