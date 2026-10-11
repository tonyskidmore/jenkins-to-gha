---
name: jenkins-example-twin
description: Make a corpus example run to completion in the j2gha harness by creating its local twin (examples/1NN, a minimally edited copy of examples/0NN with a LOCAL.md listing every edit), so that full mode has a successful Jenkins reference to compare the converted workflow against. Use this whenever a full-mode run of an example fails on things the harness cannot provide (toolchains, Docker, cloud services, private repositories, shared libraries) rather than on a conversion problem, whenever someone asks to "fix", "localise", "make runnable", "twin" or "get a green run" for an example or for the whole corpus, or right after crawling a new example to give it an executable reference. Not for editing the cited Jenkinsfile in place (never do that) and not for conversion-rule changes (j2gha-rule-improver).
argument-hint: "<example id> [--branch B] [--param NAME=VALUE] [--tiers jenkins,act[,selfhosted]]"
---

# Jenkins example twin

The corpus keeps every cited Jenkinsfile verbatim (`examples/0NN/Jenkinsfile`): that is what the converter is
measured on. Most of those pipelines cannot run here as they are (no Erlang, no Docker daemon, no AWS account),
so full mode, which compares real runs, had nothing to compare. A *twin* is a copy under `examples/1NN/` with the
fewest edits that let the pipeline finish on the harness's Jenkins, each edit marked in the file and explained
in `LOCAL.md`. The twin is the executable reference; the original keeps the citation and the conversion scores.

A good twin changes **what commands run**, never **how the pipeline is shaped**: the stages, `when` gates,
`parallel`/`matrix`, `post`, stash/archive/junit steps, credentials wrappers, parameters and options stay, and
the replacement commands write the same files the later steps read, stash, archive or report, so the outputs
comparison has something real to compare. A twin that stubs everything proves nothing; say so if that is all a
pipeline allows.

## Arguments

`$ARGUMENTS`: the example id (`009`), optionally the scenario to run (`--branch`, `--param NAME=VALUE`) and the
tiers (`--tiers jenkins,act` by default; add `selfhosted` for a real-GitHub confirmation at zero minutes).

## Prerequisites (check, do not assume)

- The harness images exist (`docker image inspect j2gha/jenkins:local j2gha/act-runner:local j2gha/runner:local`)
  and `uv sync` has run. The Jenkins controller is single-user: never run two `j2gha run`/`analyze` at once.
- The example has been analysed (`examples/0NN/analysis/`). If not: `uv run j2gha analyze 0NN`.
- Read `references/full-mode-semantics.md` first: it says what the harness already stubs, what runs for real,
  what is on the images and how to read a failed run. Half of the edits people reach for are unnecessary
  because the localiser already does them, and the other half fail because of something listed there.

## Procedure

### 1. Decide whether a twin is needed

Run the original in full mode on Jenkins only, then read what happened:

```bash
uv run j2gha run 0NN --tier jenkins --mode full [--branch B] [--param NAME=VALUE]
```

- `SUCCESS`: no twin. Run the converted side (`--tier act` or `selfhosted`) and record the result; stop.
- A failure **before any stage** with `J2ghaAny`/`j2gha-stub` in a `ClassCastException`, a `Could not find
  credentials entry`, `No such DSL method`, or a missing plugin wrapper: that is a **harness gap**, not a
  pipeline need. Fix it in the harness (localiser stub lists, credential detection, `docker/jenkins/plugins.txt`)
  with a unit test, re-run, and only then decide about a twin. The twin must not paper over harness bugs.
- A failure on a command the environment cannot run (`erl: not found`, `Cannot connect to the Docker daemon`,
  `Could not resolve host`, a private registry, an unreachable git host, a test that needs a service): a twin.
- The pipeline's own `error()` on a stubbed value (`Failure while retrieving AWS account ID`, `Missing package:
  openam-null`): a twin that gives the check a literal stand-in result.

Note the failing stage, the exact command, and everything after it that would fail next (read the Jenkinsfile
to the end: a twin that fixes the first failure and runs into the second wastes a run).

### 2. Design the edit list before touching anything

For every stage, classify each command: runs here as-is / needs a stand-in / needs a literal value. Then decide
the stand-ins so that:

- every file a later `stash`, `unstash`, `archiveArtifacts`, `junit`, `publishHTML`, `readFile` or `fileExists`
  expects is created (a tarball name the pipeline computes, a `TEST-*.xml` with one or two cases written with
  `printf`, a `dist/` file). Check the archive and junit patterns against what you write;
- the original command text stays visible: prefer `echo <original command>` or the same command against a local
  stand-in (a `file://` git remote with tags, a listing echoed in the real tool's format) over deleting a step;
- control flow is preserved: a library result that decides a branch gets `output = [status: 0, stdout: '...']`
  right before the test; a job-configuration variable the harness cannot set gets a literal at the top of the
  script (or, for scripted pipelines, a `properties([parameters([...])])` block so `--param` works and the
  converter emits inputs). Pick values that take the path worth testing and say which path in LOCAL.md;
- wide fan-outs stay (a 26-cell matrix is the point), but each cell does seconds of work;
- nothing publishes, pushes to a real remote, or needs a real credential. Network: GitHub and public registries
  only (`npm ci` from registry.npmjs.org and Maven Central are fine; a real `mvn -DskipTests install` or `npm
  ci && npm run test-unit` of a small project is a *good* twin: 116 and 115 do that).

Things that are not edits: Docker/label/kubernetes agents (localised), `@Library` and library calls (stubbed),
`withCredentials` and `credentials()` (faked), `build job:` (stubbed), `input` (approved), `options {}`.

When a step's Jenkins semantics are unclear (what `stash` does with no files, what `archiveArtifacts` excludes
by default, whether `dir()` creates the directory), check the local Jenkins documentation through the
`jenkins-docs` skill (`uv run j2gha docs path jenkins`) rather than guessing; the harness's Jenkins is the
version that bundle documents.

### 3. Create the twin

```bash
uv run python .claude/skills/jenkins-example-twin/scripts/mk_twin.py 0NN 1NN
```

This copies the Jenkinsfile and `source.json` (with `id` and a `derived_from` field), and renders the README
with a note that the Jenkinsfile is not verbatim. Then edit `examples/1NN/Jenkinsfile`:

- mark every changed or inserted line with a trailing `// j2gha-local: <reason>` (Groovy) or `# j2gha-local:
  <reason>` inside shell text. A line that ends in a shell continuation (`\`) cannot carry a trailing marker:
  put it on the line above; a `sh """#!/bin/bash` opener cannot either (the shebang must stay first), so put
  it on the line below as a shell comment;
- keep edits in place (same stage, same step), one `sh` per original `sh` where the trace shape matters;
- for a multi-line `sh '''...'''`, edit inside the block; dash runs it (`#!/bin/bash` shebangs are honoured).

### 4. Write `LOCAL.md`

Follow `references/local-md-template.md`: the edit table, what stays unchanged, what the twin tests, the expected
converted-side outcome, the scenario line. Write it before running: it is the design, and the run checks it.

### 5. Analyse, convert, validate, then run

```bash
uv run j2gha analyze 1NN && uv run j2gha convert 1NN && uv run j2gha validate 1NN
uv run j2gha run 1NN --tier jenkins,act --mode full [--branch B] [--param NAME=VALUE]
```

Before running, look at `examples/1NN/gha/workflow.yml` for what the converted side will do with your edits:
a `${...}` left in shell text, a `docker run` wrapper around a step, a job whose `if:` reads an env nothing
sets. That tells you the expected converted-side outcome to write down (and whether a *differs* there is the
converter's finding or your edit's).

Iterate on the Jenkins side until it is `SUCCESS` (read `runs/jenkins-full/console.log` and the `attempts` in
`result.json` after each run); do not iterate on the converted side by editing the twin unless the failure is
caused by an edit. If act fails with its bare `<nil>` error on a `docker cp` (wide matrices), use `--tier
selfhosted` instead. When a run exposes a harness gap (an undetected credential, a stub missing), fix the
harness, not the twin.

### 6. Record and report

```bash
uv run python .claude/skills/jenkins-example-twin/scripts/twin_results.py 1NN --note "<why the verdicts>"
uv run j2gha summary
```

`twin_results.py` appends the Jenkins result and each tier's verdict, with JUnit and archive counts and the run
URL, to `LOCAL.md`. Then report: the edit table in one or two lines per edit, the verdict per tier, and what the
twin establishes (a real build compared on both sides; a converter gap stated reproducibly; or a hollow green).
If a converter gap showed up, name it in the report so it reaches the rule-improvement worklist.

## What to avoid

- Editing `examples/0NN/Jenkinsfile`: the citation says "copied verbatim" and the scoreboard is keyed on it.
- Deleting steps, stages, `when` gates or `post` blocks to get green: the twin stops testing the thing the
  example was chosen for. Replace command text; keep structure.
- Hiding a converter finding: if the original's full run found a real conversion difference (004's `TAG_NAME`
  branch), the twin must keep that line exactly as it is.
- Adding steps the original does not have (an extra `archiveArtifacts` to give the comparison something): allowed
  only when LOCAL.md says so, and never silently.
- Printing fake secrets: `echo` of a command that carried `-u $USER:$PASS` should drop the credential part.
