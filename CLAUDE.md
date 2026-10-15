# CLAUDE.md

## What this is

`j2gha`: a Jenkins → GitHub Actions analysis, conversion and differential-validation harness run over a corpus of
real-world Jenkinsfiles in `examples/NNN/`. It is a prototype (proof of concept), not a production migration tool or
reference: report results as what the runs showed (an *equivalent* verdict means no difference was found), never as
proof that a conversion is correct.

- **Using it:** `docs/prerequisites.md`, `docs/usage.md`; results: `docs/results.md`.
- **Own (private) pipelines:** `docs/own-pipelines.md`. It covers `J2GHA_PIPELINES_DIR` and `j2gha add`, what leaves
  the machine, reading results, and shared libraries. Difficulty score: `docs/scoring.md`.
- **Design:** `docs/mechanism.md`, `docs/architecture.md`.
- **Reference-docs subsystem:** `docs/documentation.md`.
- **Adding or changing a conversion rule:** `docs/extending.md`; agent-assisted: `docs/self-improvement.md`.
- **AI and agents:** `docs/AI.md` (what needs an agent, how the repo was built), `docs/skills.md`; GitHub Copilot
  (which also reads this file and `.claude/skills/`): `docs/copilot.md`.
- **Videos:** `docs/walkthrough-videos.md`; sources in `docs/video/`.
- **README.md stays short** (what it is, getting started, links): detail goes in the relevant `docs/` page, not the README.
- **Maintain CHANGELOG.md.** Every user-visible change adds its entry under `## [Unreleased]` (Added / Changed /
  Fixed / Removed) in the same commit or pull request.
  - User-visible means a command, option, environment variable, behaviour, output or doc a user follows.
  - A new feature's entry says how to use it: a command or two.
  - Internal refactors and test-only changes need no entry.
  - A release moves `[Unreleased]` under `## [X.Y.Z] - date`, bumps `version` in `pyproject.toml`, tags `main`
    `vX.Y.Z` and updates the compare links at the bottom. `v0.1.0` is the initial proof of concept.

## Commands

```bash
uv sync                                            # deps
uv run --group dev pytest -q                       # unit tests (no Docker needed)
uv run --group dev pytest -q -m e2e tests/test_walkthrough.py   # example 000, both scenarios, Jenkins vs act (~4 min, Docker)
J2GHA_E2E_TIERS=act,selfhosted uv run --group dev pytest -m e2e tests/test_handoff_e2e.py   # hand-off/identity e2e, also on real GHA
uv run --group dev pytest tests/test_convert.py::test_workflow_shape -q   # single test
uvx ruff check j2gha tests --select F,E9,B --ignore B008                  # lint

uv run j2gha docker build [--only jenkins|act|act-runner|runner]   # harness images (runner images carry the Jenkins toolchain)
uv run j2gha crawl --count N [--dry-run]           # add N scored examples (needs gh auth + j2gha/jenkins:local)
uv run j2gha add PATH [--name N] [--force]         # own pipeline (any file name) -> $J2GHA_PIPELINES_DIR/N/Jenkinsfile
uv run j2gha analyze|convert|validate [ids|all]    # ids: 003, 1-5, "004 009", names; all (default) = corpus, or
                                                   # every pipeline in J2GHA_PIPELINES_DIR (--pipelines-dir) when set
J2GHA_OFFLINE=1 uv run j2gha pipeline <ids>        # or --offline: no GitHub API calls (cache only), no source/docs fetch
uv run j2gha run <ids> --tier jenkins,act [--mode trace|full] [--branch B] [--param NAME=VALUE ...] [--edited-model] [--fail-on-differs]
uv run j2gha run <ids> --tier selfhosted           # real GitHub Actions via local JIT runners, 0 minutes (prefer this)
uv run j2gha run <ids> --tier selfhosted --environments   # also enter j2gha-* environments + canary secret check
uv run j2gha environments [list|clean]             # the harness repo's j2gha-* environments (clean deletes them)
uv run j2gha run <ids> --tier hosted --yes --max-minutes N   # spends account minutes: user approval + `j2gha budget` first
uv run j2gha pipeline <ids> [--continue-on-invalid]   # analyze -> convert -> validate -> run (jenkins,act)
uv run j2gha gaps [--unmapped-only] | scoreboard [--check] [--strict] | guard [--base main]   # rule-improvement worklist, baseline compare, protected-file check
uv run j2gha summary                               # regenerate examples/README.md ($J2GHA_PIPELINES_DIR/README.md when set)
uv run j2gha budget [--clear ID...]                # minutes used/remaining for the harness repo's owner, reservations
uv run j2gha jenkins up|down|status                # disposable controller on 127.0.0.1:18080 (admin / j2gha-local-only)
uv run j2gha docs fetch [jenkins|gha] [--version fpt|ghec|ghes-X.Y] [--label L] [--parts P]   # -> .docs/ (gitignored)
uv run j2gha docs status|path <src>|use <src> <ver>|xref <step...>     # select bundles, Jenkins->GHA crosswalk
```

Skills in `.claude/skills/` (optional: the CLI needs no AI agent, see `docs/AI.md`):

- `jenkins-example-crawler` and `jenkins-to-gha` wrap the harness commands.
- `jenkins-example-twin` makes an example run to completion as a twin (`examples/1NN`, edits listed in `LOCAL.md`;
  the cited `examples/0NN/Jenkinsfile` is never edited; crawled ids stay below 100).
- `j2gha-rule-improver` proposes one conversion-rule change per branch (propose-only; never edits `evals/` or the oracle).
- `jenkins-docs` and `gha-docs` read the local doc bundles first and fall back to the web.
- `narrated-explainer` and `hyperframes-walkthrough` make videos; the latter films live Jenkins/GHA runs (GitHub capture
  needs per-run approval) and publishes videos as GitHub release assets (`hfw publish`, never git).
- All of them are described in `docs/skills.md`.

## Architecture

Each stage writes artifacts into the example directory and owns a marker-delimited README section
(`<!-- j2gha:<section>:start/end -->`, `readme.update_section`), so every stage is idempotent and re-runnable on
its own.

1. **Parse** (`analysis/ast.py`, `docker/jenkins/groovy/ast_dump.groovy`)
   - Uses the Groovy 2.4.21 CONVERSION-phase AST from the jar inside `jenkins.war`, so parsing matches Jenkins.
   - `dump_sources()` mounts the repo's dumper over the image copy, so dumper edits need no image rebuild.
2. **IR** (`ir.py`, `analysis/declarative.py`)
   - Declarative is interpreted directive by directive; scripted gets a best-effort model.
   - Elements keep their `line`.
   - Helper methods are kept in `Pipeline.method_defs` for inlining.
3. **Assess** (`analysis/analyze.py`, `rules/steps.yaml` step catalog)
   - Produces findings, hard gates, weighted coverage and a 0-100 difficulty score.
   - Jenkins' `/pipeline-model-converter/toJson` is only a validity cross-check: it has no line numbers, drops
     `@Library` and truncates one-line `script{}` blocks.
4. **Generate** (`convert/generator.py`, `convert/expressions.py`)
   - Job planning: consecutive stages sharing an agent (object, for scripted `node {}`) → one job; parallel, matrix,
     own-agent and input stages → separate jobs. A parallel/matrix stage's `input` → approval job before the fan-out,
     its `post` → fan-in job after it; its `when`/`environment`/`options` wrap every branch/cell.
   - Workspace hand-off: jobs on the pipeline agent pass the workspace on as `j2gha-ws-<job>` tar artifacts
     (`_workspace_handoff` picks the jobs, `convert/workspace.py` plans and generates; `J2GHA_WORKSPACE_HANDOFF=0`
     disables). Concurrent branches hand on their own change list too; a merge replays later branches' changes onto
     the first branch's snapshot (a changed file takes its whole hard-link group along). Matrix cells hand on only
     their changes (`j2gha-ws-<job>.<cell>`, a *delta* producer), replayed in cell-name order onto the workspace
     the matrix started from (a matrix starting from the checkout is not handed on: reported). The merge accounts for the
     fallback chain it uses: a job that ran but whose workspace did not arrive fails it; a job whose result is not
     visible (not a direct need) is taken as skipped, with a warning. The migration report's *Workspace hand-off* section states
     the runtime requirements. Conversion-only steps (`role: handoff`): no trace events. Tests that check job
     structure run with it off (`no_workspace_handoff` fixture); `tests/handoff_sim.py` runs the generated steps
     against Jenkins' one workspace (`tests/test_handoff_model.py`).
   - Conditions: a stage's `when` is evaluated once by a *stage-entry* step (`echo run=true >> $GITHUB_OUTPUT`,
     kind `stage-entry`, kept in trace variants via `trace_run`); the stage's steps test its output and stage `post`
     anchors on it.
   - Untranslatable conditions → `vars.J2GHA_WHEN_L<line>`, polarity-aware: `== 'true'` used positively,
     `!= 'false'` under an odd number of `not`s, so an unset variable never widens the stage.
   - Groovy assignments: plain string values and captured `sh` output go to `$GITHUB_ENV` and step outputs
     (`_carry_assignment`); container images resolve top-level constants (`Pipeline.constants`, `_fixed_value`).
   - Metadata: per-step `_j2gha` metadata is stripped from `workflow.yml` and kept in `gha/workflow.model.json`.
5. **Validate** (`validate/static.py`)
   - actionlint, with structural and shellcheck findings kept separate.
   - zizmor and the policy checks.
6. **Execute and compare** (`jenkins/`, `runners/`, `gha/`, `trace.py`)
   - Jenkins side: `jenkins/localize.py` rewrites by AST source ranges and *appends* step-shadowing methods.
   - GHA side: `runners/variants.py` derives the trace/full × act/selfhosted/hosted variants.
   - Comparison: both sides print `J2GHA-TRACE {"stage","step"}`, compared per stage by `trace.compare`; order counts
     except in `trace.concurrent_stages` (matrix, scripted `parallel`, multi-job stages); order *between* stages is
     the Jenkinsfile's partial order (`trace.stage_order`). A model edited after `convert` is refused unless
     `run --edited-model` (mutation tests; such records are never counted). Empty traces, differing
     results behind matching traces and unusable references are *inconclusive*, never equivalent.
   - Full mode also compares outputs (`outputs.py`): JUnit cases (with status) and the set of archived files,
     identified by their Jenkins archive path (archive steps record `_j2gha.root`; full variants add
     `outputs.ROOT_MARKER` so upload-artifact keeps those paths); content hashes are shown, not counted. A Jenkins
     full reference without `outputs` is not used.
   - Provenance (`provenance.py`): AST/analysis/conversion carry the Jenkinsfile sha256 (and model hash); run records
     carry them plus scenario, `LOCALIZER_VERSION` and images. Stale prerequisites are re-done (convert) or refused
     (localiser, GHA tiers); stale run records show ⏸️ and are not counted.
   - Variants pin `JOB_NAME` to the Jenkins job (`jenkins.run.harness_job`) and `BUILD_NUMBER`/`BUILD_ID` to its build,
     and give upper-case properties the localiser stubbed its `j2gha-stub` value (`variants.stubbed_properties`);
     outputs compare `BUILD_TAG` path segments as a placeholder. A reference that ran with `docker` stubbed makes full
     variants run the Docker steps on the runner too (`variants.reference_had_docker`).
   - Remote runs: orphan `j2gha/run/...` branches created through the Git Data API and deleted afterwards.
     `--environments` creates `j2gha-<name>` environments (no required reviewers) with a random canary secret
     via `gh secret set`, and compares deployments with the inputs Jenkins reached (`approved_inputs`).
   - Hosted runs: gated by `gha/budget.guard` (target repo owner's billing, refuses incomplete usage, ledger
     reservations under a lock; interrupted runs are cancelled and stay pending).

## Invariants and gotchas

- **Trace parity:** a converted step is traced iff the Jenkins localiser traces it. Both sides share `TRACED_STEPS`,
  `STUBBED_WRAPPERS` and `SILENT_STUBS` in `trace.py`. Changing a stub on one side only breaks equivalence for every
  example. Bump `LOCALIZER_VERSION` (`jenkins/localize.py`) when localisation changes what a run records;
  `tests/test_localizer_version.py` fails when the localised fixtures change without a bump (record the new
  fingerprint with `uv run python tests/test_localizer_version.py` after bumping).
- **No operator credentials in runs:** execution variants replace every `secrets.*` with the `FAKE_*` values of the
  Jenkins fake credentials (`jenkins/localize.py`), keep only allowlisted container options (`runners/variants.py`), and act gets no token
  (full mode fetches the public source on the host). Credential ids never map to reserved `GITHUB_*` secret names.
  The one exception is the harness's own random `J2GHA_ENV_CANARY` (`run --environments`), added after the faking.
  Remote (selfhosted/hosted) jobs still get GitHub's automatic `GITHUB_TOKEN`; don't describe runs as credential-free.
- **Corpus licences:** each crawled example carries `LICENSE.upstream` (and `NOTICE.upstream` where the source has
  one), listed in `THIRD-PARTY-NOTICES.md`. The crawler does not write these yet: add them, and the table row, by hand
  for a new example. AGPL sources were dropped from the corpus (old 021/121, 2026-10-11) and the crawler does not
  exclude copyleft licences, so check a new example's licence with the user before keeping it.
- **Jenkins semantics the GHA trace mirrors:**
  - Stage names `Declarative: Checkout SCM` and `Declarative: Post Actions`.
  - A stage `input` is evaluated *before* `when` (unless `beforeInput`).
  - Pipeline/stage `environment { X = sh(...) }` emits an `sh` event.
  - Matrix GString stage names are shell-expanded per cell.
  - The map returned by `checkout` is copied into `env`.
- **Line numbers:** Jenkins error lines must match the original Jenkinsfile (the `quote-env` repair is keyed on them).
  The localisation block goes at the *end* of the script, and `SourceEditor.apply` pads each edit to the line count it
  replaces and raises on an edit that adds lines.
- **Groovy 2.4 quirks:**
  - GString end columns run to end of line; `ast._cut_gstring` fixes this.
  - `a + b` string concatenation becomes `{"t":"concat"}`.
  - `stage('a'){..} stage('b'){..}` on one line is a command chain (`ast.unchain`).
  - Calls inside another call's *arguments* are DSL symbols, not steps (`CallCtx.in_args`).
- **Jenkins controller:**
  - Scripts are non-sandboxed and pre-approved via the script console.
  - Job XML must be posted ASCII-escaped (`xmlcharrefreplace`).
  - Parameterised jobs reject `/build`.
  - `toJson`/`validate` reject a Declarative agent/option/trigger/parameter type whose plugin is missing (a false
    `JenkinsValidationFailed` finding): add the plugin to `docker/jenkins/plugins.txt`. `tools {}` names are
    provisioned per pipeline (`localize.tool_installs`) by `analyze` and full-mode `run`.
  - It is shared state (global env `BRANCH_NAME`/`GIT_BRANCH`): `controller.exclusive` (`.j2gha/jenkins.lock`)
    makes a second harness process fail fast.
  - Image pins: base images are digest-pinned in `docker/*/Dockerfile` (the Jenkins base also in
    `config.JENKINS_BASE_IMAGE`; change both). Every plugin in `docker/jenkins/plugins.txt` is `name:version`; to add
    one, add the bare name, run `j2gha docker build --only jenkins`, and paste the `+ name:version` lines the
    `j2gha-check-plugins` step prints.
- **act:** only `@v4` artifact actions work (v6+ break under act 0.2.89). Job containers get no Docker socket
  (`--container-daemon-socket -`).
- **Test fixtures:** tests use committed AST fixtures (`tests/fixtures/*.ast.json`). After changing the dumper, run
  `uv run python tests/test_fixtures.py` (regenerates every fixture and `DUMPER.sha256`; CI checks the hash, the
  `docker`-marked test re-dumps locally).
- **Walkthrough example:** `examples/000` is a hand-written tutorial (only `README.md` and `Jenkinsfile` are tracked).
  Its README carries `<!-- j2gha:walkthrough -->`, so stages write their sections to a gitignored `RESULTS.md` and
  `all`/`summary`/the crawler skip it. Re-run it end to end after generator or localiser changes.
- **Evals (`evals/`):** `holdout.txt`, `protected.txt` and `baseline.json` are human-owned. Only a human runs `scoreboard --write`.
- **Generated, not hand-edited:**
  - Examples' `analysis/`, `gha/` and `runs/` are generated.
  - These are gitignored: `runs/**/workspace/`, `runs/*/artifacts/` (act's artifact store, up to ~110 MB a run),
    `.j2gha/`, `.docs/`, and `.cache/` (GitHub API GET cache: 24 h, 7 days for action SHA lookups; video work in
    `.cache/video/`, several GB).
- **Reference docs:**
  - Bundles are fetched into `.docs/` or `$J2GHA_DOCS_DIR` and never committed. Labels are validated (never a
    path); a fetch builds in a staging dir and swaps it in, so a failure keeps the old bundle; `--parts` merges.
  - Jenkins bundles are labelled `<core>+p<plugin-set digest>`.
  - The harness never reads them. The migration report's Reference section uses `xref.web_refs()` (web URLs only,
    fixed to GitHub.com), so committed reports don't depend on what is downloaded.
  - docs.github.com 429s on bursts, so the fetcher is sequential and caches raw pages in `.docs/.src/`.
  - Every GHA page named in `rules/docs-xref.yaml` must exist in `tests/fixtures/gha-pagelist-fpt.txt`. Refresh
    that snapshot when GitHub reorganises its docs.
