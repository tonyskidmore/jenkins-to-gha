# Converting your own pipelines

The corpus in `examples/` is made of public Jenkinsfiles. This page is for converting any other pipeline, especially
one that is not public: your own, or your organisation's. It covers:

- where to put the pipeline so it stays out of git;
- what the harness sends off your machine;
- how to read the results;
- what the harness cannot do yet with shared libraries and plugins.

It assumes the [prerequisites](prerequisites.md) are met and `uv run j2gha docker build` has been run. Run every command
from the root of your clone. To see every stage on one pipeline first, follow the [walkthrough](../examples/000/README.md).

## Set up a pipeline

Each pipeline needs its own directory under `examples/`:

- **Name, not number.** Numbered directories are the corpus.
- **One `Jenkinsfile`.** It must be called exactly that. Copy a pipeline stored under another name (`Jenkinsfile.deploy`,
  `ci/build.groovy`) in as `Jenkinsfile`, one directory per pipeline.

```bash
mkdir examples/my-pipeline
cp /path/to/Jenkinsfile examples/my-pipeline/
printf 'examples/my-pipeline/\n' >> .git/info/exclude   # keep it out of git
uv run j2gha pipeline my-pipeline        # analyse, convert, validate, then a trace run on Jenkins and act
```

- **Keep private pipelines out of git.** `examples/` is tracked, and this repository is public. `.git/info/exclude`
  works like `.gitignore` but is never committed, so it stays in your clone. Afterwards, check with `git status` that
  the directory no longer shows. Do not push a clone or fork that contains a private pipeline.
- **Run the stages one at a time.** Use `uv run j2gha analyze my-pipeline`, then `convert`, `validate` and
  `run my-pipeline --tier jenkins,act`. Each stage can be re-run on its own.
- **Several pipelines.** Name each one, e.g. `uv run j2gha pipeline app-a app-b`. `all` and `summary` cover only the
  numbered corpus.
- **Common gaps across them.** `uv run j2gha gaps app-a app-b` ranks the steps the converter could not map, across the
  pipelines you name.

## What leaves your machine

| Stage | Network | What it sends |
|---|---|---|
| `analyze`, `validate` | None. The parser, actionlint and zizmor run in containers with no network access. | Nothing. |
| `convert` | The GitHub API, when a GitHub token is available (`GH_TOKEN`, `GITHUB_TOKEN` or `gh auth token`) | Only the names and versions of the public actions the workflow uses, to pin them to commit SHAs. Without a token, actions keep their version tags. |
| `run --tier jenkins,act`, trace mode (the default) | Local Docker. act downloads each action the first time it is used. | Nothing from the pipeline. Trace mode replaces `sh`, `bat` and the other steps with trace markers, so the pipeline's commands do not run. Groovy in `script {}` blocks does run, on the local Jenkins. |
| `run --mode full` | | Not available for a private pipeline (see [below](#can-i-run-the-real-commands)). |
| `run --tier selfhosted`, `--tier hosted` | GitHub | **The converted workflow:** its stage names, commands and comments are pushed to the repository in `J2GHA_REPO`. That defaults to your clone's `origin`, which is this public repository if you cloned it. Run logs and artifacts stay in that repository's Actions history. For a private pipeline, use these tiers only with `J2GHA_REPO` set to a private repository you control. |

An AI assistant is separate from all of this, and what it sends depends on the assistant. For GitHub Copilot, see
[copilot.md](copilot.md#working-with-private-pipelines).

## Read the results

`pipeline` prints two summary lines. Example 017, a public pipeline that loads a shared library:

```text
[j2gha] 017: declarative      difficulty  46 (significant-redesign), coverage 82.8%, convertibility partial
[j2gha] 017: 9 job(s); mapped 29, approx 53, manual 98 -> automation 34.5%
```

- **difficulty:** a 0-100 estimate of the migration effort, and its band. How it is built, and how to read it:
  [scoring.md](scoring.md#migration-difficulty-0-100).
- **coverage:** the share of the pipeline's steps the step catalog can map, weighted by risk.
- **convertibility:** one of three values.
  - `automatic`: score of 45 or less, with no hard gate.
  - `partial`: a hard gate, a scripted pipeline, or a score above 45.
  - `report-only`: the behaviour is in a library call, or the file did not parse. The pipeline is reported, not
    converted.
- **mapped, approx, manual → automation:**
  - The counts are the migration report's items: mapped, approximated, manual (and dropped).
  - *Automation* weights them: mapped 1, dropped 0.8, approximated 0.6, manual 0.
  - It estimates the conversion effort. It does not measure correctness.

| File | What it holds |
|---|---|
| `examples/<name>/README.md` | Each stage's summary. The analysis section has a collapsed *Difficulty dimensions* table, with the hard gates under it. |
| `analysis/analysis.json` | Findings, step inventory, unknown steps, and the score's dimensions and gates (`complexity`) |
| `gha/workflow.yml` | The draft workflow |
| `gha/migration-report.md` | Every Jenkins construct with its source line, its status (mapped, approximated, manual, dropped) and its GitHub Actions target |
| `gha/validation.json` | actionlint, zizmor and policy findings |
| `runs/` | Run records and the harness's test variants of the workflow, which have fake credentials. Do not copy from here. |

### Why is my pipeline rated significant-redesign?

**Usually because of a hard gate.** A gate is a construct that j2gha treats as needing redesign, and any gate raises the
score to at least 46, which is the significant-redesign band. Open *Difficulty dimensions* in the pipeline's README: the
gates are listed under the table.

**`SharedLibrary` is a common one** where steps are shared through libraries. It applies to a pipeline that loads a
shared library and calls any step j2gha does not recognise.

- j2gha cannot see inside the library, so each such step also adds to step mapping, plugin coupling and library
  opacity.
- Example 017 shows the effect: its dimensions add up to 39 (assisted), and one unknown step lifts it to 46 through
  the gate.
- A rating like that measures what j2gha could not see as much as the pipeline itself. Read the dimensions before the
  band.

[scoring.md](scoring.md#migration-difficulty-0-100) lists every gate and dimension.

## Shared libraries

What j2gha does with them today:

- **Detection.** It detects `@Library`, `library(...)` and `libraries {}`.
- **Conversion.** A call to a library step, such as `deployTo(...)`, is an unknown step. The converted workflow gets a
  placeholder step that prints a warning, and the migration report lists the call as manual.
- **Runs.** In runs the step is stubbed, so the trace shows that it was called, not what it did.
- **The library itself is not read.** That is a [known limitation](architecture.md#known-limitations-and-where-to-extend).
- **Pipeline templates are the exception.** A library pipeline template is a `vars/<name>.groovy` file whose `call()`
  holds a whole `pipeline {}`. One can be analysed and converted on its own: copy it in as a pipeline's `Jenkinsfile`.
  Examples 005 and 011 are templates. Other library files analysed this way are reported, not converted.

## Missing Jenkins plugins

The harness's Jenkins has a fixed set of plugins, listed in `docker/jenkins/plugins.txt`. Suppose the pipeline uses a
Declarative agent, option, trigger or parameter type from a plugin that is not in that list. Jenkins rejects the
pipeline, and the analysis reports a `JenkinsValidationFailed` finding. That finding is about the harness, not your
pipeline. To add the plugin:

1. Add its bare name to `docker/jenkins/plugins.txt`.
2. Run `uv run j2gha docker build --only jenkins`.
3. Paste the `+ name:version` lines the build prints into `plugins.txt`, so the version is pinned.
4. Re-run `uv run j2gha analyze <name>`.

Tools named in `tools {}` need no change: they are installed per pipeline.

## Can I run the real commands?

**Not for a private pipeline.** Full mode (`uv run j2gha run my-pipeline --mode full`) runs the pipeline's real
commands against its source code.

- The source is fetched anonymously from the *public* repository and commit named in a `source.json`:
  `{"repository": {"full_name": "owner/repo"}, "snapshot_commit": "<commit sha>"}`.
- So private repositories are not supported.
- Credentials are always fakes.

Trace mode, which compares control flow, works on any Jenkinsfile.

## Using the converted workflow

1. Copy `gha/workflow.yml` into the target repository's `.github/workflows/`.
2. Work through the migration report:
   - review every approximated and manual item;
   - create the secrets it lists;
   - add required reviewers to the environments that replace `input` gates;
   - set or replace any `vars.J2GHA_WHEN_L<line>` variables. These are conditions the converter could not translate.
3. Do not copy anything from `runs/`.

Every converted workflow needs a person's review. An *equivalent* trace verdict means only that no difference was
found in the scenario that was run ([mechanism.md](mechanism.md#what-the-verdicts-establish)).

## Help from an AI assistant

The CLI needs no AI agent. The skills in `.claude/skills/` let an agent drive the CLI and explain its outputs, and
both Claude Code and GitHub Copilot read them.

- What each skill does: [skills.md](skills.md).
- Using Copilot, including settings for private pipelines and local models: [copilot.md](copilot.md).
