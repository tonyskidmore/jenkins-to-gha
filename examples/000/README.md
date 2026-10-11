# Example 000: hands-on walkthrough

<!-- j2gha:walkthrough -->

This walkthrough takes one realistic Jenkins pipeline from "it works on Jenkins" to "the converted GitHub Actions
workflow provably behaves the same way". You will:

1. **Run the original Jenkinsfile on Jenkins**, watch it in the browser, approve its deployment gate and check that
   what it produced is right (Part 1). This is the baseline.
2. **Run every harness stage** on it: analysis, conversion, static validation, then differential execution on act,
   on real GitHub Actions with self-hosted runners and on GitHub-hosted runners (Parts 2 to 7).
3. **Break the conversion on purpose** and watch the harness catch it (Part 8).

Allow about an hour. Only this `README.md` and the [`Jenkinsfile`](Jenkinsfile) are tracked in git. Everything the
harness generates here (`analysis/`, `gha/`, `runs/` and a `RESULTS.md` results page) is gitignored, so you can repeat
the walkthrough as often as you like (see [Reset](#reset)).

> All commands are run from the repository root.

## The pipeline

[`Jenkinsfile`](Jenkinsfile) builds, tests, packages, publishes and deploys `inventory-service`, a small Python
stock-keeping service. To keep the walkthrough self-contained, the first stage writes the service's source code into
the workspace (`scaffoldSources()` at the bottom of the file), where a real pipeline would run `checkout scm`. The
service and its tests use only the Python standard library.

```text
Prepare sources ─► Build ─► Quality (parallel) ─────────► Compatibility (matrix) ─► Publish ──────────► Deploy
                            ├─ Unit tests                 ├─ sqlite / text           when: version is     when: DEPLOY_ENV
                            ├─ Lint                       ├─ memory / json           not -SNAPSHOT        is not 'none',
                            └─ Integration tests          └─ sqlite / json                                then waits for
                               when: RUN_INTEGRATION_TESTS   (memory / text excluded)                     approval
```

It deliberately uses the constructs that make migrations hard:

| Area | Jenkins constructs used |
|---|---|
| Structure | `agent { label 'linux' }`, sequential stages, `parallel`, `matrix` with `axes`/`excludes`, a stage with `input` |
| Configuration | `options` (buildDiscarder, timeout, timestamps, disableConcurrentBuilds, skipDefaultCheckout), `triggers { cron('H ...') }`, string/choice/boolean `parameters` |
| Environment | literals, values copied from `params`, `sh(returnStdout: true).trim()`, GString interpolation, stage `environment`, `credentials()` |
| Conditions | `when { expression }`, `when { not { expression } }`, `when { beforeInput true }`, a `script {}` block with `if`/`else` |
| Steps | `sh`, `echo`, `writeFile`, `deleteDir`, `dir`, `stash`/`unstash`, `retry`, `timeout`, `catchError`, `withCredentials`, a helper method |
| Reporting | `junit`, `publishHTML`, `archiveArtifacts` with fingerprints, `currentBuild.displayName` |
| Post conditions | pipeline `post` with `always`, `success`, `unstable` and `failure` (`mail`); stage `post { always }` |
| Approval | `input` with a parameter (`CHANGE_TICKET`) and `submitterParameter` (`APPROVER`) |

## Before you start

Check the [prerequisites](../../docs/prerequisites.md), then build the harness images once (several minutes the
first time, then cached):

```bash
docker info --format 'Docker {{.ServerVersion}}'
gh auth status
uv sync
uv run j2gha docker build
```

---

## Part 1: Run the original Jenkinsfile on Jenkins

### 1.1 Start the disposable Jenkins controller

```bash
uv run j2gha jenkins up
```

Expected: `Jenkins ready at http://127.0.0.1:18080 (user admin)` after about 30 seconds. Open
<http://127.0.0.1:18080> and sign in as **admin** / **j2gha-local-only**.

The controller is a throw-away container: configured as code, bound to localhost only, with the built-in node
carrying the `linux` label the pipeline asks for. `uv run j2gha jenkins down` deletes it with everything in it.

### 1.2 Create the two credentials the pipeline uses

Go to **Manage Jenkins → Credentials**, click the **Global** domain of the **System** store (or open
<http://127.0.0.1:18080/manage/credentials/store/system/domain/_/>) and use **Add Credentials** twice:

| Kind | Fields | ID |
|---|---|---|
| Username with password | Username `ci-uploader`, Password: anything, for example `s3cr3t-passw0rd` | `artifact-repo` |
| Secret text | Secret: anything, for example `dummy-deploy-token` | `inventory-deploy-token` |

The IDs must match exactly: the Jenkinsfile refers to them in `withCredentials` (Publish) and `credentials()` (Deploy).

### 1.3 Create the Pipeline job

1. **Dashboard → New Item**, name it `inventory-service`, choose **Pipeline**, click **OK**.
2. In the **Pipeline** section, leave **Definition** as *Pipeline script*, paste the whole content of
   [`examples/000/Jenkinsfile`](Jenkinsfile) into **Script**, keep **Use Groovy Sandbox** ticked, click **Save**.

### 1.4 Build #1: the default release

Click **Build Now**. The first build of a new job always uses the parameter defaults (`RELEASE_VERSION=1.4.0`,
`DEPLOY_ENV=staging`, `RUN_INTEGRATION_TESTS=true`) and registers the parameters for later builds.

Open the build (`#1`) and click **Pipeline Overview** to watch it run:

- `Prepare sources` and `Build` run first.
- `Quality` fans out into three parallel branches: `Unit tests`, `Lint` and `Integration tests`.
- `Compatibility` runs three matrix cells (`sqlite/text`, `memory/json`, `sqlite/json`). `memory/text` is excluded.
- `Publish` uploads the release.
- `Deploy` **stops and waits for approval**.

### 1.5 Approve the deployment

Open <http://127.0.0.1:18080/job/inventory-service/1/input/>. The waiting stage in **Pipeline Overview** also links
to it. You will see *Deploy this inventory-service release?* with a **CHANGE_TICKET** field. Enter `CHG-1234` and click
**Deploy**. The build finishes within seconds.

### 1.6 Check what build #1 produced

| Check | Where | Expected |
|---|---|---|
| Result | build page | `#1 1.4.0 to staging`, green. The display name was set by the `script {}` block. |
| Stages | **Pipeline Overview** | every stage green, including the 3 parallel branches and 3 matrix cells |
| Tests | **Tests** | **21 tests, 0 failures** in 5 suites: `tests.unit` (5), `tests.integration.sqlite` (1), and `tests.unit.memory.json`, `tests.unit.sqlite.json`, `tests.unit.sqlite.text` (5 each, one per matrix cell) |
| HTML report | **Unit test report** (sidebar) | `tests.unit: 5 tests, 0 failed` |
| Artifacts | **Build Artifacts** | `build/lint/reports/lint.txt`, `deploy/staging.json`, `dist/BUILD_INFO.txt`, `dist/inventory-service-1.4.0.tar.gz`, `dist/inventory-service-1.4.0.tar.gz.sha256` |
| Fingerprints | **See Fingerprints** | the three `dist/` files Publish archived with `fingerprint: true` |
| Log | **Console Output** | `Uploaded to repository/inventory-service/1.4.0 as ci-uploader (password: 15 characters)`, `Approved by admin`, `Deploying 1.4.0 to staging (deploy token is set)` and `inventory-service-1.4.0-b1 finished: SUCCESS` |

Now prove that the release artifact is sound, not just present:

```bash
cd "$(mktemp -d)"
J=http://127.0.0.1:18080/job/inventory-service/1/artifact
for f in dist/inventory-service-1.4.0.tar.gz dist/inventory-service-1.4.0.tar.gz.sha256 dist/BUILD_INFO.txt deploy/staging.json; do
  curl -fsSu admin:j2gha-local-only -O "$J/$f"
done
sha256sum -c inventory-service-1.4.0.tar.gz.sha256      # inventory-service-1.4.0.tar.gz: OK
cat BUILD_INFO.txt                                      # service=inventory-service, version=1.4.0, build=inventory-service-1.4.0-b1, python=...
python3 -m json.tool staging.json                       # "change": "CHG-1234", "approver": "admin"
tar -xzf inventory-service-1.4.0.tar.gz
REPORT_FORMAT=json PYTHONPATH=. python3 -m inventory.cli widget=2 gadget=1
# {"backend": "memory", "stock": {"gadget": 1, "widget": 2}, "version": "1.4.0"}
cd - >/dev/null
```

The deploy record carries the ticket you typed and your user ID (from `submitterParameter`). Remember this for
Part 6: those two values are the one thing GitHub Actions cannot reproduce.

### 1.7 Build #2: a snapshot that is neither tested against the package nor released

On the job page click **Build with Parameters** and set:

- `RELEASE_VERSION` = `1.5.0-SNAPSHOT`
- `DEPLOY_ENV` = `none`
- `RUN_INTEGRATION_TESTS` unticked

Click **Build**. Expected:

- **No approval prompt.** `beforeInput true` evaluates `when` *before* asking, so there is nothing to approve.
- In **Pipeline Overview**, `Integration tests`, `Publish` and `Deploy` are shown as skipped.
- **Console Output** shows `Snapshot build: the Publish stage will be skipped`, followed by
  `Stage "Integration tests" skipped due to when conditional`, and the same for `Publish` and `Deploy`.
- **Tests** shows 20 tests: no integration suite.
- **Build Artifacts** holds only `lint.txt`.
- The job page's **Stages** view shows both builds side by side.

You now know exactly what the pipeline should do under both sets of parameters. Everything below checks that the
converted workflow does the same.

---

## Part 2: Analyse

```bash
uv run j2gha analyze 000
```

Expected: `000: declarative      difficulty  23 (assisted), coverage 78.5%, convertibility automatic`.

The harness parsed the Jenkinsfile with the Groovy that ships inside Jenkins and had the controller validate it
(`pipeline-model-converter`). It then built an intermediate model and scored the migration. Open
[`RESULTS.md`](RESULTS.md) (created by this step) and read the **Analysis** section:

- **Stage graph:** the same graph you watched in Part 1, including the parallel branches, matrix axes and the
  `when`/`input` markers.
- **Step inventory:** every step and the GitHub Actions construct it will map to.
- **Findings:** what will need attention. Examples are `InputGate` (line 204), `GroovyWhenExpression` (the
  `when { expression }` conditions), `HashedCron` (`H 2 * * 1-5`) and `CredentialBinding` (both credentials).

Raw data: `examples/000/analysis/{analysis,ir,groovy-ast,jenkins-model}.json`.

## Part 3: Convert

```bash
uv run j2gha convert 000
```

Expected: `000: 9 job(s); mapped 41, approx 33, manual 1 -> automation 81.0%` (automation is an effort estimate, not a measure
of correctness).

Open [`gha/workflow.yml`](gha/workflow.yml). Jenkins stages share one workspace, but GitHub Actions jobs do not. The
converter plans jobs like this, and hands the workspace from job to job as a tar artifact (`j2gha-ws-<job>`: each job
restores the workspace of the jobs before it and uploads its own at the end):

| Jenkins | GitHub Actions job |
|---|---|
| `Prepare sources`, `Build` (same agent, sequential) | `prepare-sources` |
| `Quality` parallel branches | `quality-unit-tests`, `quality-lint`, `quality-integration-tests` (each `needs: prepare-sources`) |
| `Compatibility` matrix | `compatibility` with `strategy.matrix` and the same `exclude` |
| `Publish` | `publish` |
| `Deploy`'s `when` (`beforeInput true`) | `deploy-gate` ("Deploy (when)"): decides the condition once, before the protected environment, so a skipped `Deploy` asks for no approval |
| `Deploy` with `input` | `deploy` with `environment: Deploy` (add required reviewers to that environment) |
| pipeline `post` | `post` (`needs` every job, `if: always()`) |

Things worth finding in the YAML:

- **`when` becomes `if:`**:
  - `when { not { expression { params.RELEASE_VERSION.endsWith('-SNAPSHOT') } } }` becomes
    `if: '!(endsWith(env.RELEASE_VERSION, ''-SNAPSHOT''))'`.
  - The `script {}` `if`/`else` is decided once by a step that records the branch taken (`taken=true` or `false`);
    each branch's steps test that output.
- **`stash`/`unstash` become artifact upload/download.** Each `unstash` restores into its stage's `dir()`
  (`path: build/unit`) and keeps the stash's directory (`path: dist`), just as Jenkins does.
- **Parameters become `workflow_dispatch` inputs.** `H 2 * * 1-5` becomes a fixed `7 2 * * 1-5` schedule.
- **Credentials become secrets.** The three secrets the workflow needs (`ARTIFACT_REPO_USR`, `ARTIFACT_REPO_PSW`,
  `INVENTORY_DEPLOY_TOKEN`) are listed at the top of the migration report.

Then read [`gha/migration-report.md`](gha/migration-report.md). Every construct is listed with its line number and
a status:

- **mapped** (41)
- **approximated** (33): for example, the `input` gate becomes a protected environment, and its `CHANGE_TICKET`
  parameter and approver ID have no equivalent.
- **manual** (1): `currentBuild.displayName = ...` has no GitHub Actions counterpart.
- **dropped** (3): `post { unstable }`, `buildDiscarder`, `timestamps`.

The report ends with **Reference documentation**: the Jenkins and GitHub Actions pages for each construct, plus the
trap worth knowing first (e.g. `stash` artifacts lose file permissions), starting with the constructs needing the
most work.

## Part 4: Validate the converted workflow

```bash
uv run j2gha validate 000
```

Expected: `000: actionlint 0 (0 shellcheck), zizmor 0, policy 1 -> OK`.

- **actionlint** checks the workflow structure and runs shellcheck over every `run:` script.
- **zizmor** looks for security problems: injection, over-broad permissions, unpinned actions. Every action is
  pinned to a commit SHA.
- **The j2gha policy check** flags one warning (`unresolved-groovy`): the `post` job's `echo` still contains the
  placeholder `${J2GHA_TODO_currentBuild_currentResult}`, because the converter could not translate the Groovy runtime
  value `currentBuild.currentResult`. That is the converter telling you where a human is needed.

Details: `gha/validation.json`.

## Part 5: Differential run in trace mode (Jenkins vs act)

```bash
uv run j2gha run 000 --tier jenkins,act
```

Expected (about 1 minute):

```text
[jenkins] 000: provisioned: []
[jenkins] 000: runtime auto-repair [('stub-property', 'PYTHON_VERSION')]
[jenkins] 000: jenkins trace -> SUCCESS (41 trace events)
[act] running act (trace) in <repo>/examples/000/runs/act-trace/workspace
[act] act trace -> success (41 trace events, 11 job results) in <seconds>s
[run] 000: act vs jenkins (trace): EQUIVALENT (100.0% step similarity)
```

**What happened.** Trace mode replaces every side-effecting step on *both* sides with a marker line:

```text
J2GHA-TRACE {"stage":"Publish","step":"sh"}
```

Then it compares, stage by stage, the sequence of steps that actually ran. This tests control flow: stage graph,
`when` decisions, parallel and matrix fan-out, `post` conditions and the `script {}` translation. It is independent
of tools and credentials.

- **Jenkins side.** The harness "localised" the original Jenkinsfile: it stubbed steps, made the agent `any` and
  removed the trigger. It ran the result as job `ex-000-trace` on the same controller. Open that job's **Console
  Output** in the browser to see the markers.
  - Compare `examples/000/Jenkinsfile` with `runs/jenkins-trace/Jenkinsfile.localized`. The original lines are
    untouched and the stubs are appended at the end, so Jenkins error line numbers still match the original.
  - The `auto-repair` line is the harness fixing its own localisation. With `sh(returnStdout: true)` stubbed,
    `PYTHON_VERSION` came back empty and Jenkins reported a missing property. The harness read the error and
    stubbed the property, then re-ran.
- **GitHub Actions side.** The converted workflow ran under act. Its 11 jobs are the 9 jobs above, with the matrix
  job counting as 3 cells.

See the comparison per stage:

```bash
python3 -c "
import json
r = json.load(open('examples/000/runs/act-trace/result.json'))
for s in r['comparison']['stages']:
    print(f\"{s['status']:<9} {s['stage'] or '(pipeline environment)':<26} {s['jenkins']}\")"
```

Every stage, including `Declarative: Post Actions` and the matrix's `Contract tests` (three cells), shows `match`.
The **Execution** section of [`RESULTS.md`](RESULTS.md) has the same result as a table.

## Part 6: Full mode: run the real commands on both sides

```bash
uv run j2gha run 000 --tier jenkins,act --mode full
```

Expected (about 2 to 3 minutes):

```text
[jenkins] 000: provisioned: []
[jenkins] 000: jenkins full -> SUCCESS (0 trace events)
[act] running act (full) in <repo>/examples/000/runs/act-full/workspace
[act] act full -> success (0 trace events, 11 job results) in <seconds>s
[run] 000: act vs jenkins (full): EQUIVALENT (jenkins SUCCESS at None, act success at None)
```

Now nothing is stubbed except the approval, which the harness auto-approves on job `ex-000-full`. Both sides
generate the source, build the tarball and run the tests. On the GitHub Actions side that only works because files
reach the later jobs: through the pipeline's own stash/unstash, and through the workspace hand-off (`j2gha-ws-*`). Check that the GitHub Actions side built
the same release you verified in Part 1:

```bash
A=$PWD/examples/000/runs/act-full/artifacts/1
cd "$(mktemp -d)"
unzip -q "$A"/artifacts-41/*.zip -d release      # Publish: archiveArtifacts (the number changes per run)
unzip -q "$A"/artifacts-47/*.zip -d deploy       # Deploy: archiveArtifacts (the number changes per run)
(cd release/dist && sha256sum -c inventory-service-1.4.0.tar.gz.sha256 && cat BUILD_INFO.txt)
cat deploy/deploy/staging.json; echo
ls "$A"         # artifacts-*, html-report-*, j2gha-ws-* (workspace hand-off), stash-*, test-reports-* (one per matrix cell)
cd - >/dev/null
```

Expected (the `artifacts-<n>` numbers differ from run to run: run `ls "$A"` first and use the folders holding the
`.tar.gz` and `staging.json`; the files keep their Jenkins paths, `dist/` and `deploy/`):

- The checksum verifies and `BUILD_INFO.txt` has the same service, version and build label. The Python version
  differs because the runner image differs.
- `staging.json` shows `"change": "none", "approver": "unknown"`. This is the gap the migration report predicted in
  Part 3: a protected GitHub environment can gate the job but cannot collect a change ticket or pass the approver's
  name. Whoever migrates this pipeline has to decide what replaces them, for example a `workflow_dispatch` input
  plus `github.actor`.

## Part 7: Real GitHub Actions

### 7.1 Self-hosted runners (costs nothing)

```bash
uv run j2gha run 000 --tier selfhosted
```

Expected (about 2 to 3 minutes):

```text
[gha] pushed j2gha/run/000-trace-selfhosted-<timestamp> (<sha>) to <owner>/<repo>
[gha] run <id>: https://github.com/<owner>/<repo>/actions/runs/<id>
[gha] started JIT runner j2gha-<label>-1   ... up to -11
[gha] run <id> -> success (41 trace events, 0 billable min)
[run] 000: selfhosted vs jenkins (trace): EQUIVALENT (100.0% step similarity)
```

Open the run URL while it runs. GitHub draws the job graph of the converted workflow:
- the parallel `Quality` jobs
- the three `Compatibility` cells
- `Publish`, the `Deploy (when)` gate and `Deploy`
- the final `post` job

The jobs run on ephemeral just-in-time runners that the harness started as local Docker containers (`docker ps`
lists them as `j2gha-<label>-N`). Each runner takes one job and exits. When the run completes, the harness downloads
the logs, compares the traces and deletes the `j2gha/run/...` branch. The run itself stays in the repository's
**Actions** tab.

Optionally run the real commands on GitHub too, still at no cost:

```bash
uv run j2gha run 000 --tier selfhosted --mode full
```

Expected: `EQUIVALENT (jenkins SUCCESS at None, selfhosted success at None)`. The run log then lists 17 uploaded artifacts
(the numbers in the names change from run to run):
- `artifacts-<n>`: the release tarball, checksum and `BUILD_INFO.txt`
- `artifacts-<n>`: the deploy record
- one `test-reports-<n>-<backend>-<format>` per matrix cell
- the HTML report and the stashes
- six `j2gha-ws-<job>` workspace hand-offs

### 7.2 GitHub-hosted runners (spends Actions minutes)

Check your allowance first:

```bash
uv run j2gha budget
```

A trace run of this workflow has 11 jobs. Each job is billed as at least one minute, so expect about **11 billable
minutes** on a private repository. The guard plans for the worst case of 55 minutes (11 jobs × the 5-minute trace
timeout), which is above the default per-run cap of 30. Raise the cap for this run:

```bash
uv run j2gha run 000 --tier hosted --max-minutes 60
```

Answer `y` at the prompt. Add `--yes` to skip the prompt, which is needed when the command is not run in a
terminal.

If `uv run j2gha budget` reports `usage data: INCOMPLETE (lower bound)` (it does when GitHub's billing API is not
available to your token), the guard refuses to run. Either give your token billing access
(`gh auth refresh -h github.com -s user`), or, once you are satisfied the allowance is not at risk, set
`J2GHA_ALLOW_INCOMPLETE_USAGE=1` for that one command. Expected (the `WARNING` line appears only with the override):

```text
[budget] ALLOW: estimate {'typical': 11, 'worst_case': 55, 'unbounded': False}, <used>/<included> used this month, 0 reserved
[budget] reserved 55 min (<reservation>)
[gha] pushed j2gha/run/000-trace-hosted-<timestamp> (<sha>) to <owner>/<repo>
[gha] run <id>: https://github.com/<owner>/<repo>/actions/runs/<id>
[gha] run <id> -> success (41 trace events, 11 billable min)
[run] 000: hosted vs jenkins (trace): EQUIVALENT (100.0% step similarity)
```

The result also records the billable minutes (`11 billable min`). Run `uv run j2gha budget` again to see the run in the harness ledger.

## Part 8: Prove the harness catches a broken conversion

Sabotage the converted workflow so that `Deploy` runs only when `DEPLOY_ENV` *is* `none`, the opposite of the
Jenkinsfile. The run tiers execute `gha/workflow.model.json`. The harness refuses a model that was edited after
`j2gha convert` (its records would otherwise claim to measure the conversion), so a mutation test must ask for it
with `--edited-model`; such a record is marked, shown as stale and never counted:

```bash
sed -i "s/env.DEPLOY_ENV != 'none'/env.DEPLOY_ENV == 'none'/" examples/000/gha/workflow.model.json
uv run j2gha run 000 --tier act --edited-model
```

Without `--edited-model` the run stops with `the converted workflow is stale (the Jenkinsfile or
gha/workflow.model.json changed since j2gha convert)`.

Expected:

```text
[act] act trace -> success (37 trace events, 10 job results) in <seconds>s
[run] 000: act vs jenkins (trace): DIFFERS (90.2% step similarity)
[j2gha] not equivalent: 000 act (differs)
```

The **Execution** section of [`RESULTS.md`](RESULTS.md) pinpoints it:

```text
- `Deploy`: missing-stage - jenkins ['input', 'unstash', 'sh', 'archiveArtifacts'] vs act []
```

The workflow still ran "successfully", which is exactly the failure a plain "did it go green?" test would miss.
Restore the real conversion and confirm:

```bash
uv run j2gha convert 000
uv run j2gha run 000 --tier act      # act vs jenkins (trace): EQUIVALENT (100.0% step similarity)
```

## Where the results are

| What | Where |
|---|---|
| Every stage's results, as one page | [`examples/000/RESULTS.md`](RESULTS.md) (regenerated by each command) |
| Analysis data | `examples/000/analysis/` |
| Converted workflow, report, validation | `examples/000/gha/workflow.yml`, `migration-report.md`, `validation.json` |
| Per-tier run records and logs | `examples/000/runs/<tier>-<mode>/result.json`, plus `console.log` (Jenkins), `act.jsonl` (act), `logs.json` (GitHub) |
| Original and localised Jenkins runs | jobs `inventory-service`, `ex-000-trace` and `ex-000-full` on <http://127.0.0.1:18080> |
| GitHub runs | the repository's **Actions** tab, or `gh run list --limit 5`: runs are titled `j2gha selfhosted trace run of examples/000` and so on. All harness runs share one workflow file, so GitHub may list them under another example's workflow name. |

Example 000 is a walkthrough, not part of the corpus: `all` does not include it and `uv run j2gha summary` leaves it
out of `examples/README.md`. Name it explicitly (`000`) to run it.

## Reset

To put everything back for another run-through:

```bash
uv run j2gha jenkins down                   # deletes the controller: jobs, builds, credentials
git clean -ffdX examples/000                # deletes everything gitignored under examples/000 (-ff: act workspaces are git repos)
git status --short --ignored examples/000   # no '!!' (ignored) entries left
```

The Docker images and the act action cache are kept, so the next run starts quickly. GitHub runs stay in the
repository's **Actions** tab; delete them there or with `gh run delete <id>` if you want a clean history.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The job page shows **Build Now**, not **Build with Parameters** | Normal before the first build: the parameters are registered by build #1. |
| `Could not find credentials entry with ID 'artifact-repo'` | Step 1.2: the credential IDs must match exactly. |
| Port 18080 is already in use | `export J2GHA_JENKINS_PORT=18081` before `jenkins up` (and use that port in the URLs). |
| `REFUSE: ... exceeds the per-run cap` on the hosted tier | Expected without `--max-minutes 60`; see 7.2. |
| `non-interactive: pass --yes` | The hosted tier asks before spending minutes; add `--yes` when not in a terminal. |
| Self-hosted run fails to register runners | Your token needs admin rights on the repository (`gh auth status`); see the [prerequisites](../../docs/prerequisites.md). |
| A `j2gha run` hangs or behaves oddly | Only one `j2gha run` at a time may use the Jenkins controller: it holds shared state (global `BRANCH_NAME`). |
