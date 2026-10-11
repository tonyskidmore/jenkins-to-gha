# Example scoring model (0-10)

Every crawled example gets a score out of 10 so the corpus can be ranked and curated. The score answers one question:
**how valuable is this pipeline as a Jenkins → GitHub Actions migration test case?** A maintained, popular,
well-written pipeline that exercises rare constructs scores high. A stale, trivial pipeline duplicating styles we
already have scores low.

| Criterion | Max | How it is computed |
|---|---:|---|
| Repository activity | 1.5 | Age of the repository's last push: ≤90 days 1.5, ≤1 year 1.2, ≤2 years 0.9, ≤4 years 0.5, older 0.2. Archived repositories are halved. |
| Jenkinsfile freshness | 1.5 | Age of the last commit touching the file (`GET /repos/{r}/commits?path=`): ≤180 days 1.5, ≤1 year 1.2, ≤2 years 0.9, ≤4 years 0.6, ≤6 years 0.3, older 0.1. |
| Complexity | 2.0 | Structural richness from the AST analysis: 0.35·min(1, distinct steps/12) + 0.25·min(1, stages/8) + 0.25·min(1, styles/6) + 0.15·min(1, difficulty/60), × 2. |
| Value / uniqueness | 2.0 | 0.8·rarity (mean of 1 − frequency of each of its styles in the candidate pool) + 0.7·novelty (min(1, styles not yet in the corpus / 3), so three or more new styles score the full 0.7) + 0.5 if it contains a showcase construct (matrix, dynamic Groovy, input gate, library template, Kubernetes agent, downstream build, Windows). |
| Popularity | 1.5 | 1.5 · min(1, log10(stars + 1)/4); 10k+ stars get full marks, 1k ≈ 1.1, 100 ≈ 0.75. |
| Quality | 1.5 | Starts at 1.0. +0.15 timeouts, +0.15 post/cleanup handling, +0.1 comments, +0.1 credential bindings. −0.6 possible literal secret, −0.2 more than 3 unmapped custom steps, −0.7 fails Jenkins validation, −0.2 under 15 lines. 0 if it does not parse. |

The total is rounded to one decimal place. Each README shows the per-criterion points, their basis and a generated
**"Why this score"** sentence naming the strongest criteria (≥70% of max) and the weakest (<40%).

## Selection is coverage-driven, not score-driven

Scores rank candidates *within* a style. The crawler round-robins over the 17 styles, always serving the style least
represented in the corpus so far. It prefers repository owners not already present, so a run of `--count 15` covers
the taxonomy rather than returning fifteen Apache projects. Novelty is recomputed as examples are selected, so the
same pipeline can score differently depending on what the corpus already contains. `j2gha crawl --rescore`
recomputes all scores against the current corpus.

## Style taxonomy

`declarative`, `scripted`, `matrix`, `parallel`, `docker-agent`, `kubernetes-agent`, `shared-library`,
`library-template`, `when-post`, `input-gate`, `credentials`, `parameters-triggers`, `artifacts-tests`,
`downstream-build`, `dynamic-groovy`, `windows`, `tools`. Search queries are only hints. A style is assigned when
the AST analysis actually detects it (`j2gha/analysis/analyze.py::detect_styles`).
