# Documentation lookup: evaluation of knowledge-attainment methods

This evaluation answers the brief's request to "test against what methods might be currently used for Jenkins/GHA
knowledge attainment against the solution" (design in [documentation.md](documentation.md)). It ran on 2026-10-03.

## Setup

- **Questions:** 15, all things a migration agent needs to know, each with an answer key verified against the vendor
  page.

  | Category | Questions | What they need |
  |---|---|---|
  | harness | Q1–Q4 | This controller's exact plugin set |
  | gha | Q6–Q10 | GitHub.com limits |
  | fresh | Q11–Q12 | GHA features documented in 2026 |
  | xref | Q5, Q13–Q14 | Jenkins construct → GHA design with constraints from both sides |
  | version | Q15 | GHES 3.18 vs GitHub.com |

- **Methods:** one subagent per method, same questions, isolated from the repository except `docker/jenkins/plugins.txt`.
  The answer key was moved out of the repo while they ran.
  - **memory:** no tools, training knowledge only (Opus).
  - **web:** WebSearch + WebFetch, the default way Claude Code looks things up today (Opus).
  - **Context7:** the third-party docs MCP service through its REST API, 25-call budget (Opus).
  - **local:** the solution: `jenkins-docs` / `gha-docs` skills, `.docs/` bundles, `j2gha docs xref`, no network
    (Opus).
  - **local-haiku:** the same as local with Claude Haiku 4.5.
- **Scoring:**
  - 1 means every key fact was stated.
  - ½ means the answer was incomplete, or correct but flagged low-confidence or "if it exists".
  - 0 means wrong or missing.
  - "Verified" counts answers whose decisive fact came from a cited authoritative page rather than memory or a
    search snippet.

## Results

| Method | Score /15 | Verified | Low-confidence answers | Tokens | Tool calls | Wall time | Needs at query time |
|---|---|---|---|---|---|---|---|
| memory | 13 | 0 | 4 | 38.6k | 2 | 56 s | nothing |
| web | **15** | 13 | 0 | 62.5k* | 30 (10 search, 17 fetch) | 165 s | internet, search engine, WebFetch summariser |
| Context7 | 13 | 8 | 3 | 83.6k | 24 (25 API calls) | 196 s | third-party service, quota (200 calls/month anonymous) |
| **local** | **15** | **15** | 0 | 87.9k | 29 | **143 s** | nothing (bundles fetched beforehand) |
| local-haiku | 14 | 15 | 0 | 86.2k | 47 | 150 s | nothing |

\* WebFetch processes each page with a separate small model, so those tokens don't appear in the subagent total. The
main-context figure understates web's real cost.

| Q | category | memory | web | Context7 | local | local-haiku |
|---|---|---|---|---|---|---|
| Q1 `retry` conditions on this controller | harness | 1 | 1 | 1 | 1 | 1 |
| Q2 `input` abort-button label (`cancel`) | harness | ½ | 1 | 1 | 1 | 1 |
| Q3 `readYaml` size/alias limits | harness | 1 | 1 | ½ | 1 | 1 |
| Q4 `podTemplate` plugin, installed? | harness | 1 | 1 | 1 | 1 | 1 |
| Q5 `disableConcurrentBuilds(abortPrevious)` → GHA | xref | 1 | 1 | 1 | 1 | 1 |
| Q6 matrix job limit | gha | 1 | 1 | 1 | 1 | 1 |
| Q7 job / workflow time limits | gha | 1 | 1 | 1 | 1 | 1 |
| Q8 `workflow_dispatch` inputs | gha | 1 | 1 | 1 | 1 | 1 |
| Q9 reusable-workflow nesting/count | gha | 1 | 1 | 1 | 1 | 1 |
| Q10 environment reviewers / wait timer | gha | 1 | 1 | 1 | 1 | 1 |
| Q11 step-level `background`/`parallel` | fresh | ½ | 1 | ½ | 1 | 1 |
| Q12 `concurrency.queue: max` | fresh | ½ | 1 | 1 | 1 | 1 |
| Q13 cron with `TZ=` and `H` → `schedule` | xref | ½ | 1 | ½ | 1 | ½ |
| Q14 `input submitter` → environment reviewers | xref | 1 | 1 | 1 | 1 | ½ |
| Q15 GHES 3.18 feature gaps + input limit | version | 1 | 1 | ½ | 1 | 1 |

## Findings

1. **Accuracy alone doesn't separate web from local; certainty does.**
   - Today's model knows most of these limits (memory 13/15).
   - Web search got everything, but 2 of its 15 answers rested on search-result snippets or release dates rather than
     a page it had read.
   - Local was the only Opus method to give 15 high-confidence answers, each citing a page plus the upstream URL.
2. **WebFetch silently loses content on large reference pages.** The GHA workflow-syntax page is 2 MB of HTML.
   WebFetch reported that the step-level `background`/`parallel` keys were *absent* on GitHub.com, GHEC and even the
   Markdown endpoint. The web agent recovered only through changelog posts. A grep of the local Markdown file (171 KB
   after cleanup) finds the heading directly. The same risk applies to every long page an agent consults, and it fails as a
   confident false negative.
3. **Version questions need versioned sources.**
   - Context7 has no version selection for either vendor, so it answered GHES 3.18 from memory.
   - The local bundles turn "does GHES 3.18 support X" into a grep across two directories.
   - On the Jenkins side, only the controller dump says which plugin provides `nonresumable()` and which `retry`
     conditions exist on *this* controller. The web agent noted that jenkins.io doesn't attribute conditions to
     plugins.
4. **A small model with local docs nearly matches the large one.**
   - Haiku with the bundles scored 14/15, and every answer was correct and cited. Its two half-points were omitted
     constraints, not wrong facts.
   - Haiku without docs wasn't run. Opus without docs left 4 of 15 answers hedged.
   - So knowledge moves into files, and lookups can be delegated to a cheaper model.
5. **Token cost is similar; latency favours local.**
   - Local reads raw text into context: 88k tokens, the largest main-context total. Web's figure hides its
     summariser.
   - Local finished fastest of the tool-using methods, needs no network and has no rate limits.
   - docs.github.com blocks bursts (HTTP 429 plus about a minute's block), and Context7's anonymous quota is
     200 calls a month. This one evaluation used 25 of those calls.
6. **Context7 was the weakest tool-based method.**
   - Its documented endpoint returned mostly off-topic code snippets, and the prose endpoint it needed is undocumented.
   - Its Jenkins library returns AI-written summaries that never surfaced parameter names (Q2, Q3).
   - The GitHub limits table arrived in fragments.
7. **The curated crosswalk earned its place.** The local agent noticed that GitHub's own *migrate-from-Jenkins*
   guide maps Jenkins `input` to action-metadata `inputs`, which is the wrong construct for approval gates. The
   crosswalk note (environment + required reviewers) corrected it.

## Fixes made from evaluation feedback

The local agents' process notes led to these changes. Bundles were rebuilt and the tests re-run afterwards.

| Problem | Fix |
|---|---|
| GHA tables embedded inline SVG check/x icons, padded to hundreds of spaces per cell | Icons are rendered as `Yes`/`No` and cell padding is collapsed. `limits.md` went from 30.9 KB to 12.3 KB, and the GHA bundle from 2.6 to 2.2 MB. |
| Installed Declarative directives (`equals`, `choice`, `parameters`) had parameter types expanded to every describable in Jenkins (4 MB lines) | Types use the raw class name. The Jenkins bundle went from 21.4 to 13.3 MB. |
| `xref cron` was treated as an unknown step | Added entries for `cron`, `pollSCM`, `upstream`, `branch`, `changeset`, `expression` and `timestamps`; the crosswalk now has 57 entries. Unknown terms get a search hint. |
| `xref` always resolved GHA pages to the default (fpt) bundle | `--gha-version ghes-3.18` / `--jenkins-version` |
| Installed directive pages were labelled "latest plugin release" | Pages now say whether they are the installed or the latest version. |

## Limitations of this evaluation

- **Sample size:** one run per method and 15 questions. Differences of one point are within run-to-run noise.
- **Grading:** the questions and grading are by the author of the solution, and the answer keys come from the same
  vendor pages the bundles contain. The questions are ones the harness actually needs, but expect some bias toward
  documentation-backed methods.
- **What wasn't tested:**
  - Long multi-step tasks (for example converting a whole Jenkinsfile with docs in the loop).
  - An installed Context7 MCP server (we used its REST API).
  - GitHub's remote `github_support_docs_search` toolset, which needs Copilot auth.

## Recommendation

1. **Make local bundles the primary source** for this project's agents. Run `uv run j2gha docs fetch` once per
   machine, and re-run it when the controller's plugins change or monthly for GHA.
2. **Keep the web fallback in the skills**, using docs.github.com's Markdown API, not HTML fetches.
3. **Use memory for drafting only.** It is right most of the time but can't say *which* answers are the exceptions.
4. **Don't adopt Context7** for this project.
5. **Consider a cheap lookup subagent.** Delegating documentation lookups to Haiku would keep the main context clean;
   the evaluation shows the bundles make that viable.
