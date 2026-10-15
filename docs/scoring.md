# Scores

j2gha computes two scores:

- **[Migration difficulty](#migration-difficulty-0-100) (0-100):** computed by `j2gha analyze` for every pipeline. It
  estimates how much work the migration will be.
- **[Example score](#example-score-0-10) (0-10):** computed only by the crawler. It ranks candidate pipelines as test
  cases for the corpus.

## Migration difficulty (0-100)

**How it is calculated.** The score is the sum of seven dimensions. If a *hard gate* applies, it is then raised to at
least 46.

**What it does and does not say.** It estimates effort, and its band names the kind of migration. It says nothing about
whether a conversion is correct. Why the score has this shape is in [mechanism.md](mechanism.md#3-classify-before-converting---convertibility-is-a-first-class-output);
the code is `complexity()` in `j2gha/analysis/analyze.py`.

| Dimension | Max | What raises it |
|---|---:|---|
| Declarative structure | 20 | The dialect, plus `script {}` blocks and the Groovy statements in them (up to 10). By dialect: Declarative 0, library template 6, library call or step 12, scripted 13, unknown 18, unparseable 20. |
| Step mapping | 25 | Steps the catalog cannot map, weighted by risk: 25 × (1 − weighted coverage). |
| Plugin coupling | 15 | 0.75 per distinct step whose conversion needs a policy decision or a redesign. When the pipeline loads no shared library, also 3 per distinct unknown step. |
| Library opacity | 15 | 9 when the pipeline loads a shared library (or is a library call), plus 2 per distinct unknown step. Without a library: 4 when there are 3 or more unknown steps, which may come from an implicitly loaded global library. |
| Runtime coupling | 10 | Custom agent labels, `docker`, `dockerfile` or Kubernetes agents, `bat`/`powershell` steps, and `tools`. |
| Security and identity | 10 | Credentials (2 each, up to 6), `input` gates, and cloud-auth wrappers (`withAWS`, `azureCLI`, `withVault`, `withKubeConfig`). |
| Control flow | 5 | Dynamic `parallel` or stage generation, loops, `try`/`catch`, a matrix, stages nested more than 2 deep, or more than one `parallel`. |

**Hard gates** raise the score to at least 46, whatever the dimensions add up to:

| Gate | When |
|---|---|
| `ParseError` | Jenkins' Groovy rejects the file. |
| `OpaqueLibraryEntrypoint` | The whole pipeline is a call into a shared library. |
| `JenkinsApiCoupling` | The pipeline uses Jenkins internals: `Jenkins.instance`, `currentBuild.rawBuild`, `hudson.model.`, `@NonCPS`, `GroovyShell` and the other patterns under `hard_gates` in `j2gha/rules/steps.yaml`. |
| `ExternalGroovyLoad` | `load` or `evaluate`. |
| `DynamicParallel` | `parallel` over a map built at run time. |
| `DynamicStageGeneration` | `stage()` called inside a loop. |

`SharedLibrary`, a pipeline that loads a shared library, is a high-severity finding but not a gate. An opaque library
is missing information, not proof that the pipeline needs a redesign.

**Bands:** 0-20 straightforward · 21-45 assisted · 46-70 significant-redesign · 71-100 rebuild-around-intent.

**Convertibility follows from the score:**

| Value | When |
|---|---|
| `report-only` | A library call or step, or a file that did not parse |
| `partial` | Any hard gate, any unknown step (it converts to a manual placeholder), a scripted pipeline, or a score above 45 |
| `automatic` | Everything else |

### Unknown steps

An unknown step is a plugin or shared-library step that the step catalog does not know. j2gha cannot tell the two
apart.

- **Where it counts.** It counts in step mapping, through coverage. Beyond that it counts once more:
  - in library opacity when the pipeline loads a library, since a bare call it does not define is most likely a library
    step;
  - otherwise in plugin coupling.
- **The score as if they were mapped.** When a pipeline has unknown steps, j2gha also gives the score and band it would
  have if every one of them were mapped. The difference is how much of the score is information j2gha lacks rather
  than the pipeline's own structure.
- **Example 017** has one unknown step and scores 36 (assisted). It would score 34 if that step were mapped.
- **Read the dimensions and that second score before the band.** Many unknown steps can still push a pipeline into
  significant-redesign. Example 015 has 15 unknown steps and no library; it scores 56, and 32 if they were mapped.
- **Before analysis version 2**, the `SharedLibrary` finding was a hard gate, and an unknown step counted in both plugin
  coupling and library opacity. Library pipelines then rated significant-redesign almost regardless of their structure
  (017 scored 46).

### Where to see it

- **The `analyze` output** (also in `pipeline`): after the summary line, one line with the dimensions and gates and,
  when there are unknown steps, one line naming them with the score as if they were mapped:

  ```text
  [j2gha] 017: declarative      difficulty  36 (assisted), coverage 82.8%, convertibility partial
  [j2gha] 017:   structure 10, mapping 4.3, plugins 6, library 11, runtime 4, security 0, flow 1; hard gates: none
  [j2gha] 017:   1 unknown step(s) (fail): 34 (assisted) if they were mapped
  ```

- **The pipeline's `README.md`**, analysis section:
  - the *Migration difficulty* row, and *If every unknown step were mapped*;
  - the collapsed *Difficulty dimensions* table, with the hard gates under it.
- **`analysis/analysis.json`**, under `complexity`: `score`, `classification`, `dimensions`, `hard_gates`, and, with
  unknown steps, `unknown_steps` and `if_unknown_mapped`.
- **`gha/migration-report.md`:** the *Difficulty breakdown* section, and the hard gates listed as blocking items.

Converting your own pipelines, and what to do about libraries and plugins: [own-pipelines.md](own-pipelines.md).

## Example score (0-10)

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

### Selection is coverage-driven, not score-driven

Scores rank candidates *within* a style. The crawler round-robins over the 17 styles, always serving the style least
represented in the corpus so far. It prefers repository owners not already present, so a run of `--count 15` covers
the taxonomy rather than returning fifteen Apache projects. Novelty is recomputed as examples are selected, so the
same pipeline can score differently depending on what the corpus already contains. `j2gha crawl --rescore`
recomputes all scores against the current corpus.

### Style taxonomy

`declarative`, `scripted`, `matrix`, `parallel`, `docker-agent`, `kubernetes-agent`, `shared-library`,
`library-template`, `when-post`, `input-gate`, `credentials`, `parameters-triggers`, `artifacts-tests`,
`downstream-build`, `dynamic-groovy`, `windows`, `tools`. Search queries are only hints. A style is assigned when
the AST analysis actually detects it (`j2gha/analysis/analyze.py::detect_styles`).
