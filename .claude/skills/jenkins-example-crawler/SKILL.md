---
name: jenkins-example-crawler
description: Crawl github.com for real-world Jenkins pipelines (Jenkinsfiles and shared-library pipeline templates) that cover different pipeline styles - declarative, scripted node{}, matrix, parallel, docker/kubernetes agents, shared libraries, input gates, credentials, parameters/triggers, downstream builds, dynamic Groovy, Windows, tools - and add N scored, cited examples to examples/NNN. Use when asked to find, collect, crawl, add or refresh example Jenkinsfiles or to grow the Jenkins-to-GitHub-Actions test corpus, including from a specific GitHub organisation or user. Accepts the number of examples to create.
argument-hint: "<count> [--owner org-or-user ...] [--styles style ...] [--allow-unlicensed]"
---

# Jenkins example crawler

Adds `<count>` new examples to `examples/` as `examples/001`, `examples/002`, ... (numbering continues after the
highest existing index). Each example directory gets:

- `Jenkinsfile` - the original pipeline, verbatim
- `README.md` - citation (repository, file permalink at the last commit that touched it, licence, stars, dates),
  classification (dialect + detected styles), a **score out of 10** with a per-criterion table and a one-paragraph
  "why this score" summary, plus placeholder sections that the harness fills later (analysis, conversion,
  validation, execution)
- `source.json` - machine-readable provenance, score breakdown and crawl-time analysis

The crawl is fully automated by the `j2gha` CLI in this repository; this skill tells you how to drive it and
check the result.

## Arguments

`$ARGUMENTS` - first token is the number of examples to create (default 10). Remaining tokens are passed through
to `j2gha crawl`, e.g. `--styles matrix scripted` to target specific styles or `--allow-unlicensed` to include
repositories without a detected licence (excluded by default so every example is redistributable).

If the user names a GitHub organisation or user (a name or a `https://github.com/<owner>` URL), pass
`--owner <owner>` (repeatable). With no count given for an owner, dry-run with a high count (e.g. 20) to see
how many candidates the owner has, then write the ones worth keeping.

## Targeting an owner (`--owner`)

`--owner` swaps code search for a walk of the owner's repositories:

- It lists the owner's public non-fork repositories and fetches each default-branch tree.
- It keeps files whose name mentions `Jenkinsfile`, plus `.groovy`/`.jenkins` scripts outside a library's
  `src/` classes, provided their content looks like a pipeline.
- It sees what code search misses: archived repositories, and names like `jenkinsfile.groovy` or
  `jenkinsfiles/jenkinsfile-publish`.
- The licence, size, duplicate and analysis filters still apply.
- It also drops near-duplicates (≥ 90% similar, as organisations template their Jenkinsfiles) of each other and
  of the existing corpus, and keeps the highest-scoring file per repository.
- The walk costs one REST call per repository, cached for 24 hours. It makes no code-search calls.

Expect lower scores than a code-search crawl: one organisation's repositories are often archived or have few
stars. Judge candidates on what they exercise, not on the total alone. Without `--owner` the crawler behaves
exactly as before.

## Prerequisites (check, do not assume)

1. `gh auth status` succeeds - GitHub code search requires authentication (the CLI uses `gh auth token`
   or `GH_TOKEN`).
2. Docker is running and the harness image exists: `docker image inspect j2gha/jenkins:local`. If it is missing,
   build it with `uv run j2gha docker build --only jenkins` (needed because candidates are parsed with Jenkins'
   own bundled Groovy to score complexity).
3. Dependencies: `uv sync` in the repository root.

## Procedure

1. Parse the count from `$ARGUMENTS` (default 10) and run:

   ```bash
   uv run j2gha crawl --count <count> [extra args]
   ```

   Use `--dry-run` first if the user wants to preview selections. The crawl takes roughly 3-6 minutes: GitHub code
   search is rate limited to 10 requests/minute and the client throttles itself; responses are cached in
   `.cache/github` for 24 hours, so re-runs are fast.

2. What the crawler does (so you can explain results):
   - runs style-specific code-search queries (`j2gha/crawl/styles.py`) - one or two per style
   - keeps the best-ranked file per repository, skips repositories already in the corpus, forks/vendored paths,
     unlicensed repositories (unless `--allow-unlicensed`), tiny/huge files and normalised-content duplicates
   - parses every candidate with Jenkins' Groovy (Docker) and runs the j2gha analyser to detect the dialect and
     styles it *actually* exhibits (search hits are only hints)
   - scores candidates (see `docs/scoring.md`) and selects examples round-robin over the styles least represented
     in the corpus, preferring repository owners not yet represented
3. After it finishes, list what was added (`ls examples/`) and spot-check one or two `README.md` files: the
   citation link must resolve to the original file and the score table must sum to the total.
4. Report back a table of the new examples: id, score, primary style, repository:path - the CLI prints exactly this.
5. Offer the next harness step: `uv run j2gha analyze <ids>` (AST analysis written into each README), then
   `uv run j2gha convert <ids>` / `validate` / `run --tier jenkins,act`.

## Re-scoring

If the scoring model changes, `uv run j2gha crawl --rescore` recomputes scores for all existing examples and
re-renders only the README header section (harness sections are preserved).

## Scoring summary (out of 10)

| Criterion | Max | Basis |
|---|---:|---|
| Repository activity | 1.5 | age of the repository's last push (archived halved) |
| Jenkinsfile freshness | 1.5 | age of the last commit touching the file |
| Complexity | 2.0 | stages, distinct steps, styles, migration difficulty |
| Value / uniqueness | 2.0 | style rarity in the candidate pool, novelty vs. corpus, showcase constructs |
| Popularity | 1.5 | stars on a log scale (10k+ = full marks) |
| Quality | 1.5 | parses, timeouts, post/cleanup, comments, no literal secrets, few unknown steps |

## Troubleshooting

- `GitHub code search needs authentication` - run `gh auth login`.
- `AST analysis unavailable` - build the image (`uv run j2gha docker build --only jenkins`).
- Few candidates for a style - widen with `--pages 2` or `--per-query 50`, or target it with `--styles <id>`.
- Style ids: declarative, scripted, matrix, parallel, docker-agent, kubernetes-agent, shared-library,
  library-template, when-post, input-gate, credentials, parameters-triggers, artifacts-tests, downstream-build,
  dynamic-groovy, windows, tools.
