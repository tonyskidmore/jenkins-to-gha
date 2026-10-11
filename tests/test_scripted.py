"""Scripted pipelines: source order, wrapper scopes around stages and try/catch/finally semantics.

Fixtures are real Groovy 2.4 parses (``dump_sources``) of ``tests/fixtures/Jenkinsfile.scripted-*``.
"""

import json
import re
from pathlib import Path

import pytest

from j2gha.analysis.declarative import build_ir
from j2gha.convert.generator import convert
from j2gha.runners.variants import make_variant

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
EVENT = re.compile(r'\{"stage":"[^"]*","step":"[^"]*"\}')


def _load(name: str) -> tuple[str, dict]:
    text = (FIXTURES / f"Jenkinsfile.{name}").read_text()
    return text, json.loads((FIXTURES / f"{name}.ast.json").read_text())


def _convert(name: str):
    text, ast = _load(name)
    ir = build_ir(ast)
    return ir, convert(ir, text, title=name)["workflow"]


def _steps(wf: dict, *kinds: str) -> list[dict]:
    """Steps of the given Jenkins kinds, in workflow order (checkout/bookkeeping steps left out)."""
    return [s for job in wf["jobs"].values() for s in job["steps"] if s.get("_j2gha", {}).get("kind") in kinds]


def _at(wf: dict, line: int, kind: str = "sh") -> dict:
    found = [s for s in _steps(wf, kind) if s["_j2gha"].get("line") == line]
    assert len(found) == 1, (line, kind, found)
    return found[0]


def _events(wf: dict) -> list[str]:
    variant, _ = make_variant(wf, "trace", "act", {"branch": "main"})
    return [m.group(0) for job in variant["jobs"].values() for s in job["steps"]
            for m in EVENT.finditer(s.get("run") or "")]


def _ev(stage: str, step: str) -> str:
    return json.dumps({"stage": stage, "step": step}, separators=(",", ":"))


# --------------------------------------------------------------------------------------------------- order
def test_statements_between_stages_keep_their_position():
    ir, wf = _convert("scripted-order")
    # one anonymous segment per run of statements between stages; `stage('Lint'){..} stage('Docs'){..}` on one line
    # (a Groovy command chain) gives both stages
    assert [(s.name, s.line) for s in ir.stages] == [("", 2), ("Build", 3), ("", 4), ("Test", 5), ("Lint", 6),
                                                       ("Docs", 6), ("", 7)]
    seq = [(s["_j2gha"]["stage"], s["_j2gha"]["kind"], s["_j2gha"]["line"]) for s in _steps(wf, "sh", "deleteDir")]
    assert seq == [("", "sh", 2), ("Build", "sh", 3), ("", "sh", 4), ("Test", "sh", 5), ("Lint", "sh", 6),
                   ("Docs", "sh", 6), ("Release", "sh", 8), ("", "deleteDir", 10)]
    assert "env.BRANCH_NAME == 'main'" in _at(wf, 8)["if"]  # stage inside a top-level if keeps its condition
    assert any(n.startswith("line 7: top-level if") and "'Release'" in n for n in ir.notes)
    assert any("kept in source order in 3 unnamed segment(s)" in n for n in ir.notes)
    # Jenkins prints an empty STAGE_NAME outside stage(): the GHA markers of the anonymous segments match it
    assert _events(wf) == [_ev("", "sh"), _ev("Build", "sh"), _ev("", "sh"), _ev("Test", "sh"), _ev("Lint", "sh"),
                           _ev("Docs", "sh"), _ev("Release", "sh"), _ev("", "deleteDir")]


# ----------------------------------------------------------------------------------------------- try/catch
def test_catch_around_stages_runs_only_on_failure_right_after_them():
    ir, wf = _convert("scripted-try")
    assert not ir.post  # one job: handled in place, not moved to pipeline post
    assert [(s.name, s.line) for s in ir.stages] == [("Build", 3), ("Test", 4), ("", 6), ("Report", 7), ("", 8),
                                                       ("Deploy", 12), ("", 13)]
    handler = ir.stages[2].steps[0]  # the catch body: a <try> with an empty body, as the generator knows it
    assert (handler.name, handler.line, handler.body) == ("<try>", 2, [])
    assert [s.name for s in handler.named["_catch"]] == ["sh"]
    report = ir.stages[3].steps[0]
    assert report.name == "<try>" and report.named["_catch"][0].name == "echo"  # a stage inside the catch
    assert [list(s.named) for s in ir.stages[4].steps] == [["_catch"], ["_finally"]]  # throw e, then finally

    order = [(s["_j2gha"]["stage"], s["_j2gha"]["kind"], s["_j2gha"]["line"])
             for s in _steps(wf, "sh", "echo", "junit", "script-manual")]
    assert order == [("Build", "sh", 3), ("Test", "sh", 4), ("", "sh", 6), ("Report", "echo", 7),
                     ("", "script-manual", 8), ("", "junit", 10), ("Deploy", "sh", 12), ("", "sh", 14),
                     ("", "echo", 16)]
    for line, kind in ((6, "sh"), (7, "echo"), (8, "script-manual")):  # catch bodies of the try around stages
        assert "failure()" in _at(wf, line, kind).get("if", ""), (line, kind)
    # a try with its own body: the catch runs only for a failure of that body, once the try was entered
    smoke, catch = _at(wf, 14), _at(wf, 16, "echo")
    entry = next(s for job in wf["jobs"].values() for s in job["steps"] if s["_j2gha"]["kind"] == "try-entry")
    assert f"steps.{smoke['id']}.outcome == 'failure'" in catch["if"] and "always()" in catch["if"]
    assert f"steps.{entry['id']}.outcome == 'success'" in catch["if"]
    assert "always()" in _at(wf, 10, "junit")["if"]  # finally
    for line in (3, 4, 12, 14):  # try bodies and later stages stay unconditional
        assert "failure()" not in _at(wf, line).get("if", "")
    assert any(n.startswith("line 2: try around stage(s) 'Build', 'Test'") and "failure()" in n for n in ir.notes)
    assert any(n.startswith("line 15: catch does not rethrow") for n in ir.notes)
    assert not any(n.startswith("line 5: catch does not rethrow") for n in ir.notes)  # `throw e` rethrows
    # markers as written in the trace variant (the catch ones only print on failure), labelled as Jenkins does:
    # catch/finally bodies outside stage() have an empty STAGE_NAME, a stage inside the catch keeps its name
    assert _events(wf) ==[_ev("Build", "sh"), _ev("Test", "sh"), _ev("", "sh"), _ev("Report", "echo"),
                           _ev("", "junit"), _ev("Deploy", "sh"), _ev("", "sh"), _ev("", "echo")]


def test_catch_around_stages_in_several_jobs_goes_to_post_failure():
    ir, wf = _convert("scripted-try-jobs")
    assert [(s.name, s.agent.label if s.agent else None) for s in ir.stages] == [("Build", None),
                                                                                 ("Package", "windows")]
    assert [(s.name, s.line) for s in ir.post["failure"]] == [("echo", 9), ("<throw>", 10)]
    assert [(s.name, s.line) for s in ir.post["cleanup"]] == [("echo", 12)]  # after the catch body, as in Jenkins
    assert any("spanning several jobs" in n and "post failure" in n for n in ir.notes)
    catch_echo = _at(wf, 9, "echo")
    assert "failure" in catch_echo["if"] and catch_echo in wf["jobs"]["post"]["steps"]
    assert "failure" not in _at(wf, 12, "echo").get("if", "")
    assert wf["jobs"]["package"]["runs-on"] == "windows-latest"


# --------------------------------------------------------------------------------------------- wrappers
def test_wrappers_around_a_stage_are_reapplied_inside_it():
    ir, wf = _convert("scripted-wrappers")
    deploy = next(s for s in ir.stages if s.name == "Deploy")
    chain, step = [], deploy.steps[0]
    while step.body:
        assert len(step.body) == 1
        chain.append((step.name, step.line))
        step = step.body[0]
    assert chain == [("withCredentials", 2), ("withEnv", 3), ("timeout", 4), ("retry", 5), ("dir", 6)]
    assert (step.name, step.line) == ("sh", 8)
    for line in (7, 8):  # the loose step inside the wrappers gets the same scope as the stage
        run = _at(wf, line)
        assert run["working-directory"] == "deploy"
        assert run["env"]["TOKEN"] == "${{ secrets.DEPLOY_TOKEN }}" and run["env"]["TARGET"] == "prod"
        assert run["timeout-minutes"] == 10
        assert "seq 1 3" in run["run"]  # retry(3) loop
    verify = _at(wf, 16)
    assert "docker run" in verify["run"] and "node:20" in verify["run"]  # docker.image().inside around the stage
    for line, what in ((2, "withCredentials"), (3, "withEnv"), (4, "timeout"), (5, "retry"), (6, "dir"),
                       (15, "inside")):
        assert any(n.startswith(f"line {line}: ") and what in n for n in ir.notes), what
    assert any(n.startswith("line 4: ") and "approximated" in n for n in ir.notes)  # block-level timeout
    assert any(n.startswith("line 14: timestamps {}") and "dropped" in n for n in ir.notes)
    assert _events(wf) == [_ev("", "sh"), _ev("Deploy", "sh"), _ev("Verify", "sh")]


def test_node_inside_a_wrapper_still_sets_the_runner():
    ir, wf = _convert("scripted-node-wrapper")
    assert ir.agent.label == "windows"
    assert [s["run"] for s in _steps(wf, "bat")] == ["build.bat"]
    assert all(job["runs-on"] == "windows-latest" for job in wf["jobs"].values())


# ----------------------------------------------------------------------------------------------- corpus
def _corpus(ex: str):
    ast_file = ROOT / "examples" / ex / "analysis" / "groovy-ast.json"
    if not ast_file.exists():
        pytest.skip(f"examples/{ex} has no saved AST")
    ir = build_ir(json.loads(ast_file.read_text()))
    wf = convert(ir, (ROOT / "examples" / ex / "Jenkinsfile").read_text(), title=ex)["workflow"]
    return ir, [s["_j2gha"] for job in wf["jobs"].values() for s in job["steps"] if s["_j2gha"].get("line")]


def test_corpus_019_stash_and_unstash_stay_in_order():
    _, metas = _corpus("019")
    lines = [m["line"] for m in metas]
    assert lines == sorted(lines)  # every node {}/stage in source order
    kinds = [(m["kind"], m["line"]) for m in metas]
    assert kinds.index(("stash", 73)) > max(i for i, m in enumerate(metas) if m["stage"] == "Git Checkout")
    assert kinds.index(("stash", 73)) < kinds.index(("unstash", 87))
    assert kinds.index(("stash", 168)) > max(i for i, m in enumerate(metas) if m["stage"] == "Build")
    assert kinds.index(("stash", 168)) < kinds.index(("unstash", 187))


def test_corpus_020_trailing_delete_dir_runs_last():
    _, metas = _corpus("020")
    assert (metas[-1]["kind"], metas[-1]["line"], metas[-1]["stage"]) == ("deleteDir", 64, "")
    assert [m["line"] for m in metas] == sorted(m["line"] for m in metas)
