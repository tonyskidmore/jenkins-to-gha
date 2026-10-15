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

| | Copilot CLI | VS Code (Copilot agent) | Copilot cloud agent |
|---|---|---|---|
| Skills in `.claude/skills/` | Yes (checked) | Yes (documented) | Yes (documented) |
| `CLAUDE.md` as repository instructions | Yes (checked) | Not documented for the Copilot agent | Yes, at the repository root (documented) |

To check from a clone:

```bash
copilot skill list          # the project skills from .claude/skills/
copilot instruction list    # CLAUDE.md
```

Copilot loads a skill's name and description up front and reads the rest only when it uses the skill, so unused skills
cost little.

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

Ask for a skill by name, or type `/<skill>` in Copilot CLI. Name the pipeline in your request: the skills were written
for Claude Code, and Copilot does not fill in their `$ARGUMENTS` placeholder, so it works the arguments out from what
you asked. Prompts that work:

- "Use the jenkins-to-gha skill to analyse, convert and validate examples/my-pipeline, then explain its difficulty
  score and the manual items in its migration report."
- "Why is examples/my-pipeline rated significant-redesign? Use its analysis/analysis.json."
- "Group the approximated and manual items in examples/my-pipeline/gha/migration-report.md by stage, and list the
  secrets and environments the workflow needs."

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
[own-pipelines.md](own-pipelines.md#what-leaves-your-machine). What Copilot sends is a separate matter.

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

**What still works.** The skills and `CLAUDE.md` load as usual.

**What has not been tested.** This repository has not been tested with local models yet. Expect a small model to
follow the skills less reliably than Copilot's hosted models.

**Organisation policy.** Managed settings can stop the CLI from using a local model (`forceLoginOrgs`).

`copilot help providers` lists every setting. GitHub's guide is
[Adding LLM models to GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models).
