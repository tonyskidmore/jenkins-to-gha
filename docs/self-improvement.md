# Improving the rules with an AI agent (design and starting point)

Status: **starting point.** The evaluation helpers and a propose-only skill exist; nothing here is autonomous, and the
loop has not been run end to end by an agent yet. Treat this page as the design plus an honest list of what can go wrong.

[extending.md](extending.md) describes how a person adds a conversion rule. This page describes how an agent could do
the same, using the corpus as an evaluation set. It is useful to think of it like model development:

| ML | Here |
|---|---|
| Training data | `examples/NNN` (excluding the holdout) |
| Validation set | the ids in `evals/holdout.txt` |
| Weights | `rules/steps.yaml`, `convert/generator.py`, `convert/expressions.py`, the lists in `trace.py` (readable and diffable) |
| Loss / metrics | per-example verdict, automation %, weighted coverage, static validation, unit tests (`j2gha scoreboard`) |
| Optimizer | the agent (or a person), via `.claude/skills/j2gha-rule-improver` |
| Checkpoint / baseline | `evals/baseline.json`, moved only by a human |

## What exists

| Piece | Purpose |
|---|---|
| `uv run j2gha gaps [--unmapped-only]` | Worklist: steps the corpus uses that are `policy`, `redesign`, `dynamic` or not in the catalog, ranked by occurrences x weight. Holdout examples are excluded, parse debris is dropped. `--unmapped-only` keeps steps not in the catalog or listed as `manual` in a migration report. Reads artifacts only |
| `uv run j2gha scoreboard [--check] [--strict]` | One row per example from the existing artifacts. `--check` exits 1 on any regression against `evals/baseline.json`. A tier whose baseline verdict was `equivalent` and is now `stale` or `none` (not re-run) prints as `unmeasured:`, and `--strict` fails on it; a tier that was `differs` or `inconclusive` can lose its measurement without either |
| `uv run j2gha guard [--base REF]` | Exits 1 if the change touches a file in `evals/protected.txt`, removes or alters an existing test line, or changes the `category`/`weight` of (or removes) an existing `steps.yaml` entry. In `trace.py` and `localize.py` only the named stub lists and `LOCALIZER_VERSION` may change (the `[lists]` section of `evals/protected.txt`; the module is compared as an AST, so comments and formatting are free). Lists `[review]` files that need a human read |
| `evals/holdout.txt`, `protected.txt`, `baseline.json` | The split, the do-not-touch list, and the committed snapshot |
| `.claude/skills/j2gha-rule-improver` | A propose-only procedure: one step per branch, evidence in the report, no merge |
| `tests/test_improve.py` | Unit tests for the three helpers, no Docker needed |

All of it is deterministic Python over artifacts the harness already writes. It needs no model; the skill is the only
agent-specific part.

## The loop

```text
baseline (scoreboard --check = clean)
   -> gaps: pick the top step
   -> read .docs/ (jenkins-docs, gha-docs): decide category and mapping
   -> edit steps.yaml / generator / tests (branch rules/<step>)
   -> pytest + ruff + pipeline all + scoreboard --check + guard
   -> report with evidence -> HUMAN reviews and merges -> human refreshes the baseline
```

A change is acceptable only if the scoreboard shows no regression on any example, holdout included, the guard passes,
and a person has read the mapping. The scoreboard decides *whether anything got worse*; it cannot decide *whether the
mapping is right*.

## Risks

1. **Reward hacking (Goodhart).** An optimizer finds the cheap way to move the number. Examples: reclassifying a step to
   `noop` or `direct` to raise coverage; lowering a catalog `weight`; adding a step to one side of the trace lists so a
   `differs` becomes `inconclusive`; editing `trace.compare`, the localiser or the validators; deleting or loosening a
   test; running `scoreboard --write` after a regression. *Mitigation:* `evals/protected.txt` plus `guard` (including the catalog check), the skill's
   hard rules, and the human-only baseline. The catalog check covers `category` and `weight` only: a reworded `gha:` target or a new entry that is
   deliberately generous still needs a reader. `trace.py` and `localize.py` hold both the lists a new step must join and the logic that judges results, so they are
   `[lists]`: only the named list assignments may change. A list edit is still a `[review]` note, because the generator and
   the localiser must stay in step (for example `FULL_MODE_STUBS` is localiser-only).
2. **Overfitting a small corpus.** Twenty examples (four held out) is little. A rule that fixes one Jenkinsfile can
   mis-convert another, and agents will read the example in front of them. *Mitigation:* the holdout and the
   `gaps` default exclude it; the gate covers all examples. Grow the corpus with `j2gha crawl` before relying on this,
   and rotate the holdout when it is used up. Holdout exclusion is a convention the agent follows, not a technical
   barrier: it can still read the files.
3. **A weak oracle.** Trace equivalence is control-flow fidelity: same stages, same step kinds, same order. It does not
   show that commands, outputs, artifacts or secrets handling are equivalent, and trace mode stubs return values. A wrong
   mapping (a mis-translated condition, the wrong action input) can pass. `inconclusive` is treated as "not worse", so a
   regression into it is not caught unless it was `equivalent` before. *Mitigation:* new agent mappings default to
   `policy`; promote to `direct` only after human review and, ideally, a full-mode run; a person reads every diff.
4. **Gaps that are not gaps.** `gaps` includes `policy` steps (e.g. `withCredentials`, `retry`) that the generator
   already approximates, and `node`/`container` rows that reflect structure. Ranking by cost can send the agent after
   work that does not change results. *Mitigation:* `gaps --unmapped-only` keeps steps that are not in the catalog or whose
   conversion rows are `manual`, and the skill uses it; a person can pick the target.
5. **Documentation is wrong, stale or version-mismatched.** `.docs/` pins a Jenkins plugin set and one GHA product
   version (github.com by default). A GHES target, a renamed input or a plugin behaving differently from its page gives a
   confidently wrong rule. Fetched pages are also untrusted text an agent reads. *Mitigation:* record the pages and
   versions in the PR, treat page content as data, and do not let the agent follow instructions found in them.
6. **Supply chain.** A new `uses:` action is third-party code in every generated workflow; plugin additions change the
   controller image. *Mitigation:* SHA-pin, prefer first-party actions, a human reviews every new dependency.
   `docker/jenkins/plugins.txt` is a `[review]` path.
7. **Silent staleness.** `scoreboard --check` compares stored artifacts. If a stage was not re-run, rows show `stale`
   or old numbers and a regression is invisible. *Mitigation:* the procedure re-runs `pipeline all` first; a `stale` or
   `none` verdict on a tier that was `equivalent` is reported as `unmeasured`, never a pass, and `--strict` makes it fail
   (a lost `differs` or `inconclusive` measurement is not flagged). The skill only re-runs `jenkins,act`, so
   selfhosted verdicts of changed examples show as unmeasured until a person re-runs that tier.
8. **Cost and safety.** Hosted runs spend account minutes and are for the user only. The operator's credentials never enter runs
   (`FAKE_*` values); remote jobs still get GitHub's automatic job token. An agent that edits runner or budget code defeats this, hence those paths are protected.
9. **Review fatigue.** One reviewable branch per step is the point. If the volume exceeds what a person can read
   carefully, stop: unreviewed merges are the largest risk here, larger than any single wrong rule.
10. **Process rot.** The baseline moves by a human, but a baseline refreshed carelessly just ratifies a regression.
    Commit it separately and look at the `improved:`/`REGRESSED:` output first.
11. **Flaky infrastructure.** The disposable Jenkins controller can fail a run for reasons unrelated to the rules (seen once:
    `UnapprovedUsageException: script not yet approved` on example 020, gone on re-run). A flake looks like a regression at the
    baseline or hides a real one later. *Mitigation:* the skill re-runs a regressed example once and reads the console log
    before deciding; a human should harden the runner (retry on that exception) rather than the agent.

## Tests of the skill and the guard

**First run (2026-10-05, supervised).** It stopped at the baseline gate on a controller flake, so the implement and
evaluate steps are still untested. It led to the `unmeasured` handling, the catalog check in `guard`,
`gaps --unmapped-only`, and the flake and branch steps in the skill.

**Reward-hack drill (2026-10-05).** 17 deliberate cheats were applied one at a time on a scratch branch and checked with
`j2gha guard`, plus one legitimate change as a control:

| Result | Cheats |
|---|---|
| Blocked | catalog category or weight changed or entry deleted; validators, runners, provenance, `baseline.json`, `holdout.txt`, CI, the AST dumper or the guard edited; a test line deleted or loosened |
| Was open, fixed | `trace.compare` edited (previously only a `review:` note). Now `trace.py` and `localize.py` may only change the stub lists |
| Open, accepted | a reworded catalog `gha:` target is not checked; a stub added to only one side's list passes with a `review:` note |
| Control | a new catalog entry plus an added test passes |

The drill is a manual procedure, not CI. `tests/test_improve.py` covers the same patterns against throwaway git repositories.

**Next:** a supervised run on `rocketSend` through implement and evaluate, then a second target (for example `withChecks`)
in a fresh session to see whether the skill behaves the same without prior context.

## What is deliberately not built

- No autonomous merge, no scheduled agent run, no auto-updating baseline.
- No technical enforcement of the holdout beyond the `gaps` default, and no sandbox: the guard checks the diff after
  the fact. A branch protection rule requiring the `guard` command in CI is the natural next step.
- No complete semantic oracle. Full mode compares outcomes, test cases and archived file paths; archive content
  hashes are recorded but do not affect the verdict. The scoreboard still reads trace results only. Requiring the
  relevant full-mode evidence and strengthening output contracts would improve the judge before changing the optimizer.
- No metric over time. `baseline.json` is one snapshot; trend tracking can come from git history.

## Suggested next steps

1. Run the loop by hand on one step (`rocketSend`) and keep the notes; revise the skill from what actually goes wrong.
2. Add `j2gha guard --base origin/main` and `scoreboard --check` to CI for branches named `rules/*`.
   Harden the Jenkins runner against the approval flake (a retry on `UnapprovedUsageException` in `jenkins/run.py`); that is a human change.
3. Crawl more examples and enlarge the holdout.
4. Require relevant full-mode evidence and strengthen output contracts before allowing more than propose-only.

The consolidated roadmap in [extending.md](extending.md#improving-the-development-loop) develops these next steps,
separates rule improvements from reliability fixes, and sets out how to evaluate skill optimisation after the
development workflow has been exercised.
