# Reference documentation for agents

The brief asked four questions:

- Where is the source of truth for Jenkins and GitHub Actions (GHA) documentation, and is there an official MCP server?
- Should agents download the docs, and in which format?
- Can a version be chosen?
- How does an agent use local docs when they exist without depending on them, and is this better than what agents
  do today?

Three parallel research agents (Jenkins sources, GHA sources, formats/MCP) and direct probes of the harness
controller answered the first three questions (2026-10-03). Five evaluation agents tested the result against the
current methods ([docs-evaluation.md](docs-evaluation.md)).

**Decision:** download on demand into a gitignored directory, as Markdown with llms.txt-style indexes, version-pinned
per source. Two skills read it locally first and fall back to the official web endpoints. A small curated crosswalk
links Jenkins constructs to GHA pages.

```bash
uv run j2gha docs fetch                          # both sources: jenkins (~1 min) + gha fpt (~4 min)
uv run j2gha docs fetch gha --version ghes-3.19  # another GitHub product version
uv run j2gha docs fetch jenkins --label 2.580.1+pc233737f --parts handbook   # refresh one part of a bundle
uv run j2gha docs status                         # bundles present, * = default per source
uv run j2gha docs use gha ghes-3.19              # switch the default (or J2GHA_DOCS_GHA=ghes-3.19)
uv run j2gha docs xref input stash when          # Jenkins construct -> catalog decision + both sides' pages
```

## 1. Sources of truth

### Jenkins

| Source | Format, size, licence | Versioning | Used |
|---|---|---|---|
| **Harness controller** `/pipeline-syntax/html`, `/pipeline-syntax/globals`, `/descriptor/<id>/help/<field>`, `/pluginManager/api/json` | HTML (1.1 MB step reference); plugin help texts (mostly MIT) | **Exact**: the controller's core version plus installed plugin versions. These are the docs for what the harness validates and runs | yes: `steps/`, `globals/`, installed `declarative/`, `plugins.md` |
| jenkins.io handbook: `jenkins-infra/jenkins.io` `content/doc/**` | AsciiDoc. Pipeline, tour, using and glossary chapters are ~0.5 MB of text. CC BY-SA 4.0 | Latest only. The repo has no tags or per-release docs, so we pin by commit SHA | yes: `handbook/` (sparse, blob-filtered clone; 2 s) |
| reports.jenkins.io `declarative.zip` and `allAscii.zip` | AsciiDoc wrapping HTML. 0.3 MB and 3.6 MB zipped; 721 plugins | Latest plugin releases, rebuilt weekly. Not pinnable, so the ETag and date are recorded | yes: `declarative/` for plugins not installed, `plugins/` |
| plugins.jenkins.io API (`/api/plugin/<name>`) | JSON with README HTML | Default branch only. A plugin's README at a release tag is reachable through raw.githubusercontent | no (future: READMEs of installed plugins at their tags) |
| workflow-cps `doc/*.md` | Markdown, 23 KB | At the installed plugin's release tag | yes: `handbook/cps/` |
| Javadoc, script-security allowlists | HTML / text | per release | no (plugin-developer material) |

### GitHub Actions

| Source | Format, size, licence | Versioning | Used |
|---|---|---|---|
| **docs.github.com APIs** (advertised in `https://docs.github.com/llms.txt`): `/api/pagelist/versions`, `/api/pagelist/en/<version>`, `/api/article/body?pathname=` | Rendered Markdown with every Liquid tag resolved. 245 Actions pages (fpt), 2.2 MB after cleanup. CC-BY-4.0 | **Per product version**: `free-pro-team@latest`, `enterprise-cloud@latest`, `enterprise-server@3.18`–`3.22`. Archived GHES returns 403 | yes: `gha/<version>/actions/**` |
| `github/docs` repo `content/actions` + `data/` | Markdown with Liquid: 3,899 `{% data %}` tags and 397 `ifversion` lines across 247 files. Only the docs app can render it | Every version mixed in one file | no: unreadable for agents without rendering. Useful for diffing, and `data/features/*.yml` records which GHES release gets a feature |
| SchemaStore `github-workflow.json`; `@actions/workflow-parser` `workflow-v1.0.json` | JSON Schema, ~100 KB | Latest / npm version | no: actionlint already validates. Candidate add-on |
| `github/rest-api-description` webhooks | OpenAPI, ~12 MB per version | Per version | no (future: event payloads) |

### MCP servers

Neither vendor provides a documentation MCP server that works locally, offline and for a chosen product version.
What exists:

- **Jenkins:** the [MCP Server plugin](https://github.com/jenkinsci/mcp-server-plugin) operates a Jenkins instance (jobs,
  builds, logs) and serves no docs.
- **GitHub:** `github/github-mcp-server` has no docs tools locally. Its remote-only `github_support_docs_search`
  toolset needs Copilot auth, has no version selection and doesn't work offline. `llms.txt` itself says the server
  "does not currently include docs search".
- **Third-party:** [Context7](https://context7.com) indexes both vendors' docs (`/websites/github_en_actions`,
  `/websites/jenkins_io_doc`) as snippets.
  - Its version list is empty for both, so it serves the latest only.
  - Anonymous use allows 200 calls a month; the free tier with a key allows 1,000.
  - Queries go to a third party, and its REST paths are undocumented.
  - DeepWiki and GitMCP are AI-generated or README-level summaries.
  - [arabold/docs-mcp-server](https://github.com/arabold/docs-mcp-server) is the closest self-hosted equivalent (local
    index with versions), but it adds a Node service for what grep already does.
- **The precedent to watch for:** Microsoft Learn's MCP server. If GitHub ships an equivalent, the `gha-docs` skill
  can prefer it, because the skills only define where to look first.

## 2. Format: Markdown files, llms.txt indexes, a small compiled layer

**The site in the brief.** `andrej-karpathy.com` is not Karpathy's site (that is `karpathy.ai`). It is a Cognee
(topoteretes) demo of his **LLM wiki** pattern: [gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f),
[post](https://x.com/karpathy/status/2039805659525644595), April 2026. The pattern has four parts:

- Immutable raw sources.
- An LLM-maintained wiki of interlinked Markdown.
- An `index.md` the model reads first.
- grep instead of RAG at moderate scale ("~100 sources, ~hundreds of pages").

He also argued in 2025 for Markdown docs and llms.txt aimed at LLMs.

**What we adopted from it, and what we didn't:**

| Idea | Here |
|---|---|
| Markdown, not HTML | Every page is Markdown. Measured on the same pages, rendered HTML is **12x** (GHA workflow syntax: 2,047 KB vs 171 KB), **31x** (GHA limits: 373 KB vs 12 KB) and **2.1–2.4x** (jenkins.io syntax, step reference) larger. Table padding and inline SVG icons are stripped. |
| `index.md` read first | Each bundle has an llms.txt-format `INDEX.md`: H1, `>` summary, H2 sections of `- [title](path): blurb`. Large families get sub-indexes so the top index stays small (Jenkins 19 KB, GHA 8 KB). |
| Raw sources kept immutable | Pages are converted mechanically and **never rewritten by an LLM**. Each starts with `> Source: <url> (<source> <version>)` for citation. |
| LLM-compiled wiki | **Only a thin layer:** `j2gha/rules/docs-xref.yaml` (57 Jenkins constructs → Jenkins and GHA pages, plus the trap worth knowing), rendered to `.docs/xref.md` and `j2gha docs xref`. Compiling the whole corpus would make agents read derived text instead of the vendor's, and the evaluation shows that exact wording (limits, parameter names, version gaps) is what matters. |
| grep over RAG | Agents use ripgrep/Grep plus ranged Reads, as Anthropic's guidance for Claude Code recommends. The bundles are ~2 MB of GHA text per version and ~13 MB of Jenkins text (10 MB of which is the all-plugins reference). SQLite FTS5 (in the standard library) is the next step if grep ever stops being enough. |

**Converters (no system dependencies).**

- HTML goes through `markdownify` + BeautifulSoup.
- AsciiDoc goes through a small converter (`j2gha/docs/asciidoc.py`) covering what jenkins.io uses:
  - Pandoc reads AsciiDoc only from 3.8.3; this machine has 2.9.
  - asciidoctor needs Ruby.
- GitHub serves Markdown already.

## 3. Versions

| Source | Version label | What is pinned |
|---|---|---|
| jenkins | the controller's identity: core version + digest of its plugin set (`2.580.1+pc233737f`) | `steps/`, `globals/` and installed `declarative/` pages exactly match core + plugin versions (`plugins.md`). `handbook/` is pinned to a jenkins.io commit (`--ref <sha>`). `declarative/` (other plugins) and `plugins/` are the latest releases, with the reports ETag recorded. |
| gha | `fpt`, `ghec`, `ghes-3.18` … `ghes-3.22` | The whole bundle is rendered for that product version. |

**Choosing a version.**

- `j2gha docs use <source> <version>` writes `.docs/selected.json`. `J2GHA_DOCS_JENKINS` and `J2GHA_DOCS_GHA` override it
  per shell.
- The skills tell the agent to answer for the product the migration targets.
- A Jenkins bundle always documents the *running* harness controller:
  - The default label is `<core>+p<first 8 hex of sha256 of the sorted plugin:version list>`. Controllers on the same
    core with different plugin sets get separate bundles, and a controller fetch under that label becomes the default.
  - `--version X.Y.Z` is a check: it is refused unless the running controller has that core. So is a `--label` that
    looks like another controller's identity.
  - `--label <name>` names the bundle; `latest` is the default when the `controller` part is skipped.
  - Bundles labelled with the core version only (`2.580.1`, fetched before the plugin digest) remain usable through
    `docs use` and `docs path`.
- To document another Jenkins, change `J2GHA_JENKINS_BASE` / `docker/jenkins/plugins.txt` and fetch again. The new
  plugin set gets its own bundle.

**Versions really differ.** Measured differences between GHES 3.18 and GitHub.com:

- `workflow_dispatch` inputs: 10 vs 25.
- Reusable-workflow nesting: 4 levels and 20 unique workflows vs 10 and 50.
- Missing from 3.18: step-level `parallel`/`background`, `concurrency.queue`, and `schedule.timezone`.

**Downloaded bundles outlive the source.** GHES 3.18 reaches end of support on 2026-10-14, after which docs.github.com
returns 403 for its Markdown. A bundle fetched before then keeps working.

## 4. Layout and integration

```text
.docs/                       ($J2GHA_DOCS_DIR to share one copy between clones; gitignored, never committed)
  INDEX.md                   bundles present, default per source
  selected.json              {"jenkins": "2.580.1+pc233737f", "gha": "fpt"}
  xref.md                    Jenkins construct -> both sides' pages (relative links)
  jenkins/2.580.1+pc233737f/ INDEX.md, manifest.json, pages.json, steps/ globals/ declarative/ handbook/ plugins/
                             plugins.md
  gha/fpt/  gha/ghes-3.18/   INDEX.md, manifest.json, pages.json, pagelist.json, actions/**.md (mirrors
                             docs.github.com paths)
  <source>/.<label>.staging-<pid>/  a fetch in progress (swapped in when complete, deleted if it fails)
  .src/                      jenkins.io sparse clone, raw docs.github.com cache (7 days; makes re-fetch resumable)
```

`manifest.json` records provenance, including `parts`: each family (Jenkins part or GHA section) and when it was
fetched. `pages.json` lists every page with its family, so a partial refresh can rebuild the indexes.

**Refreshing.**

- **A failed fetch changes nothing.** A fetch builds the bundle in a staging directory next to it, checks it (manifest
  written, at least one page), then swaps it in: old bundle → `.<label>.old-<pid>`, staging → bundle, backup deleted.
  Only then are `selected.json` and `INDEX.md` updated. On any failure (controller, git, HTTP, conversion) only the
  staging directory is deleted, so the previous bundle, the selection, `INDEX.md` and `xref.md` stay as they were.
- **A partial fetch replaces only what it fetches.** `--parts handbook` (Jenkins) or `--parts actions/reference` (GHA
  sections) onto an existing bundle of the same label:
  - replaces those families' pages;
  - keeps the other families' pages, index entries, provenance (`origin`, `components`) and fetch times;
  - gives just the requested parts when no bundle of that label exists.

  A part that no longer has a page (a plugin dropped from `allAscii.zip`) loses it. A bundle fetched before
  `pages.json` existed can only be refreshed whole: a partial fetch is refused rather than dropping families.
- **Labels are checked.** A label becomes a directory name, so wherever one is read (fetch, `docs use`, `docs path`,
  `J2GHA_DOCS_<SOURCE>`, `selected.json`) it must be 1-64 of `A-Za-z0-9._+-`, starting with a letter or digit. That
  rules out `..`, `a/b` and absolute paths. GHA aliases are normalised first (`enterprise-server@3.19` → `ghes-3.19`).
  Deletions are limited to directories inside `<docs>/<source>/`.

**Code** (`j2gha/docs/`):

- `store.py`: layout, indexes, manifests, selection, label checks, staged swap and partial-refresh merge.
- `jenkins.py`, `gha.py`: fetchers.
- `asciidoc.py`, `markdown.py`: converters (SVG icons → Yes/No, collapsed table padding).
- `xref.py`: the crosswalk. `web_refs()` gives an entry as jenkins.io and docs.github.com (GitHub.com) links only.
- `commands.py`: the CLI.

Tests (`tests/test_docs.py`) run offline. They check that every GHA page named in the crosswalk exists in a committed
page-list snapshot.

**Agents.**

- **The two skills.** `.claude/skills/jenkins-docs` and `.claude/skills/gha-docs` each:
  1. Locate the bundle with `j2gha docs path`.
  2. Map needs to files ("step parameters → `steps/<step>.md`", "workflow key → grep the heading in
     `workflow-syntax.md`").
  3. Point to `j2gha docs xref`. Its GHA links keep the requested version (`--gha-version`, `J2GHA_DOCS_GHA` or the
     default):
     - Without that version's bundle, they point to that version on docs.github.com
       (`/en/enterprise-server@3.18/actions/...`).
     - A page missing from a downloaded bundle whose sections cover it is reported as "not in the ghes-3.18 docs",
       never silently swapped for the GitHub.com page.
  4. Fall back to the web when no bundle exists. GitHub's fallback is the Markdown Article API, not HTML. Jenkins'
     fallback is jenkins.io or the running controller.
  5. Fetch the bundle when a task needs more than a couple of lookups.
- **Gitignored path.** `.docs/` is gitignored, so repo-root searches skip it, which keeps code searches clean. The
  skills therefore always pass the path explicitly.
- **Other entry points.** `jenkins-to-gha` and `AGENTS.md` point to the two skills.

**The harness.** The pipeline (`analyze`, `convert`, `validate`, `run`) never reads the bundles: an strace of a full
`pipeline` run plus `analyze`/`convert`/`validate all` (2026-10-05) recorded no access to `.docs`. The only use is
`convert`'s migration report, which ends with a *Reference documentation* section: each construct in the report that has
a crosswalk entry, most work first, with its note and its Jenkins and GHA pages. It is built with `xref.web_refs()`, so
it always links the web pages and is identical whether or not bundles are downloaded. A committed report must not
depend on the machine it was built on, or contain links to that machine's local files.

**Rate limits.** docs.github.com's edge limiter blocks an IP for about a minute after parallel bursts (`429`,
`retry-after: 0`). The fetcher is sequential at 1 request/s with exponential backoff. Fetches of 245 pages (fpt) and 214
pages (GHES 3.18) at that rate completed with no 429s.

## 5. Evaluation

[docs-evaluation.md](docs-evaluation.md) compares five methods on 15 questions:

| Method | Score /15 | Verified answers | Tokens | Wall time |
|---|---|---|---|---|
| memory | 13 | 0 | 38.6k | 56 s |
| web (WebSearch + WebFetch) | 15 | 13 | 62.5k + hidden summariser | 165 s |
| Context7 | 13 | 8 | 83.6k | 196 s |
| **local bundles** (this design) | **15** | **15** | 87.9k | 143 s |
| local bundles with Haiku | 14 | 15 | 86.2k | 150 s |

**What local adds.** Web and local tie on accuracy. Local is the only method that is:

- verifiable for every answer;
- version-exact (GHES releases, the controller's plugin set);
- immune to WebFetch truncating a 2 MB reference page into a false "this key doesn't exist";
- available offline and free of rate limits.

It also lets a small model answer with citations. The evaluation's process notes drove five fixes, listed in the
evaluation document.

## 6. Limitations and next steps

- **Partial pinning.** jenkins.io and the reports zips can't be pinned to a Jenkins release. Only the controller part
  is version-exact. Plugins not installed in the controller are documented at their latest release.
- **Killed fetches.** A fetch killed outright (SIGKILL, power loss) leaves its `<source>/.<label>.staging-<pid>/`
  directory behind. `status` ignores it and the bundle is untouched; delete it by hand.
- **Not yet included:**
  - Plugin READMEs at installed tags.
  - GitHub webhook payload schemas.
  - The workflow JSON schema.
  - GitHub's `data/features` (which GHES release gets a feature).
- **The crosswalk is curated.**
  - Its GHA links are checked against the page list in tests. Re-snapshot `tests/fixtures/gha-pagelist-fpt.txt` when
    GitHub reorganises its docs; it did so in 2025.
  - Its notes are guidance, not documentation, so treat them like the step catalog.
- **Possible addition:** a docs MCP server would only add value as a shared service across many repositories.
  Until then, files plus grep are simpler, faster, offline and version-exact.

## 7. Brief → implementation

| Brief | Where |
|---|---|
| Individual agent skills that pull down the Jenkins / GHA docs and reference them locally | `.claude/skills/jenkins-docs`, `.claude/skills/gha-docs`; `j2gha docs fetch` |
| Parallel explore agents to locate the source of truth and how to download it | §1 (three research agents: Jenkins, GHA, formats/MCP; plus probes of the live controller) |
| Is there an official MCP server? | §1 "MCP servers": Jenkins has none for docs; GitHub's official server has a remote-only docs search (`github_support_docs_search`) with no version selection or offline use. Context7 was tested and not adopted |
| Best optimised format (Markdown / HTML / other; the Karpathy reference) | §2: Markdown + llms.txt indexes + a thin curated crosswalk. Sizes were measured |
| Cross-referencing Jenkins and GHA docs | `j2gha docs xref`, `.docs/xref.md`, `j2gha/rules/docs-xref.yaml` |
| Choose a version relevant to the project | §3: controller-exact Jenkins; `--version fpt\|ghec\|ghes-X.Y`; `j2gha docs use`; `J2GHA_DOCS_*` |
| Docs not in the repo, but the repo can fetch them | `.docs/` is gitignored, or use `$J2GHA_DOCS_DIR`; fetchers live in `j2gha/docs/` |
| Agent optionally uses local docs when available | Skills: `j2gha docs path` → local, else the web fallback (§4) |
| Test against current knowledge-attainment methods | [docs-evaluation.md](docs-evaluation.md): memory, web, Context7, local (Opus and Haiku) |

## 8. Open questions

1. **Location.** Should the bundles live per clone (`.docs/`, the default) or in one shared place, e.g.
   `J2GHA_DOCS_DIR=~/.cache/j2gha-docs` in your shell profile?
2. **GitHub target.** Which product will the migrations target: GitHub.com, GHEC or a specific GHES release? GHES 3.18
   reaches end of support on 2026-10-14, after which its Markdown can no longer be fetched, so fetch it now if it
   matters.
3. **Customer Jenkins.** Should the Jenkins bundle also be buildable for a *customer's* Jenkins (core version plus
   their `plugins.txt`) by starting a throwaway controller with that plugin set? The current bundle documents the
   harness controller.
4. **Lookup subagent.** Should doc lookups be delegated to a Haiku subagent by default? The evaluation suggests the
   bundles make that viable, and it keeps the main context small.
