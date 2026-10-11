---
name: jenkins-docs
description: Look up authoritative Jenkins Pipeline documentation - step parameters and defaults, which plugin (and version) provides a step, Declarative directives/options/triggers/when conditions, global variables (env, currentBuild, params, docker, scm), scripted/CPS behaviour, shared libraries - from a local, version-pinned copy that matches the harness Jenkins controller, falling back to jenkins.io when no local copy exists. Also downloads or refreshes that copy (`j2gha docs fetch jenkins`). Use whenever a task needs Jenkins facts you would otherwise guess or web-search, e.g. while analysing or converting a Jenkinsfile, explaining a step, or citing Jenkins docs.
argument-hint: "[step | directive | question] [--fetch]"
---

# Jenkins documentation (local first)

Local docs are optional. Use them when present; never fail a task because they are missing.

## 1. Locate the bundle

```bash
uv run j2gha docs path jenkins     # prints the bundle dir, or exits 1 if not downloaded
```

- **Found** → work from that directory (call it `$J`). It is gitignored, so always pass `$J` explicitly as the
  Grep/Glob path (repo-root searches skip it).
- **Not found** → if the task needs more than one or two lookups, or `$ARGUMENTS` contains `--fetch`, download it
  (about 1 minute):
  `uv run j2gha docs fetch jenkins`. The `controller` part needs Docker (the harness controller is started
  automatically). Without Docker, run `--parts handbook,declarative,plugins` (a bundle labelled `latest`). Otherwise
  use the web fallback (section 4).
- A failed or interrupted fetch leaves the existing bundle, the default and the indexes as they were.

## 2. Where to look in `$J`

| Need | Read |
|---|---|
| Step parameters, exactly as the harness controller runs them | `$J/steps/<step>.md` (header shows plugin + version) |
| Step from a plugin the controller doesn't have | Grep `` `<step>` `` in `$J/plugins/INDEX.md` → `$J/plugins/<plugin>.md` (latest release) |
| Declarative section/directive semantics (`agent`, `post`, `when`, `matrix`, `input`, ordering rules) | `$J/handbook/pipeline/syntax.md` (Grep the heading, read only that range) |
| An `options` / `triggers` / `parameters` / `when` / `agent` symbol (e.g. `cron` with `TZ=`, `disableConcurrentBuilds`) | `$J/declarative/<directive>/<symbol>.md` (list: `$J/declarative/INDEX.md`). The page header says "installed" (exact) or "latest release" |
| `env` variables, `currentBuild`, `params`, `docker`, `scm` | `$J/globals/<name>.md` |
| Scripted pipeline, CPS, `@NonCPS`, sandbox | `$J/handbook/pipeline/cps-method-mismatches.md`, `$J/handbook/cps/*.md` |
| Shared libraries, Docker, multibranch, credentials | `$J/handbook/pipeline/*.md`, `$J/handbook/using/using-credentials.md` |
| Exact core + plugin versions | `$J/plugins.md`, `$J/manifest.json` |

Read `$J/INDEX.md` only when you don't know which page you need. It is llms.txt-style: one line per page with a
blurb. Prefer Grep with `-n` plus a ranged Read over reading whole pages. `syntax.md` alone is about 70 KB.

Cite the `> Source:` line at the top of each page, plus the bundle version, when you report a fact.

## 3. Cross-referencing to GitHub Actions

```bash
uv run j2gha docs xref stash input when cron   # per construct: catalog decision, note, Jenkins pages, GHA pages
uv run j2gha docs xref input --gha-version ghes-3.18   # resolve the GHA side in another version's bundle
```

`<docs>/xref.md` holds the whole table with relative links. GHA pages resolve locally when the `gha-docs` bundle
exists. Otherwise they link to that GitHub version on docs.github.com. "not in the <version> docs" means that version's
bundle lacks the page. Use the `gha-docs` skill for the GitHub side.

## 4. Web fallback (no local bundle)

- **Step reference:** `https://www.jenkins.io/doc/pipeline/steps/<plugin>/`. If you don't know the plugin, try
  `https://www.jenkins.io/doc/pipeline/steps/` and search the page.
- **Declarative syntax:** `https://www.jenkins.io/doc/book/pipeline/syntax/`.
- **Installed-version step reference straight from the running controller:**
  `curl -su admin:j2gha-local-only http://127.0.0.1:18080/pipeline-syntax/html` (about 1 MB of HTML; grep it, don't
  read it whole).

Web pages reflect the latest plugin releases, not the harness controller's versions. Say so when it matters.

## Versions

- A bundle documents the running harness controller. Its label is the core version plus a digest of the plugin set,
  e.g. `2.580.1+pc233737f`, so a different plugin set gets its own bundle. Bundles labelled with the core version only
  (`2.580.1`, from older fetches) still work.
- Steps and globals are exact for that controller's plugin set. The handbook is pinned by jenkins.io commit (recorded
  in `manifest.json`). `declarative/` and `plugins/` reflect the latest plugin releases.
- Commands:
  - Pin the handbook: `uv run j2gha docs fetch jenkins --ref <jenkins.io-sha>`.
  - Refresh one part of an existing bundle, keeping the others:
    `uv run j2gha docs fetch jenkins --label <bundle> --parts handbook`.
  - See what's present: `uv run j2gha docs status`.
  - Switch the default: `uv run j2gha docs use jenkins <version>`, or set `J2GHA_DOCS_JENKINS=<version>`. A
    controller fetch makes its bundle the default.
- `--version X.Y.Z` on `fetch` only checks the running controller's core; it is refused if they differ. To document a
  different Jenkins, change `J2GHA_JENKINS_BASE` / `docker/jenkins/plugins.txt`, rebuild the controller, then fetch
  again.
