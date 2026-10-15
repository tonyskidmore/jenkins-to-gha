---
description: "Unit and end-to-end tests: AST fixtures, fingerprints, markers, environment isolation"
applyTo: "tests/**"
paths:
  - "tests/**"
---
# Tests

- `uv run --group dev pytest -q` runs the unit tests (no Docker). End-to-end tests are marked `e2e`:
  `tests/test_walkthrough.py` (example 000, Jenkins vs act, about 4 minutes) and `tests/test_handoff_e2e.py`
  (`J2GHA_E2E_TIERS=act,selfhosted` also runs on real GitHub Actions).
- Tests use committed AST fixtures (`tests/fixtures/*.ast.json`). After changing the dumper, run
  `uv run python tests/test_fixtures.py`: it regenerates every fixture and `DUMPER.sha256`. CI checks the hash; the
  `docker`-marked test re-dumps locally.
- `tests/test_localizer_version.py` fingerprints the localised fixtures; see the execution rules for bumping
  `LOCALIZER_VERSION`.
- Tests that check job structure run with the workspace hand-off off (`no_workspace_handoff` fixture);
  `tests/handoff_sim.py` runs the generated hand-off steps against Jenkins' one workspace (`tests/test_handoff_model.py`).
- `tests/conftest.py` isolates the operator's `J2GHA_PIPELINES_DIR` and `J2GHA_OFFLINE`; set them in a test with
  `monkeypatch`.
- `tests/test_agent_docs.py` checks this agent material: links resolve, rule globs match files, skill frontmatter is
  valid.
- For rule-improvement changes, existing test lines may not be removed or weakened (`evals/protected.txt`).

Reference: [docs/extending.md](../../docs/extending.md).
