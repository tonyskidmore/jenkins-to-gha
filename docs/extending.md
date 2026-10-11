# Extending the converter

`j2gha analyze` and `j2gha convert` contain no model and learn nothing at run time. Everything they "know" about how a
Jenkins construct maps to GitHub Actions was written down by a person (or an AI agent working for a person) as one of:

- an entry in the **step catalog**, `j2gha/rules/steps.yaml`, which says *what we have decided* about a step;
- code in the **generator**, `j2gha/convert/generator.py` and `j2gha/convert/expressions.py`, which says *how to emit it*.

The rules therefore grow by adding catalog entries and generator code, then proving them with tests and the
differential run (Jenkins against the converted workflow). This page describes that loop. It works the same whether a
human or an agent does it. The optional `jenkins-docs` and `gha-docs` skills exist to make step 2 faster.
[Improving the development loop](#improving-the-development-loop) covers how to make this procedure repeatable for
agents and where the implementation needs strengthening. The existing agent workflow and its safeguards are in
[self-improvement.md](self-improvement.md).

## What the harness does with a step it does not know

| Situation | Result |
|---|---|
| In the catalog as `direct` and mapped in the generator | Converted to real steps, full coverage credit |
| In the catalog as `policy`, `redesign` or `dynamic` | A generator mapping may approximate it; otherwise a placeholder step (`::warning:: ... requires manual migration`), listed in the migration report with the suggested GHA pattern |
| `noop` | Dropped, noted in the report |
| Not in the catalog (category `unknown`) | Placeholder step, counted in `unknown_steps`, shown as a plugin or shared-library step |

So an unknown step is never silently lost. Extending the rules means moving steps up this table.

## The loop

### 1. Find the gap

Run the corpus and read what was left over:

```bash
uv run j2gha pipeline all --continue-on-invalid
uv run j2gha summary
```

Look at `examples/NNN/analysis/` (the `unknown_steps` list and the findings) and the "manual" rows in each
`gha/migration-report.md`. `uv run j2gha gaps` ranks the candidates. Pick one step that recurs, or one a particular pipeline needs. Prefer a step you can pin to a
real Jenkinsfile in `examples/`, so there is something to test against. If none exists yet, add one with
`j2gha crawl` (see the `jenkins-example-crawler` skill).

### 2. Decide the mapping from the documentation, not from memory

Establish two facts with authoritative sources:

- **Jenkins side:** the step's parameters, defaults and which plugin provides it. Use `j2gha docs fetch jenkins` and the
  `jenkins-docs` skill, or `jenkins.io`.
- **GitHub side:** the action, workflow key or shell pattern that gives the same behaviour, and the semantic traps.
  Use `j2gha docs fetch gha` and the `gha-docs` skill, or `docs.github.com`. `j2gha docs xref <step>` prints the
  crosswalk for constructs already listed in `rules/docs-xref.yaml`.

Then choose a category. This is a policy decision, not a technical one:

| Category | Use it when |
|---|---|
| `direct` | One deterministic, high-confidence mapping that the generator can emit without asking anyone anything |
| `policy` | Mappable, but the right pattern depends on an organisational decision (secrets, registries, reporting) |
| `redesign` | No line-for-line equivalent; needs a GHA-native design (approvals, downstream jobs) |
| `dynamic` | Runtime Groovy behaviour that cannot be converted statically and safely |
| `noop` | Cosmetic in GHA (log decoration), safe to drop |

Pin actions by full commit SHA and preserve the generated workflow's security defaults (`permissions: contents: read`,
checkout with `persist-credentials: false`). Check the emitted `uses:` references: the current resolver can leave a
floating tag when resolution fails, and the policy check reports an unpinned action as a warning.

### 3. Add the catalog entry

In `j2gha/rules/steps.yaml`:

```yaml
  archiveArtifacts: {category: direct, weight: 1, gha: "actions/upload-artifact"}
```

`weight` is the relative migration risk of one occurrence and feeds weighted coverage and the difficulty score. `gha`
is the target pattern shown in the report. Entries with `category: unknown` are not written; that is simply the absence
of an entry.

If the step is a Jenkins construct that should appear in the migration report's Reference section, also add or extend
an entry in `j2gha/rules/docs-xref.yaml`. Every GHA page named there must exist in
`tests/fixtures/gha-pagelist-fpt.txt`, and `tests/test_docs.py` checks it.

### 4. Implement it in the generator (for `direct`)

Add a branch in `generator._step` (it is a dispatch on the step name) that returns the GHA step dicts, and record the
outcome with `ctx.add(...)` so the report says `mapped` or `approximated`. The following rules apply:

- Anything translating a Groovy expression to a `${{ }}` expression goes through `expressions.py`. If it cannot be
  translated safely it must become an opt-in `vars.J2GHA_WHEN_L<line>` style gate, never a guess that widens a stage.
- A condition or expression must be valid *where GitHub evaluates it*: job-level `if:` only sees `github`, `needs`,
  `vars`, `inputs`; an `env:` entry cannot read a sibling entry of the same mapping (a step's `if:` can read the step's own
  `env:`); only the documented functions exist.
  `validate/contexts.py` enforces this on every generated workflow; add a case to `tests/test_contexts.py` (the cross
  product) when a new construct can combine with the existing ones.
- Per-step metadata lives under `_j2gha` and is stripped from `workflow.yml` into `gha/workflow.model.json`.

`policy`, `redesign` and `dynamic` entries can use the existing placeholder path without new generator code; the
catalog supplies the guidance in the report. Where a bounded approximation is useful, record its limits explicitly.

### 5. Keep the trace in step on both sides

The differential run compares `J2GHA-TRACE {"stage","step"}` lines from Jenkins and from GHA. A step is traced on the
GHA side if and only if the Jenkins localiser stubs it with a marker. Both sides read the lists in `j2gha/trace.py`:

- `TRACED_STEPS`: leaf steps stubbed with a marker (the generated step passes `trace=True`);
- `STUBBED_WRAPPERS`: block steps whose body runs but whose resources are stubbed (`withCredentials`, `sshagent`, ...);
- `SILENT_STUBS`: steps mapped to workflow-level constructs, not steps.

Add the step to the right list rather than to one side. Changing a stub on one side only breaks equivalence for every
example. When localisation changes what a run records, bump `LOCALIZER_VERSION` in `j2gha/jenkins/localize.py`, so
stale run records are re-done instead of trusted.

If the new step needs a plugin so Jenkins accepts the pipeline (a false `JenkinsValidationFailed` finding is the
symptom), add it to `docker/jenkins/plugins.txt`: add the bare name, run `uv run j2gha docker build --only jenkins`, and
paste the `+ name:version` lines it prints.

### 6. Test it

Add unit tests next to the existing ones in `tests/test_convert.py` (use a small hand-built `Step`/`Stage`, or a
committed AST fixture), then:

```bash
uv run --group dev pytest -q
uvx ruff check j2gha tests --select F,E9,B --ignore B008
```

The structural checks in `j2gha/validate/contexts.py` run on every generated workflow in the tests (the committed corpus and
the cross product in `tests/test_contexts.py`); if the new step can combine with other constructs (`dir`, `withEnv`,
`input`, parallel, post), add it to the dimensions there. `uv run --group dev pytest -q -m e2e tests/test_walkthrough.py`
runs example 000 through Jenkins and act in both modes (about 7 minutes, needs Docker); run it after generator or
localiser changes.

`test_direct_catalog_steps_have_a_generator_mapping` fails if a `direct` entry has no generator mapping, so a catalog
entry cannot claim coverage the generator does not deliver. If you changed the Groovy dumper, regenerate the fixtures
with `uv run python tests/test_fixtures.py`.

### 7. Prove it with the differential run

Unit tests show the generator does what you wrote. The differential run shows it matches what Jenkins does:

```bash
uv run j2gha pipeline <ids> --continue-on-invalid      # analyze -> convert -> validate -> run (jenkins, act)
uv run j2gha run <ids> --tier selfhosted               # real GitHub Actions on local runners, no minutes
```

Read the outcome per example:

| Outcome | Meaning |
|---|---|
| equivalent | No difference found in the compared contract: same stages, same order as the Jenkinsfile fixes (parallel branches and concurrent stages may interleave), same result. Not a proof that the conversion is correct (see [mechanism.md](mechanism.md#what-the-verdicts-establish)) |
| differs | The converted workflow diverged from Jenkins in what was compared. Usually a conversion bug or a wrong mapping decision, but it can also come from localisation (what the harness stubs or rewrites to run the pipeline here) or from the environment (different images and package versions); see [mechanism.md](mechanism.md#what-the-verdicts-establish) |
| inconclusive | Empty trace, matching traces with different results, no usable Jenkins reference (another Jenkinsfile, scenario or localiser version), or (full mode) no stage or job data. Never counted as equivalent |

To exercise both branches of a new condition, pin the parameters: `uv run j2gha run <id> --param NAME=VALUE ...` runs the
same scenario on both sides (declared parameters only). To show the comparator catches a deliberately broken
conversion, edit `gha/workflow.model.json` and run with `--edited-model` (without it the edited model is refused; the
record is marked and never counted).

For changes to commands, artifacts or test reporting, also run the affected examples with `--mode full`. Trace mode
cannot establish those results. Preserve the result and logs for each parameter scenario before running the next:
the current layout stores one result per tier and mode, so another scenario replaces that record.

Validation (actionlint, zizmor, policy checks) runs as part of the pipeline and catches invalid YAML, bad expressions and
insecure patterns. Then run the whole corpus once more to check that the change did not regress other examples, and run
`uv run j2gha summary` to refresh `examples/README.md`.

Hosted runs spend account minutes and need explicit approval; the `selfhosted` tier is the default way to confirm
behaviour on real GitHub Actions.

### 8. Commit

The commit contains the rule (catalog and generator), its tests, any new example and regenerated `analysis/`, `gha/`
and `runs/` records. Those directories are generated, so never hand-edit them; re-run the stage instead.

## Limits of this approach

- **Trace equivalence is control-flow fidelity.** A trace marker names the stage and the step kind, not the command.
  Full mode also compares outcomes, test cases and archived file paths, but archive content hashes are diagnostic
  and do not determine the verdict. Neither mode establishes behaviour beyond the scenarios run. See "Known limitations" in
  [architecture.md](architecture.md#known-limitations-and-where-to-extend).
- **Coverage follows the corpus.** Rules are only exercised by pipelines in `examples/`. A rule with no example behind
  it has only unit tests, which is why step 1 recommends adding an example first.
- **An agent proposes, the checks decide.** If an AI agent does steps 2 to 4, nothing it writes is trusted until steps 6
  and 7 pass and the mapping has been reviewed. The generator stays the only thing that emits YAML.

## Improving the development loop

The next extension is to make the procedure above consistently executable and measurable. Strengthen the existing
[`j2gha-rule-improver`](../.claude/skills/j2gha-rule-improver/SKILL.md) and add a separate
`j2gha-reliability-improver`, backed by shared evaluation and reporting helpers. The reliability skill and the helper
workflow described here are **proposed work**; the existing `gaps`, `scoreboard` and `guard` commands provide a starting
point, not a complete evaluation system.

### Separate conversion capabilities from reliability fixes

| Work | Scope | Evidence required |
|---|---|---|
| Rule improvement (existing skill) | One bounded conversion capability, such as support for a documented Jenkins step | Documented semantics, boundary and interaction tests, fresh conversion, relevant differential scenarios and no unexplained regressions |
| Reliability improvement (proposed skill) | A reproduced defect in parsing, generation, execution or reporting | Failure before the fix, an independently justified expected result, a regression test and relevant integration evidence |

This distinction preserves the rule-improver's restrictions on changing the infrastructure that judges its work.
A reliability fix may need to change a validator or comparator; give that task an explicit file scope and independent
review of the expected outcomes. For example, a comparator fix needs both a correct conversion it accepts and a
deliberately incorrect conversion it rejects. Do not weaken the rule-improver's protections globally to permit it.

Before editing, define the expected behaviour, affected scenarios and permitted files. Classify the problem as a
converter defect, harness defect, unavailable service or toolchain, stale evidence, or unsupported semantics. A
conversion change should not compensate for an environmental failure, and a runnable twin should not conceal a
genuine conversion difference. For functionality work, weigh feasibility and independent examples alongside
`gaps --unmapped-only`: a high-cost construct may still need a policy decision or redesign.

Use the relevant versioned documentation and, where practical, a minimal Jenkins execution to establish the expected
behaviour. Demonstrate a bug's regression test failing before the fix. Exercise the boundaries and interactions that
matter, including `when`, `post`, wrappers, parallel branches and workspace handoffs. Keep separate findings as
separate tasks unless they prevent evaluating the chosen change.

### Make regeneration and evidence collection executable

The skill should explain the decisions; shared helpers should perform the repeatable checks. Build on
[`j2gha/improve.py`](../j2gha/improve.py), [`j2gha/stages.py`](../j2gha/stages.py) and the existing structured run records:

| Helper responsibility | Required behaviour |
|---|---|
| Workspace preparation | Record the starting revision and existing work; use an isolated workspace when appropriate without disturbing unrelated edits |
| Evaluation selection | Declare required examples, scenarios, modes and tiers from the change scope; record what actually ran |
| Regeneration and artifact checks | Refresh affected analysis and conversion before execution; verify required artifacts match the source, model and scenario |
| Result collection | Retain command exit status, structured verdicts, logs and provenance; distinguish regressions from missing or inconclusive evidence |
| Evidence report | Explain the original problem, expected behaviour and sources, implementation, before/after results, limitations, unmeasured tiers and changes needing particular review |

The current rule-improver permits evaluating with `j2gha run` alone. After a generator edit that can execute an old
model: source/model hashes detect changed artifacts, but do not prove the current generator produced them. Require
conversion before execution, or use `pipeline` to perform the stages in order. A helper must also inspect comparison
verdicts: `run` defaults to returning success even when a comparison differs; `--fail-on-differs` makes differing or
inconclusive comparisons affect its exit status.

Run focused checks first, then the relevant broader suite and differential scenarios from the loop above. Keep
baseline updates and merging separate from producing a reviewable proposal. A successful command or test suite alone
does not establish semantic correctness.

### Strengthen the evaluation before repeating agent tasks

Three gaps in the current implementation should be addressed before using repeated attempts to optimise a skill:

1. **Require complete evidence.** `improve._verdict` reads only `runs/<tier>-trace/result.json`. The scoreboard's
   `--strict` comparison flags lost measurements for previously equivalent tiers; it does not require every relevant
   full-mode run or scenario, and a tier missing from both baseline and candidate can remain unmeasured. Add explicit
   requirements per task and fail the evaluation when required evidence is missing, stale or inconclusive. Reuse
   [`outputs.py`](../j2gha/outputs.py), which already compares test case identities/statuses and archived file paths.
   Content hashes are recorded but do not affect the verdict; stronger content contracts need explicit rules for
   reproducible outputs and known nondeterminism.
2. **Split by pipeline family.** `improve.gaps` excludes exact holdout IDs, allowing a held-out original's twin into
   development evidence. Use `source.json`'s `derived_from.example` relationship to group originals and twins, and
   keep related scenarios and mutations in the same family. Verify that selecting any family for holdout excludes
   all of its members from development and skill selection.
3. **Protect the whole evaluator.** [`evals/protected.txt`](../evals/protected.txt) covers much of the harness, but
   does not list `j2gha/outputs.py`; `improve.removed_test_lines` also exempts `tests/fixtures/`. Extend the protections
   to the output comparator and evaluation fixtures, with an explicit review path for legitimate fixture
   regeneration. Add deliberate-cheat checks proving that weakening either is detected. When reliability work
   changes the evaluator itself, retain separately maintained positive and negative cases and review their expected
   results independently.

### Further opportunities in the implementation

The same code review identifies improvements that would help both human and agent contributors:

- **Tie evidence to the implementation that produced it.** [`provenance.py`](../j2gha/provenance.py) and
  [`runners/execute.py`](../j2gha/runners/execute.py) track source/model hashes and the localiser version, but
  `stale_reason` does not invalidate evidence for generator, catalog or validator changes alone.
  `validate/static.py` records tool images and a timestamp without a workflow hash. Record relevant implementation
  and configuration fingerprints, the validated workflow hash and resolved tool image identities. A check should
  reject an old result after its producer or input changes, while unrelated documentation edits remain harmless.
- **Retain multiple scenarios.** `run_example` writes each result under `runs/<tier>-<mode>/`, replacing the previous
  scenario's record. Introduce scenario identifiers and an evaluation manifest listing the required runs; keep a
  convenient latest-result view for existing reports. Prove that two parameter scenarios remain independently
  inspectable and that a missing scenario cannot be satisfied by a different one.
- **Make action pinning reproducible.** `generator.github_resolver` returns no resolution without a token or when a
  lookup fails; `pin_actions` then leaves the tag intact, and `validate/static.py` treats it as a warning. Consider a
  reviewed action lock file and an explicit failure or incomplete-conversion status for unresolved references.
  Acceptance should include repeatable offline conversion from known pins and a clear result for an unknown action.
- **Separate generator responsibilities as they grow.** [`convert/generator.py`](../j2gha/convert/generator.py) combines
  job planning, step mappings, shell translation, reports and action resolution. `convert/workspace.py` already shows
  how a cohesive concern can be extracted. Move further responsibilities behind small interfaces when extending
  them, preserving `_j2gha` metadata and reporting. Keep structural refactors separate from semantic changes and
  verify that existing corpus models and reports remain unchanged for a refactor.

For conversion capabilities themselves, use the extension points in
[architecture.md](architecture.md#known-limitations-and-where-to-extend), including bounded Groovy dataflow,
shared-library mappings and workspace handoff support. Prioritise them using observed pipeline needs and evidence
from the loop above.

### Evaluate skill optimisation only after the loop works

Start with a reusable evaluation/reporting helper, tighter regeneration requirements for the rule-improver and the
proposed reliability skill. Exercise them on one reproduced bug with a failing regression test and one bounded,
documentation-grounded conversion extension. Use the reports to correct the workflow, then expand to independent
task families. Record recurring problems such as missed semantic constraints, misclassified failures, incomplete
regeneration, missing boundary tests and unsupported claims in reports.

SkillOpt could then be evaluated as a way to improve the development instructions: it revises a skill, an agent
attempts a bounded code change, and trusted tests and execution judge the result. The deployed converter remains
deterministic, and each useful code change still needs its own review.

Compare the original skill, a manually improved skill and a SkillOpt candidate. Reset each attempt to its specified
codebase snapshot so accumulated code improvements do not appear to be better skill performance. Keep the target
model, tools and evaluator fixed, use separate training, selection and final held-out task families, and keep hidden
checks and answer keys outside the agent's workspace. Measure correct, reviewable changes per attempt, regressions,
reviewer corrections and cost. Coverage and passing tests are supporting evidence; a candidate that weakens checks
or overstates its results must not benefit from a higher aggregate score.
