---
description: "Static validation of generated workflows: actionlint, zizmor and the policy checks"
applyTo: "j2gha/validate/**"
paths:
  - "j2gha/validate/**"
---
# Validate

- `j2gha/validate/static.py` runs actionlint (structural and shellcheck findings are kept separate), zizmor and the
  j2gha policy checks; `j2gha/validate/contexts.py` checks expression contexts.
- Structural and policy errors block validation; shellcheck and zizmor findings are reported. A scanner that fails to
  run is a failure.
- Scanners run without network access (`--network none`, zizmor `--offline`).
- `j2gha/validate/*` is protected for rule-improvement changes (`evals/protected.txt`): it judges results.

Reference: [docs/tooling.md](../../docs/tooling.md), [docs/architecture.md](../../docs/architecture.md).
