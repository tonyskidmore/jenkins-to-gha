# Research notes (October 2026)

Four parallel research agents explored the project's starting ideas (see [mechanism.md](mechanism.md)). Key findings and the decisions they
drove are below. Dates and versions were checked on 2026-10-03.

## 1. Jenkins: AST extraction and containerised execution

| Topic | Finding | Decision |
|---|---|---|
| `pipeline-model-converter` endpoints | `validate`, `validateJenkinsfile`, `toJson`, `toJenkinsfile`, `stepsToJson`, ... still exist (plugin 2.2293.v6e7193cec599, Aug 2026). POST, form field `jenkinsfile`, no CSRF crumb needed (crumb exclusion). Errors come back as `{"status":"ok","data":{"result":"failure",...}}`. | Used for authoritative validation + Declarative model. |
| `toJson` caveats | No line numbers. `@Library` dropped. One-line `script { a; b }` truncated. Validation depends on installed plugins. Scripted pipelines are rejected. | IR built from the Groovy AST; Jenkins' model is used as a cross-check. |
| Jenkins image | `jenkins/jenkins:2.580.1-lts-jdk21` (2026-09-30). LTS ≥ 2.555.1 requires Java 21/25. `jenkins-plugin-cli` 2.15.0. | `docker/jenkins/Dockerfile` + `plugins.txt` + JCasC. |
| Job execution | `createItem` (`CpsFlowDefinition`) → `build`/`buildWithParameters` → queue item → poll → `consoleText` + `wfapi/describe`. Parameterised jobs reject `/build`. Declarative registers parameters on the first build. | `j2gha/jenkins/controller.py`. |
| Script approval | Non-sandboxed scripts created over REST are *not* auto-approved. | Pre-approve through `ScriptApproval.preapprove` on the disposable controller. |
| jenkinsfile-runner | Last release 1.0-beta-32 (2023-11). master was revived mid-2026 but nothing has been released. | Not used. A JCasC controller is more reliable. |
| tree-sitter Groovy | `murtaza64/tree-sitter-groovy` is best (not on PyPI). `tree-sitter-language-pack` bundles a weak grammar (tested: errors on `def`/`return`). | Not used. Jenkins' own Groovy 2.4 jar via `ast_dump.groovy`. |
| jdp (Rust) | Dead (2020). | Not used. |
| JenkinsPipelineUnit | v1.31 (2026-07), mocked call stacks, no Declarative fidelity. | Future option for scripted pipelines. Trace mode covers the need. |
| jenkinsfilelint | Python pre-commit hook (v1.5.1) wrapping `/validate`, with an optional local server image. | Same endpoint. Hook recommended for source repos. |

## 2. Conversion landscape and semantics

- **GitHub Actions Importer:** still shipping its container image (`ghcr.io/actions-importer/cli` 1.3.22671,
  2026-07). The CLI wrapper has been unchanged since 2024. `--source-file-path` still needs a live Jenkins, because it
  calls `toJson`. It marks `matrix`, `input`, `options` and `parameters` unsupported and scripted pipelines manual.
  A dry-run against the harness controller was trialled and not adopted - see
  [section 5](#5-github-actions-importer-trial).
- **No mature open-source converter exists.** GitHub's `actions-migrations-via-copilot` (Copilot agents with
  Jenkins skills, actively developed through Sept 2026) is the closest, with actionlint-only validation and some
  lossy mappings.
- **Academic work** (CIMig, CIgrate, Wang et al. 2025) evaluates Travis→GHA with YAML validity, similarity and
  *build success rate*, classifying failures as logic 38%, platform 32%, environment 25%, syntax 5%. j2gha's trace
  equivalence adds a control-flow oracle that those studies lack.
- **Semantic traps baked into the generator:**
  - `env` is not available in job-level `if:`.
  - GHA `==` is case-insensitive.
  - Stage→job mapping loses the workspace.
  - Job containers run as root.
  - Cron has no `H`, runs on the default branch only, with a 5-minute minimum interval.
  - `workflow_dispatch` inputs are empty on push events.
  - Artifacts lose file permissions.
  - `upstream` maps to `workflow_run`, not `needs`.
  - `notValues` must be expanded explicitly.
  - Post `unstable`/`changed`/`fixed`/`regression` have no equivalent.
- **New 2026 syntax:** step-level `parallel:`/`background:` (June 2026) and concurrency `queue: max`. Not emitted
  yet, because actionlint 1.7.12 and act 0.2.89 don't understand them.

## 3. Local GHA execution: act and alternatives

See [act-evaluation.md](act-evaluation.md). In short:
- act v0.2.89 is in maintenance mode (security fixes only) but fine for fast local smoke tests with
  `upload-artifact@v4` and pinned runner images.
- Ephemeral JIT self-hosted runners give real GitHub orchestration for free.
- wrkflw, Local CI, Gitea/Forgejo runners and Dagger were assessed and not adopted.

Static tooling: actionlint 1.7.12 (bundles shellcheck/pyflakes), zizmor 1.30.1 (`--offline`, exit codes 11-14),
and the SchemaStore workflow schema (via check-jsonschema).

## 4. GitHub Actions minutes monitoring

- `GET /users/{u}/settings/billing/actions` was **retired** (changelog 2025-09-26). The per-run `/timing` endpoint
  responds but reports 0 billable ms.
- Replacement: `GET /users/{u}/settings/billing/usage/summary?year&month&product=actions` (enhanced billing,
  API version up to 2026-03-10). It needs the classic **`user`** scope and returns **404, not 403**, without it
  (`X-Accepted-OAuth-Scopes: user`).
- Plans: Free 2,000 min/month, Pro 3,000. Public repos and self-hosted runners are free. The self-hosted
  $0.002/min fee announced for 2026 was postponed. Each job is rounded up to a whole minute. Hosted prices were
  cut ~39% on 2026-01-01.
- j2gha uses the billing API when the scope is present. Otherwise it tallies job minutes from the jobs API across
  all owned private repos (a lower bound), plus a local ledger of harness runs. The guard keeps a 20% reserve and
  a per-run cap.

## 5. GitHub Actions Importer trial

The research conversation that started the project proposed the Importer as the baseline comparator. The initial build set it aside because it
needs a live Jenkins, but the harness controller already provides one, so it was trialled on 2026-10-03 against the
15-example corpus.

It runs locally with no `gh` extension and no hosted minutes:

```bash
docker run --rm --network container:j2gha-jenkins -e DISABLE_TELEMETRY=1 \
  -e GITHUB_ACCESS_TOKEN=dummy -e JENKINS_INSTANCE_URL=http://localhost:8080 \
  -e JENKINS_USERNAME=admin -e JENKINS_ACCESS_TOKEN=j2gha-local-only -v "$PWD":/data \
  ghcr.io/actions-importer/cli:latest dry-run jenkins --output-dir /data/out \
  --source-url http://localhost:8080/job/any/ --source-file-path /data/Jenkinsfile
```

- With `--source-file-path` it only POSTs the file to `toJson`. The `--source-url` job does not need to exist.
- The GitHub token is only used to identify the user for telemetry, so a dummy value works for `dry-run`.
- Without `DISABLE_TELEMETRY=1` the process spins at ~95% CPU after "Sending telemetry" and never exits.

| Outcome | Examples |
|---|---|
| Converted | 001, 006, 009, 014 |
| Rejected: scripted pipeline | 002, 008, 010 |
| Rejected by `toJson`: plugin or tool installation missing on the controller (since fixed, below) | 003, 004, 005, 007, 013, 015 |
| Rejected by `toJson`: invalid Jenkinsfile | 011, 012 |

The 4 converted workflows (001, 006, 009, 014) compared with j2gha's:

| | Importer | j2gha |
|---|---|---|
| actionlint structural errors | 3 of 4 fail | 4 of 4 clean |
| j2gha policy checks | 4 of 4 fail (unpinned actions, no permissions, no timeouts) | 4 of 4 pass |
| zizmor findings | 18, 33, 0, 10 | 3, 0, 0, 0 |
| `matrix` stages | dropped without a placeholder (009, 014) | converted; trace-equivalent under act |

Its output also cannot be trace-compared, because it carries no per-step mapping back to the Jenkins steps.

**Decision:** not added as a harness stage. It converts too little of the corpus to be a useful baseline, and it
is closed-source and in maintenance mode. The trial did show that the controller lacked the plugins
(`kubernetes`, `gitlab-plugin`, `generic-webhook-trigger`, `validating-string-parameter`) and tool installations
that Declarative validation needs. The plugins are now in `docker/jenkins/plugins.txt` and `analyze` provisions the
`tools {}` installations before calling `toJson`, so j2gha's own cross-check now also covers 003, 004, 005, 007,
013 and 015.

## Sources (selection)

- pipeline-model-definition `ModelConverterAction.java`: https://github.com/jenkinsci/pipeline-model-definition-plugin
- Jenkins changelog (LTS): https://www.jenkins.io/changelog-stable/ ; jenkinsfilelint: https://www.jenkins.io/blog/2026/06/08/jenkinsfilelint-pre-commit/
- jenkinsfile-runner: https://github.com/jenkinsci/jenkinsfile-runner ; JenkinsPipelineUnit: https://github.com/jenkinsci/JenkinsPipelineUnit
- GitHub Actions Importer: https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/automated-migrations/jenkins-migration
- Manual Jenkins migration guide: https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins
- Copilot migrations: https://github.com/github/actions-migrations-via-copilot ; Slack Engineering migration write-up (2024-12-16)
- Papers: arXiv 2407.02644 (CIMig), 2507.20402 (CIgrate), 2511.01316 (Wang et al.)
- nektos/act: https://github.com/nektos/act ; https://nektosact.com/not_supported.html
- Self-hosted runner version enforcement: https://github.blog/changelog/2026-06-12-github-actions-minimum-version-enforcement-timeline-for-self-hosted-runners/
- Billing: https://docs.github.com/en/rest/billing/usage ; https://github.blog/changelog/2025-09-26-product-specific-billing-apis-are-closing-down
- Pricing: https://docs.github.com/en/billing/reference/actions-runner-pricing ; https://github.com/resources/insights/2026-pricing-changes-for-github-actions
