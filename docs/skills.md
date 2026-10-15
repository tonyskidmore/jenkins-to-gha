# Agent skills

Everything an AI agent does in this repository goes through the `j2gha` CLI. The skills in `.claude/skills/` tell
the agent how to drive it, what to read afterwards and what not to do. The agent can be Claude Code or GitHub Copilot;
Copilot reads the same directory ([copilot.md](copilot.md)). None of them is required:
the commands in [usage.md](usage.md) run the same stages by hand (what needs an agent: [AI.md](AI.md)). Each skill is a directory with a
`SKILL.md` (frontmatter `name`, `description`, `argument-hint`, then the instructions), and optionally `scripts/`,
`references/`, `assets/` and `evals/`.

## The chain

The skills form a chain from "find a real pipeline" to "a converted workflow compared against a successful run":

```
jenkins-example-crawler  ->  jenkins-to-gha  ->  jenkins-example-twin  ->  jenkins-to-gha (full mode)
        (examples/0NN)        (analyse, convert,       (examples/1NN:          (Jenkins vs act / self-hosted /
                               validate, trace runs)    a runnable copy)        hosted, outputs compared)
                                      |
                                      v
                            j2gha-rule-improver  (one conversion-rule change per branch, judged by the scoreboard)

jenkins-docs, gha-docs: reference lookups the others call on when a step's semantics are in doubt
narrated-explainer:     videos about the above; not part of the chain
hyperframes-walkthrough: 60 s videos with live footage of an example's Jenkins and GitHub Actions runs; not part of the chain
```

Trace mode compares control flow and works on any Jenkinsfile; full mode compares real runs and needs a pipeline
that can finish here, which is what the twin step provides. A *differs* verdict on a twin with a stated cause is the
input to the rule improver.

## jenkins-example-crawler

`/jenkins-example-crawler <count> [--owner org-or-user ...] [--styles style ...] [--allow-unlicensed]`

Adds `<count>` scored, cited real-world pipelines from github.com as `examples/0NN/` (`Jenkinsfile` verbatim,
`README.md` with the citation, classification and score, `source.json` with the provenance). It searches by
pipeline style (declarative, scripted, matrix, parallel, docker/kubernetes agents, shared libraries, input gates,
credentials, parameters, downstream builds, dynamic Groovy, Windows, tools), or walks one owner's repositories,
parses every candidate with Jenkins' own Groovy, and picks round-robin over the styles the corpus lacks. New ids
stay below 100: `1NN` belongs to the twins. Needs `gh auth` and the `j2gha/jenkins:local` image.

## jenkins-to-gha

`/jenkins-to-gha <example ids | all> [--tier jenkins,act,selfhosted,hosted] [--mode trace|full]`

Runs the harness stages on examples: `analyze` (Groovy AST from Jenkins' own jar, findings, difficulty),
`convert` (the workflow, `gha/workflow.model.json`, the migration report), `validate` (actionlint, zizmor, policy)
and `run` (the localised Jenkinsfile on the disposable controller against the converted workflow on act, on
ephemeral self-hosted runners at zero minutes, or on GitHub-hosted runners behind the minutes budget guard, which
needs the user's approval each time). Explains the verdicts: *equivalent* means no difference was found for that
scenario, *differs* names the stage, *inconclusive* could not be compared. Also `summary`, `scoreboard`, `budget`.

## jenkins-example-twin

`/jenkins-example-twin <example id> [--branch B] [--param NAME=VALUE] [--tiers jenkins,act[,selfhosted]]`

Makes an example run to completion in full mode by creating its *twin*, `examples/1NN/`: a copy of
`examples/0NN/Jenkinsfile` with the fewest edits that let the pipeline finish on the harness's Jenkins (commands
that need Erlang, a Docker daemon, a cloud account or a private host replaced by stand-ins that write the same
files later steps stash, archive or report), every edit marked `j2gha-local:` in the file and listed in
`LOCAL.md` with its reason, the scenario and the results per tier. The cited Jenkinsfile is never edited; the twin
is the executable reference, the original keeps the citation and the conversion scores. The skill first runs the
original in full mode and separates harness faults (a crash before any stage on a stub value, an undetected
credential, a missing plugin: fixed in the harness, with a test) from genuine environment needs (a twin). It ships
`scripts/mk_twin.py` (creates the twin directory, `source.json` with `derived_from`, the README note),
`scripts/twin_results.py` (appends each tier's verdict to `LOCAL.md`), `references/full-mode-semantics.md` (what
the harness stubs and runs for real, what is on the images, how to read a failed run) and
`references/local-md-template.md`.

## j2gha-rule-improver

`/j2gha-rule-improver [step name]`

Proposes one conversion-rule change for the highest-cost unmapped Jenkins step (`j2gha gaps`): a `rules/steps.yaml`
catalog entry, the generator code and tests, grounded in the local documentation bundles and checked with
`scoreboard --check` (no regression against `evals/baseline.json`) and `guard` (no change to protected files). It
works on a branch and never edits `evals/`; a human decides the merge. See `docs/extending.md` and
`docs/self-improvement.md`.

## jenkins-docs and gha-docs

`/jenkins-docs [step | directive | question] [--fetch]`, `/gha-docs [topic | question] [--version fpt|ghec|ghes-X.Y] [--fetch]`

Read the documentation bundles under `.docs/` (`uv run j2gha docs fetch jenkins|gha`, never committed): the
Jenkins bundle is pinned to the controller's version and plugin set, the GitHub Actions bundle to a product
version. They answer "what does this step do, which plugin provides it, what is the GitHub equivalent and its
limits" with citations, and fall back to the web when no bundle exists. The harness itself never reads the
bundles; the migration report's references are web URLs. See `docs/documentation.md`.

## narrated-explainer

`/narrated-explainer <source doc or topic> [--chapter name] [--engine kokoro]`

Builds the narrated walkthrough videos in `docs/video/` from a document: a scene script, replayed terminal output,
local text-to-speech, captions, an mp4 through headless Chrome and ffmpeg. Unrelated to running the harness.

## hyperframes-walkthrough

`/hyperframes-walkthrough <example id> [--slug name]` · `hfw publish <video> --tag videos`

Makes the 60-second walkthrough of an example with HyperFrames: four acts (Jenkins baseline, analyse/convert/validate,
differential trace, real GitHub Actions) where acts 1 and 4 play **live screen captures** of the actual Jenkins build
(inputs answered on camera) and of a self-hosted GitHub Actions run, cut to fit with labelled speed-ups. Narration
reuses narrated-explainer's Kokoro runtime. The examples/000 video is the reference project; a video's inputs live in
`docs/video/<slug>/`, everything generated in `.cache/video/<slug>/`. The GitHub capture needs a browser profile the
user signs in to by hand (outside the repo, read-only during capture) and the user's approval per run, because it
pushes a branch and creates a workflow run. Finished videos (from either video skill) are stored as GitHub release
assets with `hfw publish` (dry run unless `--yes`), never in git.

## Conventions shared by the skills

- Check prerequisites rather than assume them: Docker and the harness images, `gh auth`, `uv sync`.
- The Jenkins controller is single-user (`.j2gha/jenkins.lock`): one `run`/`analyze` at a time.
- Generated directories (`analysis/`, `gha/`, `runs/`) are never hand-edited; the cited `examples/0NN/Jenkinsfile`
  is never edited; `evals/` is human-owned.
- A skill reports what the harness measured and what it does not establish (a hollow green, an act fault, a
  difference caused by the environment) in the same breath as the verdict.
