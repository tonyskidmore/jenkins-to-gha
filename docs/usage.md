# Using the CLI

The commands below assume the [prerequisites](prerequisites.md) are met and `uv sync` and `uv run j2gha docker build`
have been run. The full list of commands and options is in `uv run j2gha --help` and in [CLAUDE.md](../CLAUDE.md#commands).
What each stage does is in [architecture.md](architecture.md#stages). Run every command from the root of your clone
of this repository.

## Convert your own pipeline

Keep your pipelines in a directory outside the clone, add each Jenkinsfile (any file name), and run the stages:

```bash
export J2GHA_PIPELINES_DIR=~/j2gha-pipelines
uv run j2gha add /path/to/payments/Jenkinsfile    # -> ~/j2gha-pipelines/payments/Jenkinsfile
uv run j2gha pipeline payments                    # analyse, convert, validate, then a trace run on Jenkins and act
```

[own-pipelines.md](own-pipelines.md) covers the rest. Read it before using a pipeline that is not public:

- the pipelines directory, `j2gha add`, and its index (`j2gha summary`);
- offline mode (`J2GHA_OFFLINE=1`);
- what each stage sends off your machine;
- how to read the results and the difficulty score;
- shared libraries and missing plugins;
- full mode;
- using the converted workflow.

## Grow and run the corpus

```bash
gh auth status                            # GitHub token used for code search and remote runs
uv run j2gha crawl --count 10             # add 10 scored, cited examples to examples/NNN
uv run j2gha pipeline all                 # analyze -> convert -> validate -> run (jenkins + act, trace mode)
uv run j2gha summary                      # corpus index: examples/README.md
```

`all` means every numbered example: the crawled originals (`001`-`020`) and their twins (`1NN`, minimally edited copies
that run to completion on the local Jenkins; see [results.md](results.md#twins-full-mode-against-a-successful-jenkins-reference)).
To repeat the originals' trace results on act from [results.md](results.md), run `uv run j2gha pipeline 1-20`.

Each stage writes its results into the example's `README.md`, `analysis/`, `gha/` and `runs/`. These are committed for
the corpus examples, so running them changes tracked files: `git restore examples/` puts back the committed versions
(it also discards any other uncommitted edits there, and leaves new files in place). The walkthrough, `examples/000`,
writes only gitignored files.

Or use the skills from Claude Code or GitHub Copilot CLI: `/jenkins-example-crawler 10` and `/jenkins-to-gha all`.

- What each skill does: [skills.md](skills.md).
- Using Copilot: [copilot.md](copilot.md).
- No agent is needed: [AI.md](AI.md).

## Run on real GitHub Actions

```bash
uv run j2gha run 004 --tier selfhosted                      # ephemeral self-hosted runners in local Docker: no hosted minutes
uv run j2gha budget                                         # check the allowance first
uv run j2gha run 004 --tier hosted --yes --max-minutes N    # GitHub-hosted runners: spends Actions minutes
```

Both push the workflow to a throw-away branch of the repository in `J2GHA_REPO` (default: this clone's `origin`) and
delete it afterwards. The run's logs and artifacts stay in that repository.

For a pipeline that is not a corpus example, the harness refuses both tiers unless `J2GHA_REPO` names a private
repository ([own-pipelines.md](own-pipelines.md#what-leaves-your-machine)).

act, the local tier, cannot be the final word; why is in [act-evaluation.md](act-evaluation.md).

## Re-run the reference runs

The runs linked from the examples' READMEs ([results.md](results.md#reference-runs)) are re-run by re-running every
remote record in its own mode and scenario, which rewrites the records and links. On the public repository the hosted
runs are free; `J2GHA_MAX_RUN_MINUTES` only caps a run's worst case:

```bash
export J2GHA_MAX_RUN_MINUTES=300
for d in examples/[0-9]*/; do
  i=$(basename "$d")
  for mode in trace full; do
    tiers=$(for t in selfhosted hosted; do [ -d "examples/$i/runs/$t-$mode" ] && echo "$t"; done | paste -sd,)
    [ -n "$tiers" ] || continue
    extra=()
    case "$i-$mode" in
      006-trace|106-trace) extra=(--environments) ;;
      013-full) extra=(--param PROMOTE=false) ;;
    esac
    uv run j2gha run "$i" --tier "$tiers" --mode "$mode" --yes "${extra[@]}"
  done
done
uv run j2gha summary
```

GitHub occasionally starts a second run for one push to a run branch; the harness records the first, and the duplicate
stays queued with no runner to pick it up. Cancel it with
`gh api -X POST repos/<owner>/<repo>/actions/runs/<id>/force-cancel`.

## Keep an eye on GitHub Actions minutes

Hosted runs on a private repository spend real minutes: always check `j2gha budget` first. On a public repository,
standard GitHub-hosted runners are free and only the per-run cap applies. Artifact storage is not tracked by the guard.

```bash
uv run j2gha budget                      # usage bar, remaining minutes, harness ledger, per-repo breakdown
gh auth refresh -h github.com -s user    # billing data for a user-owned repository (required for hosted runs on private repositories)
```

Environment knobs: `J2GHA_INCLUDED_MINUTES` (2000 Free / 3000 Pro), `J2GHA_RESERVE_PCT` (20),
`J2GHA_MAX_RUN_MINUTES` (30). Trace runs force `ubuntu-latest` (no OS multipliers) and 5-minute job timeouts. How the
guard decides is in [architecture.md](architecture.md) (*Cost control*).

## Reference docs for agents

`uv run j2gha docs fetch` downloads version-pinned Jenkins and GitHub Actions documentation into the gitignored
`.docs/` directory for the `jenkins-docs` and `gha-docs` skills; the harness itself never reads it. Commands, design
and evaluation: [documentation.md](documentation.md).
