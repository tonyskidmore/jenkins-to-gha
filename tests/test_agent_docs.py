"""The agent material that Claude Code and GitHub Copilot share stays loadable and accurate.

It covers AGENTS.md, the path-scoped rules in .github/instructions (also .claude/rules), the skills, the custom
agent, the hook and the docs.
"""

import glob
import importlib.util
import json
import os
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
RULES = sorted((ROOT / ".github" / "instructions").glob("*.instructions.md"))
SKILLS = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
AGENTS = sorted((ROOT / ".github" / "agents").glob("*.agent.md"))
SKILL_KEYS = {"name", "description", "argument-hint", "license", "compatibility", "metadata", "allowed-tools",
              "disable-model-invocation", "user-invocable"}


def frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path}: no frontmatter"
    head, _, body = text[4:].partition("\n---\n")
    return yaml.safe_load(head), body


def test_agents_md_is_the_short_root_and_claude_md_stays_local():
    lines = (ROOT / "AGENTS.md").read_text().splitlines()
    assert len(lines) <= 130, "AGENTS.md is always loaded: route to docs/ and the rule files instead of growing it"
    assert "/CLAUDE.md" in (ROOT / ".gitignore").read_text().splitlines()


@pytest.mark.skipif(os.name == "nt", reason="a symlink checks out as a text file without core.symlinks")
def test_claude_rules_is_the_copilot_instructions_directory():
    assert (ROOT / ".claude" / "rules").resolve() == (ROOT / ".github" / "instructions").resolve()


@pytest.mark.parametrize("rule", RULES, ids=lambda p: p.name)
def test_rule_files_scope_the_same_files_for_both_agents(rule):
    meta, body = frontmatter(rule)
    assert meta.get("description"), "VS Code uses the description to load a rule on demand"
    apply_to = [g for g in meta["applyTo"].split(",") if g]
    assert apply_to == meta["paths"], "Copilot reads applyTo, Claude Code reads paths: keep them identical"
    for pattern in apply_to:
        assert glob.glob(str(ROOT / pattern), recursive=True), f"{pattern} matches no file"
    assert "Reference:" in body
    assert f"`{rule.name.removesuffix('.instructions.md')}`" in (ROOT / "AGENTS.md").read_text(), \
        "AGENTS.md's layout table names every rule file"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skills_load_in_claude_code_and_copilot(skill):
    meta, body = frontmatter(skill)
    assert set(meta) <= SKILL_KEYS, f"unexpected keys {set(meta) - SKILL_KEYS}"
    assert meta["name"] == skill.parent.name and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"])
    assert 0 < len(meta["description"]) <= 1024
    assert "$ARGUMENTS" not in body, "Copilot does not substitute $ARGUMENTS: refer to the user's request"


def test_video_skills_stay_out_of_the_default_context():
    for name in ("narrated-explainer", "hyperframes-walkthrough"):
        meta, _ = frontmatter(ROOT / ".claude" / "skills" / name / "SKILL.md")
        assert meta.get("disable-model-invocation") is True


@pytest.mark.parametrize("agent", AGENTS, ids=lambda p: p.name)
def test_custom_agents(agent):
    meta, body = frontmatter(agent)
    assert meta["name"] == agent.name.removesuffix(".agent.md") and meta["description"]
    assert set(meta.get("tools", [])) <= {"execute", "read", "search", "edit", "agent", "web", "todo", "skill"}
    assert "## Rules" in body


def _hook():
    spec = importlib.util.spec_from_file_location("hosted_guard", ROOT / ".github" / "hooks" / "hosted_guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hook_config_runs_the_guard():
    config = json.loads((ROOT / ".github" / "hooks" / "j2gha.json").read_text())
    assert config["version"] == 1
    for entry in config["hooks"]["preToolUse"]:
        assert ".github/hooks/hosted_guard.py" in entry["bash"] and entry["timeoutSec"] <= 30


@pytest.mark.parametrize("command,asks", [
    ("uv run j2gha run 004 --tier hosted --yes --max-minutes 10", True),
    ("uv run j2gha pipeline 004 --tier=jenkins,act,hosted", True),
    ("uv run j2gha run 004 --tier selfhosted", False),
    ("uv run j2gha run 004 --tier jenkins,act", False),
    ("uv run j2gha budget", False),
    ("git status", False),
])
def test_hook_asks_before_a_hosted_run(command, asks):
    guard = _hook()
    event = {"toolName": "bash", "toolArgs": {"command": command}}
    decision = guard.decide(event, {})
    assert (decision is not None) == asks
    if asks:
        assert decision["permissionDecision"] == "ask" and "minutes" in decision["permissionDecisionReason"]
        assert guard.decide(event, {"J2GHA_AGENT_HOSTED": "1"}) is None
    assert guard.decide({"toolName": "view", "toolArgs": {"path": command}}, {}) is None
    # the PascalCase (VS Code / Claude format) payload and a JSON-string toolArgs work too
    pascal = {"tool_name": "Bash", "tool_input": json.dumps({"command": command})}
    assert (guard.decide(pascal, {}) is not None) == asks


def _slug(heading: str) -> str:
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    seen: dict[str, int] = {}
    out = set()
    for line in path.read_text().splitlines():
        if m := re.match(r"#{1,6}\s+(.*)", line):
            slug = _slug(m.group(1))
            n = seen.get(slug, 0)
            seen[slug] = n + 1
            out.add(slug if n == 0 else f"{slug}-{n}")
    return out


LINKED = [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md")),
          *RULES, *SKILLS, *AGENTS]


@pytest.mark.parametrize("doc", LINKED, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(doc):
    text = re.sub(r"```.*?```", "", doc.read_text(), flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    broken = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"[a-z]+:", target):
            continue
        path, _, anchor = target.partition("#")
        resolved = (doc.parent / path).resolve() if path else doc.resolve()
        if not resolved.is_relative_to(ROOT):
            continue  # a URL relative to the repository on GitHub, such as ../../../releases/...
        if not resolved.exists():
            broken.append(target)
        elif anchor and resolved.suffix == ".md" and anchor not in _anchors(resolved):
            broken.append(target)
    assert not broken
