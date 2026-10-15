---
name: gha-docs
description: Look up authoritative GitHub Actions documentation - workflow syntax keys, contexts and expressions, events/triggers, limits, runners, environments and approvals, concurrency, artifacts and caching, secrets/OIDC, reusable workflows and composite actions, the Jenkins migration guide - from a local copy rendered for a chosen product version (GitHub.com, GHEC or a specific GHES release), falling back to docs.github.com's Markdown API when no local copy exists. Also downloads or refreshes that copy (`j2gha docs fetch gha --version ...`). Use whenever a task needs GitHub Actions facts you would otherwise guess or web-search, e.g. while generating or reviewing a converted workflow, checking a limit, or deciding whether a feature exists on the user's GHES version.
argument-hint: "[topic | question] [--version fpt|ghec|ghes-X.Y] [--fetch]"
---

# GitHub Actions documentation (local first)

Local docs are optional. Use them when present; never fail a task because they are missing.

## 1. Locate the bundle (and pick the version)

```bash
uv run j2gha docs status           # bundles present; * marks the default per source
uv run j2gha docs path gha         # default GHA bundle dir, or exit 1
```

- **Product version:** answer for the version the migration targets.
  - Use GitHub.com (`fpt`) unless the user or the project says GHEC or a GHES release.
  - Pass `--version ghes-3.19` to `path`, or set `J2GHA_DOCS_GHA=ghes-3.19`, to use another downloaded bundle.
  - `uv run j2gha docs use gha <version>` changes the default.
- **Found** → work from that directory (`$G`). It is gitignored, so pass `$G` explicitly to your search tool, e.g. `rg -n --no-ignore <pattern> "$G"` (searches
  from the repository root skip gitignored paths).
- **Not found** → if the task needs more than one or two lookups, or the request includes `--fetch`, download:
  - Command: `uv run j2gha docs fetch gha [--version fpt|ghec|ghes-X.Y]`.
  - It fetches about 250 pages and is throttled for docs.github.com's rate limit, so expect about 5 minutes the
    first time. Re-runs within 7 days reuse the cache.
  - Supported versions: `fpt`, `ghec`, and the GHES releases listed by `https://docs.github.com/api/pagelist/versions`.
  - `--parts actions/reference` refreshes just that section and keeps the rest of an existing bundle. A failed fetch
    leaves the existing bundle as it was.
  - Otherwise use the web fallback (section 4).

## 2. Where to look in `$G`

Pages mirror docs.github.com paths: `$G/actions/<path>.md`.

| Need | Read |
|---|---|
| Any workflow key (`on`, `jobs.<id>.if`, `strategy.matrix`, `concurrency`, `container`, `services`, `permissions`...) | `$G/actions/reference/workflows-and-actions/workflow-syntax.md` (about 170 KB: search for the key's heading, read that range) |
| Contexts (`github`, `env`, `job`, `steps`, `inputs`...) and where each is available | `$G/actions/reference/workflows-and-actions/contexts.md` |
| Expressions, operators, status functions (`always()`, `cancelled()`...) | `$G/actions/reference/workflows-and-actions/expressions.md` |
| Events and their filters (`workflow_dispatch`, `workflow_run`, `schedule`...) | `$G/actions/reference/workflows-and-actions/events-that-trigger-workflows.md` |
| `GITHUB_OUTPUT`/`GITHUB_ENV`, annotations, masking | `$G/actions/reference/workflows-and-actions/workflow-commands.md` |
| Default env vars (`GITHUB_REF_NAME`, `RUNNER_OS`...) | `$G/actions/reference/workflows-and-actions/variables.md` |
| Limits (job time, matrix size, queue, payloads) | `$G/actions/reference/limits.md` |
| Environments, required reviewers, wait timers | `$G/actions/reference/workflows-and-actions/deployments-and-environments.md` |
| Jenkins migration guide / Actions Importer | `$G/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins.md`, `.../automated-migrations/jenkins-migration.md` |
| Anything else | Search `$G` or `$G/INDEX.md` (reference pages) → category sub-indexes (`$G/actions/how-tos/INDEX.md`, `concepts/`, `tutorials/`) |

Cite the `> Source:` URL at the top of the page and the bundle version (e.g. "GHES 3.19 docs").

## 3. Cross-referencing from Jenkins

```bash
uv run j2gha docs xref <jenkins step/directive ...> [--gha-version ghes-3.18]
```

This prints the catalog decision and the Jenkins and GHA pages for each construct (`<docs>/xref.md` has the full
table). `--gha-version` (or `J2GHA_DOCS_GHA`) picks the version:

- **Bundle downloaded:** links resolve in it. A page it lacks is marked "not in the <version> docs" (its link is the
  GitHub.com page). Treat that as the page, and likely the feature, being absent from that release.
- **No bundle:** links point to that version on docs.github.com (`/en/enterprise-server@X.Y/actions/...`).

Use the `jenkins-docs` skill for the Jenkins side.

**Comparing versions.** To check whether a feature exists on the target, grep the same page in both bundles, e.g.
`rg -n "queue" .docs/gha/{fpt,ghes-3.18}/actions/reference/workflows-and-actions/workflow-syntax.md`.

## 4. Web fallback (no local bundle)

docs.github.com serves rendered Markdown, which is far cheaper than HTML. Don't fire more than about 10 requests in
a burst: it answers HTTP 429.

- **One page:**
  ```bash
  curl -s "https://docs.github.com/api/article/body?pathname=/en/actions/reference/workflows-and-actions/contexts"
  ```
  For a GHES version, prefix the path: `/en/enterprise-server@3.19/actions/...`. A web-fetch tool on
  `https://docs.github.com/en/actions/<path>.md` also works.
- **Search:**
  ```bash
  curl -s "https://docs.github.com/api/search/v1?query=<q>&language=en&version=free-pro-team@latest&client_name=j2gha"
  ```
- **Page list:** `https://docs.github.com/api/pagelist/en/free-pro-team@latest`.

## Version notes

- GHES docs exist only for supported releases. Deprecated releases are archived and not served by these APIs.
- New github.com features usually reach GHES a release or more later. When the user targets GHES, check that
  version's bundle before recommending a feature.
