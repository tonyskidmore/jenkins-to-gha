# The key mechanism

The research conversation (with Perplexity) that started the project wandered from "is JCasC still a thing" to Docker, `act`, SAST/DAST and ASTs. Strip
away the detours and one mechanism remains:

> **Treat a Jenkinsfile as a program whose *intent* must be extracted into a typed intermediate representation (IR)
> via its AST; generate GitHub Actions deterministically from that IR; and test the conversion by *differential
> execution* - run the original on a disposable Jenkins and the conversion on GHA-compatible runners, and compare
> observable behaviour, not text.**

The original framing said "prove equivalence". Differential execution cannot do that: it finds differences in what
it observes, for the scenarios it runs. An `equivalent` verdict means *no difference was found in the compared
contract* (see [What the verdicts establish](#what-the-verdicts-establish)).

Everything else in the conversation is a component of that loop.

```text
            ┌──────────────────────── evidence-backed migration package ──────────────────────────────────┐
Jenkinsfile │  1 PARSE           2 MODEL            3 ASSESS            4 GENERATE        5 TEST          │
 (+ repo)   │  Groovy AST   ──▶  typed IR       ──▶  coverage +     ──▶  GHA YAML     ──▶  differential │
            │  Jenkins        (provenance:       hard gates +        + migration       execution          │
            │  Declarative    every node keeps   difficulty score    report            Jenkins vs         │
            │  model          its source line)   (0-100)             (mapped/approx/   act/GHA            │
            │                                                        manual/dropped)                      │
            └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

## The five load-bearing ideas

### 1. Two ASTs, not one - and don't parse with regexes

A Jenkinsfile is Groovy plus a Jenkins DSL. The conversation's strongest technical point is to use **two trees**:

| Tree | What it gives | j2gha implementation |
|---|---|---|
| Groovy AST | every call, closure, loop, `script{}` body, `load`, `@Library`, helper method - with line/column | `docker/jenkins/groovy/ast_dump.groovy`, run with the **Groovy 2.4.21 jar bundled inside jenkins.war** (exact parser parity with Jenkins) |
| Jenkins Declarative model (`ModelASTPipelineDef`) | Jenkins' own validated, normalised view of `pipeline {}` | `POST /pipeline-model-converter/toJson` + `/validate` on a disposable controller |

Research confirmed the conversation's hunch about *why* both are needed: Jenkins' JSON model has **no line numbers**,
**drops `@Library`**, and **truncates one-line `script{}` blocks**, so it cannot be the only source - but it is the
authority on validity. j2gha builds its IR from the Groovy AST (with provenance) and cross-checks stage structure
against Jenkins' model, recording discrepancies as findings.

### 2. A canonical IR is the contract

"Do not translate Jenkins Groovy directly to YAML." The IR (`j2gha/ir.py`) is deliberately small - `Pipeline`,
`Stage`, `Step`, `Agent`, `When/Condition`, `Matrix`, `EnvValue`, `Parameter`, `Trigger` - and every element carries
its source line. Jenkins upgrades touch only the AST→IR adapter; GHA schema changes touch only the generator.

### 3. Classify before converting - convertibility is a first-class output

The conversation's "three groups" (direct / policy-driven / manual) became the **step catalog**
(`j2gha/rules/steps.yaml`: `direct`, `policy`, `redesign`, `dynamic`, `noop`, plus `unknown`) and an
**Automated Translation Difficulty** score (0-100) built from the seven weighted dimensions proposed in the
conversation:

| Dimension | Weight |
|---|---:|
| Declarative structure (scripted / `script{}` penalty) | 20 |
| Step mapping coverage (risk-weighted) | 25 |
| Plugin coupling (unknown + plugin-specific steps) | 15 |
| Shared-library opacity | 15 |
| Runtime/environment coupling (labels, docker, k8s, Windows, tools) | 10 |
| Security/identity redesign (credentials, input gates, cloud auth) | 10 |
| Control-flow complexity (dynamic parallel, loops, nesting) | 5 |

plus **hard gates** (dynamic stage generation, dynamic `parallel`, `load`/`evaluate`, `Jenkins.instance`,
opaque library entry points, parse failures) that force at least *significant-redesign*. Classification bands:
0-20 straightforward · 21-45 assisted · 46-70 significant redesign · 71-100 rebuild around intent.

### 4. Generate deterministically; report everything

The generator owns the YAML (no free-form LLM output). Every Jenkins construct produces a report line with
status **mapped / approximated / manual / dropped**, the GHA target and a note. Semantic gaps the conversation
flagged are handled explicitly rather than glossed:

- `agent` → `runs-on` / job `container:` / docker-run wrapper; labels recorded for self-hosted mapping
- stages sharing an agent → steps of one job (shared workspace); parallel/matrix/agent/input stages → jobs + `needs`. Jobs that Jenkins runs in the pipeline agent's one workspace hand it on as a tar artifact (`j2gha-ws-<job>`), so later jobs see the files earlier stages made; a parallel split stays `approximated` (concurrent branches do not see each other's files)
- `post` conditions → status functions scoped to the stage's own step outcomes, anchored on a stage-entry step
- `credentials()` / `withCredentials` → `secrets.*` (never values); `input` → protected environments (with `beforeInput`, a gate job decides `when` first so a skipped stage asks for no approval)
- `build job:` / `copyArtifacts` / changed/fixed/regression post → manual, with the recommended GHA pattern

### 5. Test with differential execution (the "validation pyramid")

The conversation's pyramid - static checks → local Docker → `act` → real GitHub Actions - only becomes useful
with a **comparison oracle**. Raw logs differ; behaviour contracts don't. j2gha's oracle is the **trace**:

1. *Localise* the original Jenkinsfile (AST-range rewrites: agents → `any`, triggers/`@Library` removed; a preamble
   shadows side-effecting steps with script methods that print `J2GHA-TRACE {"stage","step"}`; fake credentials
   and tool installations are provisioned; Jenkins' own error messages drive an auto-repair loop).
2. Run it on the disposable JCasC controller → reference trace.
3. Derive a trace variant of the converted workflow (the same markers per converted step) and run it on act,
   on ephemeral self-hosted runners, or on GitHub-hosted runners.
4. Compare per-stage step sequences (LCS similarity) → *equivalent / differs* with a stage-level diff. Order
   within a stage counts, except for stages whose steps the workflow model shows to run concurrently (matrix
   cells, scripted `parallel` branches, a stage split across jobs). Order *between* stages counts as far as the
   original Declarative pipeline fixes it (`trace.stage_order`, a partial order of stage pairs: stages run in sequence; the branches of a
   `parallel` are mutually unordered but each keeps the order of its own stages; a matrix's inner stages interleave
   across cells), so a converter that runs `Deploy` before `Build` differs;
   scripted pipelines declare no such structure and are compared per stage only. Remote runs merge the job logs
   by runner timestamp to get a real time order. The verdict is *inconclusive* - never counted
   as equivalent - when the traces cannot decide: no events on either side; matching traces but runs that ended
   differently (the difference is outside the markers); a Jenkins reference that did not run, or ran another
   Jenkinsfile version or scenario; or Jenkins failing on the pipeline's own `error` while the converted run did
   not (the branch was decided by runtime values - `sh` output, library results - that trace mode stubs; compare
   such pipelines in `full` mode). Scenarios are pinned on both sides: a branch (`--branch`) and parameter values
   (`--param NAME=VALUE`, declared parameters only). Run records carry the hash of the model that was executed; a model
   edited after `convert` is refused unless `run --edited-model` asks for a mutation test, whose record is never counted.

Trace mode isolates **control-flow fidelity** (when/post/parallel/matrix/script translation) from toolchain and
credential availability - which is why it works on arbitrary third-party Jenkinsfiles. Markers name the stage and
the step *kind*: two different `sh` commands look alike, so trace equivalence is not command or artifact
equivalence. A `full` mode runs real commands against the original repository at the cited commit and compares the
outcome: the overall result and, for failures, the first failing stage (the converted side's failing step mapped to
its stage through the workflow model). It also compares the *outputs* (`j2gha/outputs.py`): the test cases Jenkins'
`junit` recorded against the JUnit reports the converted run uploaded (same cases, same status), and the set of files
`archiveArtifacts` kept against the converted run's artifacts. Files are identified by the path Jenkins archives them
under (relative to the `dir()` the step ran in): the converter records that directory on the upload step and
full-mode variants add a pattern there that matches nothing, so `upload-artifact` - which stores files relative to its
patterns' common directory - uploads them under the same paths. Converted files with one path are copies of one
logical file (matrix cells upload the same path; Jenkins keeps one) and are grouped before comparing, so a copy never
stands in for another Jenkins file; an archive uploaded without the Jenkins paths (a model converted before) is not
compared and makes the comparison inconclusive. Content hashes are
recorded and shown but do not decide the verdict, because builds are not reproducible (archive timestamps,
`BUILD_NUMBER` vs `github.run_number`); for the same reason a path segment that is a side's own `BUILD_TAG`
(`logdir/${BUILD_TAG}/...`) is compared as a placeholder. Collection problems (a failed download, a file over the download cap, an
artifact listing cut short) make a side's evidence incomplete: a difference counts only if the evidence for it is
complete (a missing file needs a complete converted side, an extra one a complete Jenkins side; a test case whose status
changed always counts), otherwise the verdict is *inconclusive*. A Jenkins full-mode reference recorded without
outputs is not used. Infrastructure states (timeouts, cancelled or unstarted runs) and failures
whose stage is unknown are *inconclusive*, as are two outcomes with no stage or job data on either side. Before any run,
every generated workflow also passes structural checks (`validate/contexts.py`: job-level `if` contexts, `needs`
references, expression functions, skipped-dependency handling, one decision per gated stage), so some classes of
conversion bug are caught without executing anything.

#### What the verdicts establish

| Verdict | Establishes | Does not establish |
|---|---|---|
| trace `equivalent` | For this scenario (branch, parameters), the same stages ran the same *kinds* of steps in the same order, and both runs ended the same way. | That the commands, their arguments, outputs, artifacts or secret handling are the same; that other branches or parameter values behave the same; that runtime-decided branches (stubbed in trace mode) go the same way. |
| full `equivalent` | Running the real commands against the original source, both sides ended with the same result, (for failures) failed in the same stage, recorded the same test cases with the same status, and archived the same set of files. | That the archived files have the same content (shown, not counted); that outputs other than archives and JUnit reports (HTML reports, deployments, published packages) are the same; that a failure caused by the local environment is a conversion bug. |
| `differs` | A concrete, reproducible divergence, with the stage it shows up in. | Which side is "right": a divergence can be a conversion bug, a localisation artefact or an environment gap. |
| `inconclusive` | The runs could not be compared (no events, no reference, infrastructure failure, a runtime-decided `error()`). | Anything about the conversion. Never counted as equivalent. |

The workspace hand-off between split jobs (`convert/workspace.py`) has its own boundary. **Reproduced:** every job
on the pipeline agent starts with the files, directories, modes, symbolic and hard links that Jenkins' one workspace
holds at that point, provided concurrent branches change different paths. This is checked by running the generated
steps against a reference model of Jenkins' workspace (seeded pipeline shapes and file system changes, with lost
and corrupt transfers) and end to end. **Approximated by design:** concurrent branches do not see each other's files
while they run, and a path two of them change takes the later branch's version, where Jenkins' result depends on
timing (matrix cells: the later cell by name); timestamp-only changes are not handed on, nor are the cells' changes of a matrix that starts from the checkout (reported). **Refused:** an unreadable entry, a
workspace that did not arrive from a job that ran (a nearest one, or one a skipped job's fallback chain relies on),
and busybox/Alpine job containers (a manual item in the migration report) fail rather than pass. **Warned:** a missing
workspace from a job whose result the restoring job cannot see (one it does not need directly) is taken as skipped. Each converted pipeline's migration report lists these under *Workspace hand-off*.

So the corpus numbers ("15/20 equivalent") count pipelines in which no control-flow difference was found, not
pipelines whose conversion is proven correct. The structural checks have the same character: they rule out known
classes of bug, not all bugs.

**Automation % is an effort estimate.** The conversion report's automation figure is the share of report items the
generator handled, weighted by status (mapped 1.0, dropped 0.8, approximated 0.6, manual 0). It estimates how much of
the migration is left to a person; it is not a measure of correctness (an `approximated` item may still be wrong, and
a `mapped` item is only as right as its rule), and items are not weighted by how much work each one is. Rows that
describe what the converter adds around a Jenkins element (status `info`, e.g. the SCM environment a checkout implies)
are listed in the report but not scored, so adding such a row never moves the figure.

## What the conversation got right, and what changed after research

| Claim in the conversation | Status (research, Oct 2026) |
|---|---|
| GitHub Actions Importer is the baseline comparator | Still published (closed-source image rebuilt 2026-07) but maintenance-mode. It runs locally against the harness controller, but a trial converted 4/15 examples, 3 of them with actionlint errors, and dropped `matrix` stages silently. Not adopted - see `docs/research.md` §5. |
| Use Jenkins' Declarative AST via the controller | Confirmed: `pipeline-model-converter` endpoints exist on Jenkins 2.580.1, POST without crumb. Caveats above. |
| jenkinsfile-runner for headless execution | Effectively unreleased since 2023 (beta-32); a JCasC controller + REST is more reliable. |
| `jdp` Rust parser for triage | Dead since 2020; tree-sitter Groovy grammars are too weak for Jenkinsfiles (tested). |
| `act` for fast local feedback | Still useful but in maintenance mode (v0.2.89, June 2026); breaks with `upload-artifact@v6+`. See `docs/act-evaluation.md`. |
| Real GHA is the final verifier | Yes - and ephemeral **JIT self-hosted runners** give real GitHub orchestration at zero hosted minutes. |
| Monitor minutes | The legacy billing endpoint was retired (2025); the guard uses the enhanced billing usage API of the target repository's owner (user or organization) and refuses when only an incomplete jobs-API tally is available. |
