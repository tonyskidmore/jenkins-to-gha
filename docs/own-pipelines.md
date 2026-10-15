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

Keep your pipelines in a directory **outside the clone**, and point `J2GHA_PIPELINES_DIR` at it. Each pipeline then
gets a subdirectory there, and everything the stages write for it goes there too: `analysis/`, `gha/`, `runs/` and its
`README.md`. None of it is in this repository's working tree, so none of it can be committed by accident.

```bash
export J2GHA_PIPELINES_DIR=~/j2gha-pipelines              # or pass --pipelines-dir DIR to each command
uv run j2gha add /path/to/payments/Jenkinsfile            # -> ~/j2gha-pipelines/payments/Jenkinsfile
uv run j2gha add /path/to/payments/Jenkinsfile.deploy     # -> payments-jenkinsfile-deploy
uv run j2gha add ci/build.groovy --name billing-build     # choose the name yourself
uv run j2gha pipeline payments                            # analyse, convert, validate, then a trace run on Jenkins and act
```

**What `add` does.**

- It copies the file in as `<name>/Jenkinsfile`; the file can have any name.
- The default name is the file's directory, plus the file name when that is not `Jenkinsfile`.
- A name is letters, digits, `-` and `_`. It is never all digits, because numbers are corpus ids.
- Re-adding a changed file needs `--force`. The later stages notice the change and re-analyse.
- You can also create `<name>/Jenkinsfile` in the directory by hand.

**Running the stages.**

- **One at a time.** Use `uv run j2gha analyze payments`, then `convert`, `validate` and
  `run payments --tier jenkins,act`. Each stage can be re-run on its own.
- **`all` is your pipelines.** With `J2GHA_PIPELINES_DIR` set, `all` (and a command given no ids) means every pipeline
  in that directory, e.g. `uv run j2gha pipeline all`.
- **The corpus is still reachable.** Corpus ids such as `003` still find the corpus example when your directory has no
  pipeline of that name.
- **Common gaps.** `uv run j2gha gaps` ranks the steps the converter could not map, across your pipelines.
- **An index of them all.** `uv run j2gha summary` writes `$J2GHA_PIPELINES_DIR/README.md`, one row per pipeline:
  dialect, difficulty, hard gates, automation, validation and run results.

**Without `J2GHA_PIPELINES_DIR`.** Pipelines go under the clone's `examples/` (`add` warns about it). That directory is
tracked, and this repository is public, so use it only for pipelines you could publish.

## What leaves your machine

| Stage | Network | What it sends |
|---|---|---|
| `analyze`, `validate` | None. The parser, actionlint and zizmor run in containers with no network access. | Nothing. |
| `convert` | The GitHub API, when a GitHub token is available (`GH_TOKEN`, `GITHUB_TOKEN` or `gh auth token`) | Only the names and versions of the public actions the workflow uses, to pin them to commit SHAs. Without a token, actions keep their version tags. [Offline](#offline-mode), only lookups already cached are used. |
| `run --tier jenkins,act`, trace mode (the default) | Local Docker. act downloads each action the first time it is used. | Nothing from the pipeline. Trace mode replaces `sh`, `bat` and the other steps with trace markers, so the pipeline's commands do not run. Groovy in `script {}` blocks does run, on the local Jenkins. |
| `run --mode full` | | Not available for a private pipeline (see [below](#can-i-run-the-real-commands)). |
| `run --tier selfhosted`, `--tier hosted` | GitHub | **The converted workflow:** its stage names, commands and comments are pushed to the repository in `J2GHA_REPO`, and run logs and artifacts stay in that repository's Actions history. For any pipeline that is not a corpus example, the harness refuses these tiers unless `J2GHA_REPO` names a repository GitHub reports as private (or internal). The default, your clone's `origin`, is this public repository if you cloned it. The local tiers in the same command still run. |

An AI assistant is separate from all of this, and what it sends depends on the assistant. For GitHub Copilot, see
[copilot.md](copilot.md#working-with-private-pipelines).

### Offline mode

Set `J2GHA_OFFLINE=1`, or pass `--offline` to a command, and the harness itself makes no GitHub API calls and
fetches nothing:

```bash
export J2GHA_OFFLINE=1
uv run j2gha pipeline payments          # analyse, convert, validate, Jenkins and act trace runs: all still work
```

- **`convert`** pins only the actions whose commit SHA is already in the lookup cache (`.cache/`, kept for 7 days).
  The rest keep their version tag, which it reports. Convert again online later to pin them.
- **The remote tiers are refused**, as is a full-mode run that would fetch a source repository. The local tiers in the
  same command still run.
- **Commands that exist to go online fail with a clear message:** `docs fetch`, `crawl`, `budget`, `environments`.

**What offline mode does not cover:**

- Docker image pulls, during `docker build` or for a `docker` agent;
- act's first download of each public action a workflow uses. Run a workflow once while online, or build the images on
  a connected machine, and later runs reuse the cache.

These carry nothing from your pipelines.

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

In the pipeline's directory (`$J2GHA_PIPELINES_DIR/<name>/`):

| File | What it holds |
|---|---|
| `README.md` | Each stage's summary. The analysis section has a collapsed *Difficulty dimensions* table, with the hard gates under it. |
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
  holds a whole `pipeline {}`. One can be analysed and converted on its own: `uv run j2gha add vars/<name>.groovy`.
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

**Not for a private pipeline.** Full mode (`uv run j2gha run payments --mode full`) runs the pipeline's real commands
against its source code.

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
