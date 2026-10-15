# Using GitHub Copilot

`j2gha` needs no AI agent ([AI.md](AI.md)). If you use GitHub Copilot, it can drive the CLI with this repository's
skills and explain what the harness produced. This page covers:

- what Copilot loads from the repository;
- how to ask it to use a skill;
- settings for working on private pipelines;
- using a local model.

Copilot CLI behaviour was checked with Copilot CLI 1.0.98 in October 2026. The other Copilot surfaces are described
from GitHub's documentation.

## What Copilot reads from this repository

Claude Code reads the same files, so one set of instructions serves both.

| | Copilot CLI | VS Code (Copilot agent) | Copilot cloud agent |
|---|---|---|---|
| `AGENTS.md`: the root instructions, always loaded | Yes (checked) | Yes (documented) | Yes (documented) |
| `.github/instructions/*.instructions.md`: rules scoped by `applyTo`, loaded for matching files | Yes (checked) | Yes (documented) | Yes (documented) |
| Skills in `.claude/skills/` | Yes (checked) | Yes (documented) | Yes (documented) |
| The `j2gha-migrator` agent in `.github/agents/` | Yes (documented) | Yes (documented) | Yes (documented) |
| The hook in `.github/hooks/` | Yes (documented) | Preview | Yes (documented) |

To check from a clone:

```bash
copilot instruction list    # AGENTS.md and the eleven rule files, each with its applyTo globs
copilot skill list          # the project skills from .claude/skills/
```

**How the instructions are layered:**

- **`AGENTS.md`** is short: what j2gha is, where to find things, the commands and the rules that apply everywhere.
- **The rule files** carry the detail for one area each, for example the generator or the corpus. They load only when
  Copilot works on matching files.
- **A skill's** name and description load up front; the rest is read only when the skill is used.
- **The two video skills** are marked `disable-model-invocation`, so they never enter Copilot's context unless you
  invoke them by name.

## Skills for converting pipelines

| Skill | Use it to |
|---|---|
| `jenkins-to-gha` | Analyse, convert, validate and run a pipeline, then read the results |
| `jenkins-docs` | Look up Jenkins steps, directives and plugins. Uses the local docs bundle, else jenkins.io. |
| `gha-docs` | Look up GitHub Actions syntax and features for GitHub.com, GHEC or a GHES version. Uses the local docs bundle, else docs.github.com. |

The other skills are for other jobs:

- **Maintaining the public corpus:** `jenkins-example-crawler`, `jenkins-example-twin`, `j2gha-rule-improver`.
- **Making videos:** the two video skills.

[skills.md](skills.md) describes them all. The docs skills read the bundles that `uv run j2gha docs fetch` downloads
([documentation.md](documentation.md)).

**Your own pipelines.** If they live outside the clone in `J2GHA_PIPELINES_DIR`
([own-pipelines.md](own-pipelines.md#set-up-a-pipeline)), start Copilot in the clone with that variable exported. Also
give Copilot access to the directory, so it can read the results there:

```bash
export J2GHA_PIPELINES_DIR=~/j2gha-pipelines
copilot --add-dir "$J2GHA_PIPELINES_DIR"
```

**Invoking skills.** Ask for a skill by name, or type `/<skill>` in Copilot CLI. Name the pipeline in your request: the
skills were written for Claude Code, and Copilot does not fill in their `$ARGUMENTS` placeholder, so it works the
arguments out from what you asked. Prompts that work:

- "Use the jenkins-to-gha skill to analyse, convert and validate the payments pipeline, then explain its difficulty
  score and the manual items in its migration report."
- "Why is the payments pipeline rated significant-redesign? Use its analysis/analysis.json."
- "Group the approximated and manual items in the payments pipeline's gha/migration-report.md by stage, and list the
  secrets and environments the workflow needs."

**The `j2gha-migrator` agent** packages this workflow with its rules: keep pipelines local and out of git, explain
before editing, edit only a copy of the workflow, and never change j2gha itself.

- **Select it:** `copilot --agent j2gha-migrator`, or `/agent` in a session (in VS Code, the agent picker).
- **Then ask, for example:** "add ~/src/payments/Jenkinsfile and tell me what its migration needs".

**A tested run.** The first prompt was run on example 000 with Copilot CLI. Copilot:

1. loaded the skill;
2. ran `analyze`, `convert` and `validate`;
3. explained the results, and its figures matched the generated files.

**Limit what it may run.** Say in the prompt which stages it may run, e.g. "do not run `j2gha run`" or
"only `--tier jenkins,act`". Two checks stand behind that:

- The skills tell the agent to ask before any GitHub-hosted run.
- The CLI itself refuses hosted runs without `--yes` and checks the minutes budget.

## Working with private pipelines

**Keep the pipeline local.** Use only the local stages and tiers in
[own-pipelines.md](own-pipelines.md#what-leaves-your-machine). Export `J2GHA_OFFLINE=1` in the shell you start Copilot
from, and the harness refuses anything that would go to GitHub, whatever the agent runs
([offline mode](own-pipelines.md#offline-mode)). What Copilot sends is a separate matter.

**What goes to the model.** Copilot sends your prompts, and the files and command output it reads, to the models your
Copilot plan provides. Which models and features you may use is set by your organisation's Copilot policies, so check
them with whoever administers them.

**Session export.** Copilot CLI exports sessions to GitHub.com when session sync is available. This is the
`remoteExport` setting, which is on by default.

- To keep sessions on your machine, run `copilot config remoteExport false`, or pass `--no-remote-export` for one
  session.
- `/share gist` and `--share-gist` publish a transcript as a gist. `--share <file>` writes it locally instead.

**Tool limits.** `--deny-tool 'shell(git push)'` stops the agent pushing, and a deny rule always beats an allow rule.
Shell rules match a command and its first subcommand only, so they cannot single out one `j2gha run` option.

**The hook** in `.github/hooks/` asks you before the agent starts a GitHub-hosted run (`--tier hosted`), because that
spends Actions minutes.

- Copilot CLI shows the question. A non-interactive run or the cloud agent treats it as a refusal.
- Set `J2GHA_AGENT_HOSTED=1` before starting Copilot to let the agent start hosted runs itself.
- Repository hooks load only in folders you have trusted.

**Content exclusion.** GitHub's documentation does not agree on whether content exclusion applies to Copilot CLI and
agents. Do not rely on it to keep files from Copilot.

## Local models

Copilot CLI can use a model server on your machine instead of GitHub's models ("bring your own key"). With offline
mode, it makes no other network connections: no GitHub sign-in, telemetry, web tools or automatic updates.

```bash
export COPILOT_PROVIDER_BASE_URL=http://localhost:11434/v1   # Ollama, or any OpenAI-compatible server
export COPILOT_MODEL=<model name on that server>
export COPILOT_OFFLINE=true
copilot
```

**Model requirements.** The model must support tool calling and streaming. GitHub recommends a context window of
128k tokens or more; raise the server's own context limit to match.

**What still works.** `AGENTS.md`, the rule files and the skills load as usual.

**What has not been tested.** This repository has not been tested with local models yet. Expect a small model to
follow the skills less reliably than Copilot's hosted models.

**Organisation policy.** Managed settings can stop the CLI from using a local model (`forceLoginOrgs`).

`copilot help providers` lists every setting. GitHub's guide is
[Adding LLM models to GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models).
