# jenkins-to-gha

Convert Jenkins pipelines to GitHub Actions, then check each conversion by running the original and the converted
workflow and comparing what they do.

`j2gha` parses a Jenkinsfile with Jenkins' own Groovy and converts it deterministically into a GitHub Actions workflow,
with a report of everything it could not map. It validates the workflow, then runs the original on a disposable local
Jenkins and the conversion on act or real GitHub runners, and compares the two runs stage by stage.

> [!WARNING]
> **This is a prototype (a proof of concept), not a production migration tool or reference implementation.** It was
> built to test an idea against 20 public Jenkinsfiles. Converted workflows need a person's review, and an *equivalent*
> verdict means no difference was found in the runs compared, not that the conversion is correct. It runs third-party
> build scripts in local containers and a local Jenkins with pre-approved scripts: see the
> [security posture](docs/architecture.md#security-posture).

It started from one idea: use a disposable Jenkins set up with JCasC (Jenkins Configuration as Code), and act, which
runs GitHub Actions workflows locally, as the basis for automating the comparison. It grew from there: see
[docs/mechanism.md](docs/mechanism.md) for the approach and [docs/AI.md](docs/AI.md) for how it was built.

## Watch

[![60-second overview on YouTube](https://img.youtube.com/vi/eM67fInxk7k/hqdefault.jpg)](https://www.youtube.com/watch?v=eM67fInxk7k)

The [60-second overview](https://www.youtube.com/watch?v=eM67fInxk7k), and a
[five-chapter walkthrough](https://www.youtube.com/playlist?list=PLD_4eoDDE3Rk) (about 23 minutes) of example 000.
Downloads and what each chapter shows: [docs/walkthrough-videos.md](docs/walkthrough-videos.md).

## Getting started

You need Docker, Python 3.10+ with [uv](https://docs.astral.sh/uv/), and git; the GitHub tiers also need the GitHub CLI
and a repository you administer. Details: [docs/prerequisites.md](docs/prerequisites.md).

```bash
git clone https://github.com/tonyskidmore/jenkins-to-gha.git
cd jenkins-to-gha
uv sync                      # install the harness
uv run j2gha docker build    # build the Jenkins, act and runner images (once; several minutes, about 10 GB)
```

Then follow the hands-on [walkthrough](examples/000/README.md): it takes one realistic pipeline from Jenkins to
GitHub Actions through every stage, and everything it writes is gitignored. Running the corpus and the other commands
is covered in [docs/usage.md](docs/usage.md). No AI agent or LLM API key is needed; the Claude Code skills are
optional ([docs/AI.md](docs/AI.md)).

## How it works

1. **Analyse:** parse with Jenkins' Groovy into a typed model; score the migration difficulty.
2. **Convert:** generate the workflow and a migration report (mapped, approximated, manual, dropped).
3. **Validate:** actionlint, zizmor and the project's own policy checks.
4. **Run and compare:** Jenkins against act locally, or against real GitHub Actions on self-hosted or GitHub-hosted
   runners (behind a minutes budget guard).

## The example corpus

- **`examples/000`:** the hand-written walkthrough.
- **`examples/001`-`020`, the originals:** 20 real-world Jenkinsfiles found on GitHub, each cited and never edited.
- **`examples/1NN`, the twins:** `1NN` is a minimally edited copy of original `0NN`, made so that the pipeline runs to
  completion on the local Jenkins, with every edit listed in its `LOCAL.md`. Most originals need private services,
  credentials or other nodes, so with their real commands they can only fail; a twin gives full mode a successful
  Jenkins run to compare against. 16 of the 20 originals have one.

In trace mode (control flow), 15 of the 20 originals' conversions matched Jenkins on act and on GitHub-hosted runners,
2 were inconclusive and 3 differed, all three on pipelines that build stages at run time. In full mode (real
commands), 12 of the 16 twins' conversions showed no difference from the successful Jenkins run on real GitHub
Actions; the other 4 differ where the converter reports manual work. Each example's README links its reference runs on
GitHub Actions. Index: [examples/README.md](examples/README.md); details: [docs/results.md](docs/results.md).

## Documentation

| Topic | Document |
|---|---|
| Prerequisites, commands, Actions minutes | [prerequisites.md](docs/prerequisites.md), [usage.md](docs/usage.md) |
| Approach and design | [mechanism.md](docs/mechanism.md), [architecture.md](docs/architecture.md) |
| Results and limitations | [results.md](docs/results.md), [architecture.md](docs/architecture.md#known-limitations-and-where-to-extend) |
| Adding conversion rules | [extending.md](docs/extending.md), [self-improvement.md](docs/self-improvement.md) |
| Agent skills and AI | [skills.md](docs/skills.md), [AI.md](docs/AI.md) |
| Background research | [research.md](docs/research.md), [act-evaluation.md](docs/act-evaluation.md), [tooling.md](docs/tooling.md), [documentation.md](docs/documentation.md) |

## Feedback

Questions and bug reports are welcome as GitHub issues. Report security problems privately, as described in
[SECURITY.md](SECURITY.md).

## Licence

MIT, see [LICENSE.md](LICENSE.md), except for the example corpus: each crawled Jenkinsfile, its twin and the files
derived from them stay under the licence of the repository they came from. Details, with a copy of each licence:
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
