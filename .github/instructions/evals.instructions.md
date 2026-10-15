---
description: "Rule-improvement evals: human-owned baseline, holdout and protected-file lists"
applyTo: "evals/**,j2gha/improve.py"
paths:
  - "evals/**"
  - "j2gha/improve.py"
---
# Evals

- `evals/holdout.txt`, `evals/protected.txt` and `evals/baseline.json` are human-owned. Only a human runs
  `uv run j2gha scoreboard --write`.
- `scoreboard --check` compares coverage, automation, unknown steps, manual items, validation and verdicts against the
  baseline; the difficulty column is display-only.
- `uv run j2gha guard --base main` fails when a rule-improvement change touches a `[protected]` path, and warns on
  `[review]` ones.
- `j2gha gaps` leaves holdout examples out, so a rule is not tuned to the examples that validate it.

Reference: [docs/self-improvement.md](../../docs/self-improvement.md), [docs/extending.md](../../docs/extending.md).
