"""Evidence model: trace/outcome comparison, run status, provenance and the exit status of `j2gha run`."""

import json
import subprocess

import pytest

from j2gha.provenance import sha256_json, sha256_text
from j2gha.runners import execute
from j2gha.runners.variants import estimate_minutes, make_variant, matrix_expansion
from j2gha.trace import compare, concurrent_stages


def ev(*pairs):
    return [{"stage": s, "step": st} for s, st in pairs]


# ------------------------------------------------------------------------------------------------ trace comparison
def test_order_matters_within_a_sequential_stage():
    ref = ev(("Build", "sh"), ("Build", "archiveArtifacts"))
    swapped = ev(("Build", "archiveArtifacts"), ("Build", "sh"))
    assert compare(ref, swapped)["verdict"] == "differs"  # publishing before building is not equivalent
    # cells of a matrix (or scripted parallel branches) interleave legitimately
    c = compare(ref, swapped, concurrent={"Build"})
    assert c["verdict"] == "equivalent" and c["stages"][0]["status"] == "reordered"
    # stages of parallel branches interleave: only per-stage sequences are compared
    assert compare(ev(("A", "sh"), ("B", "sh")), ev(("B", "sh"), ("A", "sh")))["equivalent"]


def test_traces_cannot_show_equivalence_on_their_own():
    empty = compare([], [], reference_result="FAILURE", candidate_result="failure")
    assert empty["verdict"] == "inconclusive" and not empty["equivalent"]
    ref = ev(("Build", "sh"))
    # identical traces, but the candidate failed after the last marker (outside the marker contract)
    c = compare(ref, ref, reference_result="SUCCESS", candidate_result="failure")
    assert c["verdict"] == "inconclusive" and not c["equivalent"]
    assert compare(ref, ref, reference_result="SUCCESS", candidate_result="success")["verdict"] == "equivalent"
    # GitHub has no UNSTABLE result: an unstable Jenkins build ends like a successful workflow
    assert compare(ref, ref, reference_result="UNSTABLE", candidate_result="success")["verdict"] == "equivalent"


def test_concurrent_stages_come_from_the_workflow_model():
    def step(stage, **meta):
        return {"name": "x", "_j2gha": {"stage": stage, "trace": True, **meta}}
    model = {"jobs": {
        "build": {"steps": [step("Build"), step("Fan", concurrent=True)]},
        "cells": {"strategy": {"matrix": {"OS": ["a", "b"]}}, "steps": [step("Test")]},
        "a": {"steps": [step("Shared")]}, "b": {"steps": [step("Shared")]},
    }}
    assert concurrent_stages(model) == {"Fan", "Test", "Shared"}


# ------------------------------------------------------------------------------------------------ full mode
MODEL = {"jobs": {"build": {"steps": [
    {"name": "Build: make", "_j2gha": {"stage": "Build"}},
    {"name": "Publish: upload", "_j2gha": {"stage": "Publish"}},
    {"name": "post: ./notify.sh", "_j2gha": {"stage": "Declarative: Post Actions"}},
    {"name": "Checkout", "_j2gha": {"trace_events": [["Declarative: Checkout SCM", "checkout"]]}},
]}}}


def _ref(result, failed=None):
    stages = [{"name": "Build", "status": "SUCCESS"}] + ([{"name": failed, "status": "FAILED"}] if failed else [])
    return {"result": result, "stages": stages}


@pytest.mark.parametrize("ref, rec, verdict", [
    (_ref("SUCCESS"), {"result": "success"}, "equivalent"),
    (_ref("FAILURE", "Publish"), {"result": "failure", "failed_steps": ["Publish: upload"]}, "equivalent"),
    (_ref("FAILURE", "Publish"), {"result": "failure", "failed_steps": ["Build: make"]}, "differs"),
    (_ref("FAILURE", "Declarative: Post Actions"), {"result": "failure", "failed_steps": ["post: ./notify.sh"]},
     "equivalent"),
    (_ref("SUCCESS"), {"result": "failure", "failed_steps": ["Build: make"]}, "differs"),
    # the failing location is unknown on one side: not evidence of the same failure
    (_ref("FAILURE"), {"result": "failure", "failed_steps": ["Build: make"]}, "inconclusive"),
    (_ref("FAILURE", "Publish"), {"result": "failure"}, "inconclusive"),
    # infrastructure states never compare equal
    (_ref("NOT_RUN"), {"result": "timeout"}, "inconclusive"),
    (_ref("ABORTED"), {"result": "cancelled"}, "inconclusive"),
    (_ref("UNSTABLE"), {"result": "failure"}, "inconclusive"),
])
def test_compare_outcome(ref, rec, verdict):
    c = execute.compare_outcome(ref, {"jobs": [{"name": "build"}], **rec}, MODEL)
    assert c["verdict"] == verdict and c["equivalent"] == (verdict == "equivalent")


def test_run_status():
    assert execute.run_status({"result": "SUCCESS"}) == "ran"
    assert execute.run_status({"result": "failure"}) == "ran"
    for result in ("NOT_RUN", "timeout", "error", None):
        assert execute.run_status({"result": result}) == "infra"
    assert execute.run_status({"result": "cancelled", "error": "timed out; run cancelled"}) == "infra"
    assert execute.run_status({"result": "refused"}) == "refused"


# ------------------------------------------------------------------------------------------------ run_example
@pytest.fixture
def example(tmp_path, monkeypatch):
    d = tmp_path / "901"
    (d / "gha").mkdir(parents=True)
    (d / "Jenkinsfile").write_text("pipeline { agent any; stages { stage('Build') { steps { sh 'make' } } } }\n")
    model = {"jobs": {"build": {"steps": [{"name": "Build: make", "run": "make",
                                            "_j2gha": {"kind": "sh", "stage": "Build", "trace": True}}]}}}
    (d / "gha" / "workflow.model.json").write_text(json.dumps(model))
    (d / "gha" / "conversion.json").write_text(json.dumps({
        "source_sha256": sha256_text((d / "Jenkinsfile").read_text()), "model_sha256": sha256_json(model)}))
    (d / "README.md").write_text("# 901\n")
    monkeypatch.setattr(execute, "image_provenance", lambda: {})
    return d


def _jenkins(result="SUCCESS", traces=None):
    def run(d, mode, scenario, docker=False):
        return {"tier": "jenkins", "mode": mode, "scenario": scenario, "result": result, "stages": [],
                "traces": ev(("Build", "sh")) if traces is None else traces}
    return run


def _act(result="success", traces=None):
    seen = {}

    def run(out, yml, branch, mode, source=None, timeout=0):
        seen.update(branch=branch, source=source, yml=yml)
        return {"tier": "act", "mode": mode, "result": result, "traces": ev(("Build", "sh")) if traces is None
                else traces}
    run.seen = seen
    return run


def test_run_example_statuses_and_verdicts(example, monkeypatch):
    import j2gha.jenkins.run as jrun
    import j2gha.runners.act as act
    monkeypatch.setattr(jrun, "run_jenkins", _jenkins())
    monkeypatch.setattr(act, "run_act", _act())
    res = execute.run_example(example, ["jenkins", "act"])
    assert res["ok"] and res["statuses"] == {"jenkins": "ran", "act": "ran"} and res["verdicts"] == {"act": "equivalent"}
    rec = json.loads((example / "runs" / "act-trace" / "result.json").read_text())
    assert rec["provenance"]["model_sha256"] and rec["provenance"]["scenario"]["branch"] == "main"
    # act fails without markers against a successful reference: a result, judged by the comparison
    monkeypatch.setattr(act, "run_act", _act("failure", []))
    res = execute.run_example(example, ["act"])
    assert res["ok"] and res["verdicts"] == {"act": "differs"}
    # a Jenkins run that never started is no reference: an error, and the act run is not judged against it
    monkeypatch.setattr(jrun, "run_jenkins", _jenkins("NOT_RUN", []))
    res = execute.run_example(example, ["jenkins", "act"])
    assert not res["ok"] and res["statuses"]["jenkins"] == "infra" and res["verdicts"] == {"act": "inconclusive"}
    assert "did not run" in res["records"]["act"]["comparison"]["inconclusive"]["reason"]


def test_reference_must_match_jenkinsfile_and_scenario(example, monkeypatch):
    import j2gha.jenkins.run as jrun
    import j2gha.runners.act as act
    monkeypatch.setattr(jrun, "run_jenkins", _jenkins())
    monkeypatch.setattr(act, "run_act", _act())
    execute.run_example(example, ["jenkins"])  # reference recorded for branch main
    res = execute.run_example(example, ["act"], branch="release/1")
    c = res["records"]["act"]["comparison"]
    assert c["verdict"] == "inconclusive" and "scenario" in c["inconclusive"]["reason"]
    # the Jenkinsfile changed: the conversion is stale, the GHA tiers refuse to run it
    (example / "Jenkinsfile").write_text("pipeline { agent any; stages { stage('NEW') { steps { sh 'x' } } } }\n")
    res = execute.run_example(example, ["act"])
    assert not res["ok"] and "stale" in res["records"]["act"]["error"]
    assert execute.stale_reason(example, json.loads((example / "runs" / "jenkins-trace" / "result.json")
                                                    .read_text()), "jenkins")


def test_run_examples_exit_status(monkeypatch):
    from j2gha import stages
    results = {"ok": {"statuses": {"act": "ran"}, "verdicts": {"act": "equivalent"}},
               "differs": {"statuses": {"act": "ran"}, "verdicts": {"act": "differs"}},
               "refused": {"statuses": {"hosted": "refused"}, "verdicts": {}},
               "infra": {"statuses": {"act": "infra"}, "verdicts": {}}}
    monkeypatch.setattr(execute, "run_example", lambda d, **kw: results[d.name])
    monkeypatch.setattr(stages, "example_dir", lambda i: __import__("pathlib").Path(i))
    assert stages.run_examples(["ok", "differs"], ["act"]) == 0
    assert stages.run_examples(["ok", "differs"], ["act"], fail_on_differs=True) == 2
    assert stages.run_examples(["ok", "refused"], ["hosted"]) == 3
    assert stages.run_examples(["refused", "infra"], ["act"]) == 1


def test_cli_validates_tiers_and_stops_on_invalid_workflows(monkeypatch):
    from j2gha import cli, stages
    with pytest.raises(SystemExit):
        cli.main(["run", "001", "--tier", "jenkis,act"])
    calls = {}
    monkeypatch.setattr(stages, "analyze_examples", lambda ids, use_jenkins: None)
    monkeypatch.setattr(stages, "convert_examples", lambda ids: None)
    monkeypatch.setattr(stages, "validation_failures", lambda ids: ["002"])
    monkeypatch.setattr(stages, "run_examples", lambda ids, **kw: calls.setdefault("ids", ids) and 0)
    assert cli.main(["pipeline", "001", "002", "--tier", "hosted", "--yes"]) == 1
    assert calls["ids"] == ["001"]  # the invalid workflow is not executed (nor are hosted minutes spent on it)


# ------------------------------------------------------------------------------------------------ variants
def _wf():
    return {"name": "x", "on": {}, "env": {"TOKEN": "${{ secrets.JENKINS_GITHUB_TOKEN }}"}, "jobs": {"build": {
        "runs-on": "ubuntu-latest", "timeout-minutes": 60,
        "container": {"image": "node:20", "options": "-v /var/run/docker.sock:/var/run/docker.sock --privileged "
                                                     "--user 0", "credentials": {"username": "${{ secrets.R_USR }}"}},
        "steps": [
            {"name": "Checkout", "uses": "actions/checkout@v4", "with": {"persist-credentials": False},
             "_j2gha": {"kind": "checkout", "trace": False}},
            {"name": "Build: x", "run": "x", "env": {"P": "${{ secrets.DEPLOY_PSW }}", "U": "${{ secrets.DEPLOY_USR }}"},
             "_j2gha": {"kind": "sh", "stage": "Build", "trace": True}},
        ]}}}


@pytest.mark.parametrize("mode, target", [("full", "act"), ("full", "hosted"), ("trace", "act")])
def test_variants_never_reference_real_secrets(mode, target):
    variant, notes = make_variant(_wf(), mode, target, {"branch": "main"}, {"repository": "o/r", "sha": "abc"})
    text = json.dumps(variant)
    assert "secrets." not in text
    assert variant["env"]["TOKEN"] == "j2gha-fake-secret"  # the value the Jenkins reference's fake credential has
    if mode == "full":
        build = variant["jobs"]["build"]
        assert build["steps"][1]["env"] == {"P": "j2gha-fake-password", "U": "j2gha-user"}
        assert build["container"] == {"image": "node:20", "options": "--user 0"}
        assert "docker.sock" in notes["dropped_container_options"]["build"]
        checkout = build["steps"][0]["with"]
        # act: the source is fetched on the host and act's local checkout is used; remote tiers check it out
        assert ("repository" in checkout) == (target != "act")


def test_act_gets_no_operator_token(tmp_path, monkeypatch):
    import j2gha.runners.act as act
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw.get("env") or {}))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setattr(act.subprocess, "run", run)
    monkeypatch.setattr(act, "_git", lambda *a: None)
    monkeypatch.setenv("GITHUB_TOKEN", "operator-token")
    monkeypatch.setenv("GH_TOKEN", "operator-token")
    act.run_act(tmp_path / "out", "name: x\n", "main", "full")
    docker = next(c for c in calls if c[0][:2] == ["docker", "run"] and "push" in c[0])
    assert "GITHUB_TOKEN" not in " ".join(docker[0]) and "operator-token" not in json.dumps(docker[1])


def test_act_timeout_stops_the_act_container(tmp_path, monkeypatch):
    import j2gha.runners.act as act
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if "push" in cmd:
            raise subprocess.TimeoutExpired(cmd, 1)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setattr(act.subprocess, "run", run)
    monkeypatch.setattr(act, "_git", lambda *a: None)
    rec = act.run_act(tmp_path / "out", "name: x\n", "main", "trace")
    name = next(c for c in calls if "push" in c)[next(c for c in calls if "push" in c).index("--name") + 1]
    assert rec["result"] == "timeout"
    assert ["docker", "stop", "-t", "60", name] in calls and ["docker", "rm", "-f", name] in calls


def test_matrix_expansion_is_exact_or_bounded():
    def job(matrix):
        return {"strategy": {"matrix": matrix}, "timeout-minutes": 5, "runs-on": "ubuntu-latest"}
    assert matrix_expansion(job({"X": ["a", "b", "c"], "exclude": [{"X": "a"}, {"X": "a"}]})) == (2, True)
    assert matrix_expansion(job({"X": ["a", "b"], "include": [{"X": "c"}]})) == (3, True)  # new value: new job
    assert matrix_expansion(job({"X": ["a", "b"], "include": [{"X": "a", "extra": 1}]})) == (2, True)  # merged
    assert matrix_expansion(job({"X": ["a", "b"], "exclude": [{"X": "z"}]})) == (2, True)
    assert matrix_expansion(job({"X": "${{ fromJSON(needs.a.outputs.list) }}"})) == (256, False)
    est = estimate_minutes({"jobs": {"m": job({"X": ["a", "b", "c"], "exclude": [{"X": "a"}, {"X": "a"}]})}}, "full")
    assert est == {"typical": 10, "worst_case": 10, "unbounded": False}
    assert estimate_minutes({"jobs": {"m": job({"X": "${{ x }}"})}}, "full")["unbounded"]


# ------------------------------------------------------------------------------------------------ controller lock
def test_controller_lock_is_exclusive_between_processes(tmp_path, monkeypatch):
    import sys
    import textwrap
    from j2gha.jenkins import controller
    monkeypatch.setattr(controller, "STATE_DIR", tmp_path)
    with controller.exclusive("test"):
        with controller.exclusive("nested"):  # re-entrant in one process
            pass
        code = textwrap.dedent(f"""
            import pathlib, j2gha.jenkins.controller as c
            c.STATE_DIR = pathlib.Path({str(tmp_path)!r})
            try:
                with c.exclusive("other"):
                    print("acquired")
            except RuntimeError as e:
                print("refused:", e)
        """)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout
        assert out.startswith("refused:") and "pid" in out
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout
    assert out.startswith("acquired")


def test_upsert_reposts_when_the_controller_stores_a_different_script(monkeypatch):
    """Jenkins can store a corrupted copy of the posted script (an entity reference at a parser buffer boundary:
    example 121); the upsert reads the stored script back and posts again with the XML layout shifted."""
    from j2gha.jenkins import controller
    j = controller.Jenkins.__new__(controller.Jenkins)
    j.base = "http://jenkins.invalid"
    posted, approved = [], []
    stored = ["the script with a fragment repeated", "still different", "the script"]

    class Resp:
        status_code = 200
        text = ""

    class Session:
        def get(self, url, timeout=10):  # /api/json: the job exists
            return Resp()
    j.s = Session()
    monkeypatch.setattr(j, "post", lambda path, **kw: posted.append((path, kw["data"])) or Resp())
    monkeypatch.setattr(j, "job_script", lambda name: stored[len(posted) - 1])
    monkeypatch.setattr(j, "approve_script", lambda script: approved.append(script))
    j.upsert_pipeline_job("ex-1-full", "the script", description="d")
    assert [p[0] for p in posted] == ["/job/ex-1-full/config.xml"] * 3
    assert [p[1].count(b"<description>d" + b" " * n + b"</description>") for n, p in enumerate(posted)] == [1, 1, 1]
    assert approved == ["the script"]
    posted.clear()
    stored[:] = ["corrupt"] * 4
    with pytest.raises(RuntimeError, match="differs from the posted one"):
        j.upsert_pipeline_job("ex-1-full", "the script", description="d")
    assert len(posted) == 4 and not approved[1:]


# ------------------------------------------------------------------------------------- edited model (mutation tests)
def _edit_model(example):
    f = example / "gha" / "workflow.model.json"
    model = json.loads(f.read_text())
    model["jobs"]["build"]["steps"][0]["run"] = "sabotaged"
    f.write_text(json.dumps(model))


def test_an_edited_model_is_refused_by_default(example, monkeypatch):
    import j2gha.jenkins.run as jrun
    import j2gha.runners.act as act
    monkeypatch.setattr(jrun, "run_jenkins", _jenkins())
    monkeypatch.setattr(act, "run_act", _act())
    _edit_model(example)
    res = execute.run_example(example, ["jenkins", "act"])
    assert res["statuses"]["act"] == "infra" and "stale" in res["records"]["act"]["error"]


def test_an_edited_model_runs_on_request_and_is_never_counted_as_a_measurement(example, monkeypatch):
    import j2gha.jenkins.run as jrun
    import j2gha.runners.act as act
    monkeypatch.setattr(jrun, "run_jenkins", _jenkins())
    monkeypatch.setattr(act, "run_act", _act(traces=ev(("Build", "sh"), ("Build", "sh"))))  # the sabotage's effect
    _edit_model(example)
    res = execute.run_example(example, ["jenkins", "act"], allow_edited_model=True)
    assert res["verdicts"] == {"act": "differs"}  # the comparator judges the edited conversion
    rec = res["records"]["act"]
    assert rec["provenance"]["edited_model"] is True
    assert rec["provenance"]["model_sha256"] == sha256_json(json.loads((example / "gha/workflow.model.json").read_text()))
    assert "mutation test" in execute.stale_reason(example, rec, "act")  # shown as stale, so never counted
    clean = execute.run_example(example, ["jenkins"], allow_edited_model=True)["records"]["jenkins"]
    assert execute.stale_reason(example, clean, "jenkins") is None  # the Jenkins reference is unaffected


# --------------------------------------------------------------------------- full-mode corpus findings (H7, H10)
def test_failed_step_lookup_ignores_the_whitespace_github_trims():
    """H7: GitHub trims step names, so a model name with surrounding whitespace must still find its stage."""
    model = {"jobs": {"build": {"steps": [{"name": " Publish:  upload ", "_j2gha": {"stage": "Publish"}}]}}}
    assert execute.step_stages(model) == {"Publish: upload": {"Publish"}}
    rec = {"result": "failure", "failed_steps": ["Publish: upload"], "jobs": [{"name": "build"}]}
    assert execute.compare_outcome(_ref("FAILURE", "Publish"), rec, model)["verdict"] == "equivalent"


@pytest.mark.parametrize("target", ["act", "selfhosted", "hosted"])
def test_full_variants_pin_git_commit_to_the_cited_commit(target):
    """H10: the checkout is pinned to the cited upstream commit (act's workspace holds it too), so GIT_COMMIT must
    name that commit, as Jenkins' does, not the harness run branch's `github.sha`. Trace mode is left alone."""
    wf = _wf()
    wf["env"]["GIT_COMMIT"] = "${{ github.sha }}"
    source = {"repository": "o/r", "sha": "abc123"}
    full, _ = make_variant(wf, "full", target, {"branch": "main"}, source, runner_label="x")
    assert full["env"]["GIT_COMMIT"] == "abc123"
    trace, _ = make_variant(wf, "trace", target, {"branch": "main"}, source, runner_label="x")
    assert trace["env"]["GIT_COMMIT"] == "${{ github.sha }}"
    unpinned, _ = make_variant(wf, "full", target, {"branch": "main"}, {"repository": "o/r"}, runner_label="x")
    assert unpinned["env"]["GIT_COMMIT"] == "${{ github.sha }}"
    no_checkout, _ = make_variant(_wf(), "full", target, {"branch": "main"}, source, runner_label="x")
    assert "GIT_COMMIT" not in no_checkout["env"]  # a workflow without GIT_COMMIT (no checkout) gets none
