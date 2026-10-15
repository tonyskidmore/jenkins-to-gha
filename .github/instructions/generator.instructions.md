---
description: "Generating the GitHub Actions workflow: job planning, workspace hand-off, conditions, assignments, metadata"
applyTo: "j2gha/convert/**"
paths:
  - "j2gha/convert/**"
---
# Generate

- **Job planning:** consecutive stages sharing an agent (object, for scripted `node {}`) become one job; parallel,
  matrix, own-agent and input stages become separate jobs. A parallel/matrix stage's `input` becomes an approval job
  before the fan-out, its `post` a fan-in job after it; its `when`/`environment`/`options` wrap every branch/cell.
- **Workspace hand-off:**
  - Jobs on the pipeline agent pass the workspace on as `j2gha-ws-<job>` tar artifacts. `_workspace_handoff` picks
    the jobs and `j2gha/convert/workspace.py` plans and generates; `J2GHA_WORKSPACE_HANDOFF=0` disables it.
  - Concurrent branches hand on their own change list too. A merge replays later branches' changes onto the first
    branch's snapshot (a changed file takes its whole hard-link group along).
  - Matrix cells hand on only their changes (`j2gha-ws-<job>.<cell>`, a *delta* producer), replayed in cell-name order
    onto the workspace the matrix started from. A matrix starting from the checkout is not handed on (reported).
  - The merge accounts for the fallback chain it uses: a job that ran but whose workspace did not arrive fails it; a
    job whose result is not visible (not a direct need) is taken as skipped, with a warning.
  - The migration report's *Workspace hand-off* section states the runtime requirements. Conversion-only steps
    (`role: handoff`) emit no trace events.
- **Conditions:** a stage's `when` is evaluated once by a *stage-entry* step (`echo run=true >> $GITHUB_OUTPUT`, kind
  `stage-entry`, kept in trace variants via `trace_run`). The stage's steps test its output and stage `post` anchors
  on it.
- **Untranslatable conditions** become `vars.J2GHA_WHEN_L<line>`, polarity-aware: `== 'true'` used positively,
  `!= 'false'` under an odd number of `not`s, so an unset variable never widens the stage.
- **Groovy assignments:** plain string values and captured `sh` output go to `$GITHUB_ENV` and step outputs
  (`_carry_assignment`); container images resolve top-level constants (`Pipeline.constants`, `_fixed_value`).
- **Metadata:** per-step `_j2gha` metadata is stripped from `workflow.yml` and kept in `gha/workflow.model.json`.
- **Trace parity:** a converted step is traced if and only if the Jenkins localiser traces it (`TRACED_STEPS` and
  friends in `j2gha/trace.py`; see the execution rules).
- **act:** only `@v4` artifact actions work (v6+ break under act 0.2.89).
- **After generator changes,** re-run the walkthrough end to end:
  `uv run --group dev pytest -q -m e2e tests/test_walkthrough.py`.

Reference: [docs/architecture.md](../../docs/architecture.md), [docs/extending.md](../../docs/extending.md).
