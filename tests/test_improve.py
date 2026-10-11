import json
import subprocess

from j2gha import improve


def _example(root, i, steps=None, unknown=None, auto=50.0, verdict=None, ok=True):
    d = root / i
    (d / "analysis").mkdir(parents=True)
    (d / "gha").mkdir()
    (d / "analysis" / "analysis.json").write_text(json.dumps({
        "steps": steps or {}, "unknown_steps": unknown or [], "coverage": {"weighted_mapped_pct": 80.0},
        "complexity": {"score": 10}}))
    (d / "gha" / "conversion.json").write_text(json.dumps({"automation_pct": auto, "counts": {"manual": 1}}))
    (d / "gha" / "validation.json").write_text(json.dumps({"ok": ok, "security_ok": True}))


def test_gaps_rank_by_count_times_weight_and_skip_holdout(tmp_path, monkeypatch):
    monkeypatch.setattr(improve, "holdout_ids", lambda: {"002"})
    _example(tmp_path, "001", {"stash": {"count": 4, "category": "policy"}, "sh": {"count": 90, "category": "direct"}},
             [{"name": "rocketSend", "count": 2, "lines": [1]}])
    _example(tmp_path, "002", {"build": {"count": 50, "category": "redesign"}})
    rows = improve.gaps(["001", "002"], examples_dir=tmp_path)
    assert [r["step"] for r in rows] == ["stash", "rocketSend"]  # direct steps and holdout examples are not gaps
    assert rows[0]["cost"] == 4 * 1.5 and rows[1]["in_catalog"] is False
    assert "build" in [r["step"] for r in improve.gaps(["001", "002"], tmp_path, include_holdout=True)]


def test_scoreboard_compare_flags_regressions_not_improvements(tmp_path):
    _example(tmp_path, "001", auto=60.0)
    base = improve.scoreboard(["001"], tmp_path)
    base["examples"]["001"]["verdicts"]["act"] = "equivalent"
    _example(tmp_path, "002", auto=10.0)
    better = json.loads(json.dumps(base))
    better["examples"]["001"]["automation_pct"] = 70.0
    reg, imp, unmeasured = improve.compare(base, better)
    assert not reg and not unmeasured and imp == ["001: automation_pct 60.0 -> 70.0"]
    worse = json.loads(json.dumps(base))
    worse["examples"]["001"]["automation_pct"] = 50.0
    worse["examples"]["001"]["verdicts"]["act"] = "inconclusive"
    worse["examples"]["001"]["static_ok"] = False
    reg, _, _ = improve.compare(base, worse)
    assert len(reg) == 3
    reg, _, _ = improve.compare(base, {"examples": {}})
    assert reg == ["001: missing from the current scoreboard"]


def test_a_tier_that_was_not_rerun_is_unmeasured_not_a_regression(tmp_path):
    _example(tmp_path, "001")
    base = improve.scoreboard(["001"], tmp_path)
    base["examples"]["001"]["verdicts"] = {"act": "equivalent", "selfhosted": "equivalent", "hosted": "none"}
    now = json.loads(json.dumps(base))
    now["examples"]["001"]["verdicts"]["selfhosted"] = "stale"
    reg, _, unmeasured = improve.compare(base, now)
    assert reg == [] and len(unmeasured) == 1 and "selfhosted" in unmeasured[0]
    now["examples"]["001"]["verdicts"]["act"] = "differs"  # a re-measured tier that got worse still regresses
    assert improve.compare(base, now)[0] == ["001: act verdict equivalent -> differs"]


def test_gaps_unmapped_only_and_parse_debris(tmp_path, monkeypatch):
    monkeypatch.setattr(improve, "holdout_ids", lambda: set())
    steps = {"stash": {"count": 4, "category": "policy"}, "readFile": {"count": 3, "category": "policy"},
             "docker.image).inside": {"count": 1, "category": "policy"}}
    _example(tmp_path, "001", steps, [{"name": "rocketSend", "count": 2, "lines": [1]}])
    (tmp_path / "001" / "gha" / "conversion.json").write_text(json.dumps({"items": [
        {"jenkins": "readFile", "status": "manual"}, {"jenkins": "stash", "status": "mapped"}]}))
    assert [r["step"] for r in improve.gaps(["001"], tmp_path)] == ["stash", "readFile", "rocketSend"]  # no debris
    only = improve.gaps(["001"], tmp_path, unmapped_only=True)
    assert [r["step"] for r in only] == ["readFile", "rocketSend"]  # stash is catalogued and mapped in the report


def test_guard_blocks_oracle_edits_and_weakened_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(improve.config, "ROOT", tmp_path)
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, check=True,
                                    capture_output=True)
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "protected.txt").write_text("[protected]\nj2gha/runners/*\n[review]\nj2gha/trace.py\n")
    for f, body in {"j2gha/runners/x.py": "a\n", "j2gha/trace.py": "a\n", "j2gha/rules/steps.yaml": "steps:\n  sh: {category: direct, weight: 1}\n",
                    "tests/test_x.py": "assert 1\nassert 2\n"}.items():
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text(body)
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")
    assert improve.guard("HEAD") == ([], [])
    (tmp_path / "j2gha/rules/steps.yaml").write_text(
        "steps:\n  sh: {category: direct, weight: 1}\n  new: {category: policy, weight: 1}\n")  # allowed
    (tmp_path / "j2gha/trace.py").write_text("b\n")  # review only
    (tmp_path / "tests/test_x.py").write_text("assert 1\nassert 2\nassert 3\n")  # additions are fine
    bad, notes = improve.guard("HEAD")
    assert bad == [] and len(notes) == 1
    (tmp_path / "j2gha/runners/x.py").write_text("b\n")
    (tmp_path / "tests/test_x.py").write_text("assert 1\n")
    bad, _ = improve.guard("HEAD")
    assert any("runners" in b for b in bad) and any("tests weakened" in b for b in bad)


def test_guard_blocks_catalog_downgrades_but_allows_new_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(improve.config, "ROOT", tmp_path)
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, check=True,
                                    capture_output=True)
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "protected.txt").write_text("[protected]\n")
    cat = tmp_path / "j2gha/rules/steps.yaml"
    cat.parent.mkdir(parents=True)
    cat.write_text("steps:\n  sh: {category: direct, weight: 1, gha: run}\n  slackSend: {category: policy, weight: 1}\n")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")
    cat.write_text("steps:\n  sh: {category: direct, weight: 1, gha: 'run: bash'}\n"
                   "  slackSend: {category: policy, weight: 1}\n  rocketSend: {category: policy, weight: 1}\n")
    assert improve.guard("HEAD") == ([], [])  # a new entry and a reworded `gha` target are fine
    cat.write_text("steps:\n  sh: {category: direct, weight: 0.1}\n  slackSend: {category: noop, weight: 1}\n")
    bad, _ = improve.guard("HEAD")
    assert sorted(bad) == ["existing catalog entry 'sh': weight 1 -> 0.1",
                           "existing catalog entry 'slackSend': category policy -> noop"]
    cat.write_text("steps:\n  slackSend: {category: policy, weight: 1}\n")
    assert improve.guard("HEAD")[0] == ["existing catalog entry 'sh' removed"]
    cat.write_text("not: a catalog\n")
    assert improve.guard("HEAD")[0] == ["existing catalog is no longer a mapping with a `steps:` section"]


def test_guard_allows_list_edits_but_not_logic_edits_in_mixed_files(tmp_path, monkeypatch):
    monkeypatch.setattr(improve.config, "ROOT", tmp_path)
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, check=True,
                                    capture_output=True)
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "protected.txt").write_text("[lists]\nj2gha/trace.py: TRACED_STEPS\n")
    f = tmp_path / "j2gha/trace.py"
    f.parent.mkdir()
    base = 'TRACED_STEPS = ["sh"]\n\n\ndef compare(a, b):\n    return a == b\n'
    f.write_text(base)
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")
    f.write_text(base.replace('["sh"]', '[\n    "sh",  # a comment\n    "rocketSend",\n]'))
    assert improve.guard("HEAD") == ([], [])  # the list may grow, formatting and comments are free
    f.write_text(base.replace("a == b", "True"))
    assert improve.guard("HEAD")[0] == ["j2gha/trace.py changed outside TRACED_STEPS"]
    f.write_text(base + "OTHER = 1\n")
    assert improve.guard("HEAD")[0] == ["j2gha/trace.py changed outside TRACED_STEPS"]
    f.write_text("def broken(:\n")
    assert improve.guard("HEAD")[0] == ["j2gha/trace.py no longer parses"]
