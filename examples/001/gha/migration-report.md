# Migration report: apache/couchdb `build-aux/Jenkinsfile`

- **Classification:** significant-redesign (difficulty 46/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 68.6% (22 mapped, 11 approximated, 9 manual, 2 dropped)
- **Weighted step coverage (analysis):** 88.6%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 10 | 20 |
| step mapping | 2.9 | 25 |
| plugin coupling | 7.5 | 15 |
| library opacity | 0.0 | 15 |
| runtime coupling | 8.0 | 10 |
| security identity | 2 | 10 |
| control flow | 5 | 5 |

- **Hard gates:** DynamicParallel (each forces at least significant-redesign; see *Blocking items*)
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Secrets required

| Secret | Purpose |
|---|---|
| `DOCKERHUB_CREDS` | Jenkins credential 'dockerhub_creds' |

## Blocking items (hard gates)

- line 740: **DynamicParallel** - parallel(parallelStagesMap) → Emit a bounded matrix from a planning job (fromJSON) instead of runtime fan-out

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `stage 'Setup Env' post cleanup` |  | Setup Env | if: (always()) && (steps.s1.outcome == 'success') |  |
| ✅ mapped | `stage 'Build Docs' post cleanup` |  | Build Docs | if: (always()) && (steps.s5.outcome == 'success') |  |
| ✅ mapped | `stage 'Build Release Tarball' post failure` |  | Build Release Tarball | if: (always()) && (steps.s10.outcome == 'success') && ((steps.s11.outcome == 'failure' || steps.s12.outcome == 'failure' || steps.s13.outcome == 'failure' || steps.s14.outcome == 'failure' || steps.s15.outcome == 'failure' || steps.s16.outcome == 'failure')) |  |
| ✅ mapped | `stage 'Build Release Tarball' post success` |  | Build Release Tarball | if: (!cancelled()) && (steps.s10.outcome == 'success') && (!(steps.s11.outcome == 'failure' || steps.s12.outcome == 'failure' || steps.s13.outcome == 'failure' || steps.s14.outcome == 'failure' || steps.s15.outcome == 'failure' || steps.s16.outcome == 'failure' || steps.s17.outcome == 'failure')) |  |
| ✅ mapped | `stage 'Build Release Tarball' post cleanup` |  | Build Release Tarball | if: (always()) && (steps.s10.outcome == 'success') |  |
| ✅ mapped | `environment GIT_COMMITTER_NAME` | 605 |  | env |  |
| ✅ mapped | `environment GIT_COMMITTER_EMAIL` | 606 |  | env |  |
| ✅ mapped | `environment DOCKER_ARGS` | 611 |  | env |  |
| ✅ mapped | `agent docker '${DOCKER_IMAGE_BASE}-${MINIMUM_ERLANG_VERSION}'` | 624 | Setup Env | job container | job containers run as root; reuseNode has no equivalent |
| ✅ mapped | `agent docker '${DOCKER_IMAGE_BASE}-${MINIMUM_ERLANG_VERSION}'` | 667 | Build Docs | job container | job containers run as root; reuseNode has no equivalent |
| ✅ mapped | `sh` | 677 | Build Docs | run |  |
| ✅ mapped | `sh` | 678 | Build Docs | run |  |
| ✅ mapped | `sh` | 679 | Build Docs | run |  |
| ✅ mapped | `agent docker '${DOCKER_IMAGE_BASE}-${MINIMUM_ERLANG_VERSION}'` | 693 | Build Release Tarball | job container | job containers run as root; reuseNode has no equivalent |
| ✅ mapped | `sh` | 703 | Build Release Tarball | run |  |
| ✅ mapped | `sh` | 704 | Build Release Tarball | run |  |
| ✅ mapped | `sh` | 705 | Build Release Tarball | run |  |
| ✅ mapped | `sh` | 706 | Build Release Tarball | run |  |
| ✅ mapped | `sh` | 707 | Build Release Tarball | run |  |
| ✅ mapped | `sh` | 708 | Build Release Tarball | run |  |
| ✅ mapped | `archiveArtifacts` | 713 | Build Release Tarball | actions/upload-artifact@v4 | fingerprinting has no equivalent |
| ✅ mapped | `sh` | 716 | Build Release Tarball | run |  |
| ⚪ dropped | `options: buildDiscarder` |  |  | - | use artifact retention-days / repo settings |
| 🟡 approximated | `options: timeout` |  |  | timeout-minutes: 240 (per job) | Jenkins timeout covers the whole pipeline |
| ⚪ dropped | `options: timestamps` |  |  | - | native in GitHub Actions |
| 🟡 approximated | `script {}` | 634 | Setup Env | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `sh` | 655 | Setup Env | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `stage 'Build Docs' when` | 665 | Build Docs | if: env.ONLY_DOCS_CHANGED == '1' | evaluated once at stage entry against env |
| 🟡 approximated | `sh` | 683 | Build Docs | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `stage 'Build Release Tarball' when` | 691 | Build Release Tarball | if: env.ONLY_DOCS_CHANGED == '0' && env.ONLY_GITHUB_CHANGED == '0' | evaluated once at stage entry against env |
| 🟡 approximated | `stash 'tarball'` | 712 | Build Release Tarball | actions/upload-artifact@v4 | artifact hand-off between jobs; file permissions are not preserved; no matching files fails the step, as the stash does in Jenkins (if-no-files-found: error) |
| 🟡 approximated | `sh` | 719 | Build Release Tarball | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `stage 'Test and Package' when` | 727 | Test and Package | if: env.ONLY_DOCS_CHANGED == '0' && env.ONLY_GITHUB_CHANGED == '0' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 730 | Test and Package | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `parallel (step)` | 740 | Test and Package | sequential steps | scripted parallel branches serialised; split into jobs/matrix for real parallelism |
| 🔴 manual | `options: preserveStashes` |  |  | - | no GHA equivalent |
| 🔴 manual | `assign env.DOCS_CHANGED = 0` | 635 | Setup Env | - | Groovy variable assignment |
| 🔴 manual | `assign env.ONLY_DOCS_CHANGED = 0` | 636 | Setup Env | - | Groovy variable assignment |
| 🔴 manual | `assign env.GITHUB_CHANGED = 0` | 637 | Setup Env | - | Groovy variable assignment |
| 🔴 manual | `assign env.ONLY_GITHUB_CHANGED = 0` | 638 | Setup Env | - | Groovy variable assignment |
| 🔴 manual | `if (sh(returnStatus: true, script: docs_changed) == 0 )` | 639 | Setup Env | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (sh(returnStatus: true, script: github_changed) == )` | 645 | Setup Env | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `assign parallelStagesMap = meta.collectEntries(...)` | 732 | Test and Package | - | Groovy variable assignment from a step |
| 🔴 manual | `collectEntries` | 732 | Test and Package | - | Groovy method / helper call - port logic to a script |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Stage graph

```text
pipeline [declarative] agent: none
├── Setup Env  [agent docker; post: cleanup]
│   · script, <assign>×8, <if>×4
├── Build Docs  [when; agent docker; post: cleanup]
│   · sh×3
├── Build Release Tarball  [when; agent docker; post: success,failure,cleanup]
│   · sh×6
└── Test and Package  [when]
    · script, <assign>, meta.collectEntries, <if>, <expr>, parallel
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 7 manual, 🟡 2 approximated): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`options`** (🔴 1 manual)
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
- **`sh`** (🟡 3 approximated, ✅ 10 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`when`** (🟡 3 approximated): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`stash`** (🟡 1 approximated): stash/unstash between stages on different agents -> upload-artifact/download-artifact between jobs (file permissions are lost).
  - Jenkins: [step `stash`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- **`parallel`** (🟡 1 approximated): parallel stages -> independent jobs; failFast -> strategy.fail-fast only applies within a matrix.
  - Jenkins: [syntax #parallel](https://www.jenkins.io/doc/book/pipeline/syntax/#parallel)
  - GitHub Actions: [use-jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs) · [workflow-syntax #jobsjob_idneeds](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
- **`buildDiscarder`** (⚪ 1 dropped): no per-count run retention; artifact retention-days and the repository log retention setting.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepswith](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepswith) · [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- **`timestamps`** (⚪ 1 dropped): GHA logs are always timestamped - drop it.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [use-workflow-run-logs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs)
- **`post`** (✅ 5 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`environment`** (✅ 3 mapped): the env context is not available in jobs.<id>.if; credentials('id') -> secrets.<NAME>.
  - Jenkins: [syntax #environment](https://www.jenkins.io/doc/book/pipeline/syntax/#environment)
  - GitHub Actions: [workflow-syntax #env](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#env) · [variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) · [variables](https://docs.github.com/en/actions/concepts/workflows-and-actions/variables)
- **`agent`** (✅ 3 mapped): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`archiveArtifacts`** (✅ 1 mapped)
  - Jenkins: [step `archiveArtifacts`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) · [store-and-share-data](https://docs.github.com/en/actions/tutorials/store-and-share-data) · [download-workflow-artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
