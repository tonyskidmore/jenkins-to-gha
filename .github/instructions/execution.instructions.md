---
description: "Running the original on Jenkins and the conversion on act or GitHub, and comparing the runs (trace parity, localiser, provenance)"
applyTo: "j2gha/trace.py,j2gha/jenkins/**,j2gha/runners/**,j2gha/outputs.py,j2gha/provenance.py"
paths:
  - "j2gha/trace.py"
  - "j2gha/jenkins/**"
  - "j2gha/runners/**"
  - "j2gha/outputs.py"
  - "j2gha/provenance.py"
---
# Execute and compare

- **Trace parity:** a converted step is traced if and only if the Jenkins localiser traces it. Both sides share
  `TRACED_STEPS`, `STUBBED_WRAPPERS` and `SILENT_STUBS` in `j2gha/trace.py`; changing a stub on one side only breaks
  equivalence for every example.
- **`LOCALIZER_VERSION`** (`j2gha/jenkins/localize.py`): bump it when localisation changes what a run records.
  `tests/test_localizer_version.py` fails when the localised fixtures change without a bump; after bumping, record
  the new fingerprint with `uv run python tests/test_localizer_version.py`.
- **Jenkins side:** `j2gha/jenkins/localize.py` rewrites by AST source ranges and *appends* step-shadowing methods.
- **Line numbers:** Jenkins error lines must match the original Jenkinsfile (the `quote-env` repair is keyed on them).
  The localisation block goes at the *end* of the script, and `SourceEditor.apply` pads each edit to the line count it
  replaces and raises on an edit that adds lines.
- **Jenkins semantics the GHA trace mirrors:**
  - stage names `Declarative: Checkout SCM` and `Declarative: Post Actions`;
  - a stage `input` is evaluated *before* `when` (unless `beforeInput`);
  - pipeline/stage `environment { X = sh(...) }` emits an `sh` event;
  - matrix GString stage names are shell-expanded per cell;
  - the map returned by `checkout` is copied into `env`.
- **GHA side:** `j2gha/runners/variants.py` derives the trace/full x act/selfhosted/hosted variants. Variants pin
  `JOB_NAME` to the Jenkins job (`jenkins.run.harness_job`) and `BUILD_NUMBER`/`BUILD_ID` to its build, and give
  upper-case properties the localiser stubbed its `j2gha-stub` value (`variants.stubbed_properties`). A reference that
  ran with `docker` stubbed makes full variants run the Docker steps on the runner too
  (`variants.reference_had_docker`).
- **Comparison:** both sides print `J2GHA-TRACE {"stage","step"}`, compared per stage by `trace.compare`.
  - Order counts except in `trace.concurrent_stages` (matrix, scripted `parallel`, multi-job stages); order *between*
    stages is the Jenkinsfile's partial order (`trace.stage_order`).
  - A model edited after `convert` is refused unless `run --edited-model` (mutation tests; never counted).
  - Empty traces, differing results behind matching traces and unusable references are *inconclusive*, never
    equivalent.
- **Full mode** also compares outputs (`j2gha/outputs.py`): JUnit cases (with status) and the set of archived files,
  identified by their Jenkins archive path (archive steps record `_j2gha.root`; full variants add
  `outputs.ROOT_MARKER`). Content hashes are shown, not counted. A Jenkins full reference without `outputs` is not used.
  Outputs compare `BUILD_TAG` path segments as a placeholder.
- **Provenance** (`j2gha/provenance.py`): AST, analysis and conversion carry the Jenkinsfile sha256 (and model hash);
  run records add scenario, `LOCALIZER_VERSION` and images. Stale prerequisites are re-done (convert) or refused
  (localiser, GHA tiers); stale run records show as stale and are not counted.
- **No operator credentials in runs:** execution variants replace every `secrets.*` with the `FAKE_*` values of the
  Jenkins fake credentials, keep only allowlisted container options (`variants.py`), and act gets no token (full mode
  fetches the public source on the host). Credential ids never map to reserved `GITHUB_*` secret names. The one
  exception is the harness's own random `J2GHA_ENV_CANARY` (`run --environments`), added after the faking.
- **Jenkins controller:**
  - scripts are non-sandboxed and pre-approved via the script console;
  - job XML must be posted ASCII-escaped (`xmlcharrefreplace`);
  - parameterised jobs reject `/build`;
  - `tools {}` names are provisioned per pipeline (`localize.tool_installs`) by `analyze` and full-mode `run`;
  - it is shared state (global env `BRANCH_NAME`/`GIT_BRANCH`): `controller.exclusive` (`.j2gha/jenkins.lock`) makes
    a second harness process fail fast.
- **act:** job containers get no Docker socket (`--container-daemon-socket -`).
- `j2gha/runners/*` and `j2gha/provenance.py` are protected for rule-improvement changes; `trace.py` and
  `localize.py` only allow their listed assignments to change (`evals/protected.txt`).

Reference: [docs/mechanism.md](../../docs/mechanism.md), [docs/architecture.md](../../docs/architecture.md).
