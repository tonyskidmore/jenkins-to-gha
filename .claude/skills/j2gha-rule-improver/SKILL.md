---
name: j2gha-rule-improver
description: Propose ONE improvement to the j2gha conversion rules (rules/steps.yaml catalog entry plus generator code and tests) for the highest-cost unmapped Jenkins step, grounded in the local .docs/ bundles and checked against the examples/ scoreboard. Propose-only - works on a branch, never touches the evaluation files, and leaves the merge decision to a human. Use when asked to improve, extend or "teach" the converter, add support for a Jenkins step, or reduce manual/unknown steps across the corpus.
argument-hint: "[step name]  (default: the top row of `j2gha gaps`)"
---

# Improve the conversion rules (propose-only)

Follow `docs/extending.md` for the procedure and `docs/self-improvement.md` for why the guardrails exist. This skill is
the same loop with a worklist and a gate. You are the optimizer; the harness is the judge and you do not edit the judge.

## Hard rules

- Work on a new branch `rules/<step>`. Never commit to `main`, never push, never open a hosted run (`--tier hosted`).
- One step per branch. Stop after one proposal and report.
- Do not edit anything matched by `evals/protected.txt` (the validators, runners, comparison, provenance, the dumper,
  `evals/*`, CI), and do not delete or weaken an existing test. `uv run j2gha guard --base main` must pass.
- Do not move a step to `noop`, change a catalog `weight`, or add a step to only one side of the trace lists to improve
  a number. Categories follow the documentation, not the score. (`guard` enforces the catalog part.)
- Do not read `evals/holdout.txt`-listed examples to design the rule. `j2gha gaps` already excludes them.
- New mappings of unknown semantics default to `category: policy` (placeholder plus guidance), not `direct`.

## Procedure

1. **Baseline.** Start from a clean tree on a worktree or throwaway checkout (`git status` empty). Run
   `uv run j2gha pipeline all --continue-on-invalid` (Docker needed; `jenkins,act` only; about 10 minutes), then
   `uv run j2gha scoreboard --check`. It must exit 0.
   - `unmeasured:` lines are a tier you did not re-run (e.g. selfhosted); they are not failures. Report them.
   - On `REGRESSED:` before you changed anything, re-run only those ids once (`uv run j2gha run <ids> --tier jenkins,act`)
     and check again. Read `examples/<id>/runs/jenkins-trace/console.log`: a controller error such as
     `UnapprovedUsageException` or a connection error is a flake. If the regression persists, or the cause is not
     environmental, stop and report: the tree is not clean. Do not edit rules to compensate.
2. **Pick the gap.** `uv run j2gha gaps --unmapped-only`. Use `$ARGUMENTS` if given, else the top row. Without
   `--unmapped-only` many rows are `policy` steps the generator already approximates (`withCredentials`, `retry`).
   Read the step in the example Jenkinsfiles it appears in.
3. **Branch.** `git switch -c rules/<step>` now, before editing. Generated files under `examples/` that the baseline run
   refreshed are churn: discard them (`git checkout -- examples`) so the branch contains only the rule change, its
   tests and, if the change is meant to alter results, the regenerated records for the affected examples.
4. **Ground it in the docs.** Use the `jenkins-docs` skill (step parameters, plugin) and `gha-docs` skill (action, keys,
   limits). Run `j2gha docs status` first; fall back to the web only if no bundle exists. Quote the pages you relied on in
   the PR. If the docs do not settle the mapping, stop and ask a human; do not guess.
5. **Implement.** Catalog entry in `j2gha/rules/steps.yaml` (add entries only: `guard` fails on a changed `category` or
   `weight` of an existing one); for `direct`, a branch in `generator._step`; trace lists in `j2gha/trace.py` and
   `FULL_MODE_STUBS` in `j2gha/jenkins/localize.py` when a step leaves the unknown list, so both sides still stub it;
   plugin in `docker/jenkins/plugins.txt` only if Jenkins rejects the pipeline without it. Add tests to
   `tests/test_convert.py`. SHA-pin any action.
6. **Evaluate.** `uv run --group dev pytest -q`; `uvx ruff check j2gha tests --select F,E9,B --ignore B008`;
   re-run the examples the change can affect and the holdout with `uv run j2gha run <ids> --tier jenkins,act` (or
   `pipeline all`); then `uv run j2gha scoreboard --check` and `uv run j2gha guard --base main`.
   Any `REGRESSED:` or `PROTECTED:` line means revert or fix, never adjust the baseline.
7. **Report** (final message and PR body): the step and why it was chosen, docs consulted, files changed, the
   scoreboard `improved:` and `unmeasured:` lines, the guard output, anything marked `review:`, and what you are unsure
   of. State plainly that equivalence is control-flow fidelity and the mapping's semantics need a human check.

Never run `j2gha scoreboard --write`: moving the baseline is the human's merge decision.
