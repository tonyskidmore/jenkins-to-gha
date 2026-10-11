"""Environments in remote execution variants (Phase 4, P4.2: `run --environments`)."""

import json
import os
import subprocess

import pytest

from j2gha.gha import environments as envs
from j2gha.runners import execute
from j2gha.runners.variants import make_variant

MODEL = {"on": {"workflow_dispatch": {}}, "env": {"TOKEN": "${{ secrets.API_TOKEN }}"}, "jobs": {
    "build": {"runs-on": "ubuntu-latest", "steps": [
        {"name": "Build: make", "run": "make", "_j2gha": {"kind": "sh", "stage": "Build", "trace": True}}]},
    "deploy": {"runs-on": "ubuntu-latest", "environment": "Deploy", "needs": "build", "steps": [
        {"name": "Deploy: input approval", "run": "echo ok", "_j2gha": {"kind": "input", "stage": "Deploy", "trace": True}},
        {"name": "Deploy: ./deploy.sh", "run": "./deploy.sh", "env": {"K": "${{ secrets.DEPLOY_KEY }}"},
         "_j2gha": {"kind": "sh", "stage": "Deploy", "trace": True}}]},
    "fan-input": {"runs-on": "ubuntu-latest", "environment": {"name": "Fan out", "url": "https://x"}, "steps": [
        {"name": "Fan out: input approval", "run": "echo ok", "_j2gha": {"kind": "input", "stage": "Fan out"}}]},
}}
DIGESTS = {"j2gha-Deploy": envs.digest("canary-1"), "j2gha-Fan-out": envs.digest("canary-2")}


def test_environments_map_to_the_stages_whose_input_they_stand_for():
    assert envs.environment_stages(MODEL) == {"j2gha-Deploy": {"Deploy"}, "j2gha-Fan-out": {"Fan out"}}
    assert set(envs.new_canaries(MODEL)) == {"j2gha-Deploy", "j2gha-Fan-out"}
    assert len(set(envs.new_canaries(MODEL).values())) == 2


@pytest.mark.parametrize("mode", ["trace", "full"])
def test_remote_variants_keep_environments_under_harness_names(mode):
    v, notes = make_variant(MODEL, mode, "selfhosted", {"branch": "main"}, environments=DIGESTS)
    deploy = v["jobs"]["deploy"]
    assert deploy["environment"] == "j2gha-Deploy" and v["jobs"]["fan-input"]["environment"] == "j2gha-Fan-out"
    check = deploy["steps"][0]
    assert check["name"] == envs.CHECK_STEP and DIGESTS["j2gha-Deploy"] in check["run"]
    assert "environment" not in v["jobs"]["build"] and notes["environments"] == sorted(DIGESTS)
    # the canary is the only real secret the variant reads; every pipeline secret is still faked
    text = json.dumps(v)
    assert set(envs.re.findall(r"secrets\.(\w+)", text)) == {envs.CANARY}


@pytest.mark.parametrize("target, digests", [("act", DIGESTS), ("selfhosted", None), ("hosted", {})])
def test_environments_are_removed_otherwise(target, digests):
    v, _ = make_variant(MODEL, "trace", target, {"branch": "main"}, environments=digests)
    assert not any("environment" in j for j in v["jobs"].values())
    assert "secrets." not in json.dumps(v)


@pytest.mark.parametrize("value, ok", [("canary-1", True), ("other", False), ("", False)])
def test_the_canary_check_accepts_only_the_environments_own_secret(value, ok):
    v, _ = make_variant(MODEL, "full", "selfhosted", {"branch": "main"}, environments=DIGESTS)
    script = v["jobs"]["deploy"]["steps"][0]["run"]
    p = subprocess.run(["bash", "-e", "-c", script], env={**os.environ, envs.CANARY: value}, capture_output=True,
                       text=True)
    assert (p.returncode == 0) == ok, p.stdout


def ref(approved):
    return {"approved_inputs": approved} if approved is not None else {}


def rec(entered, checks=("deploy", "success")):
    return {"environments": {"entered": entered, "secret_checks": [{"job": checks[0], "conclusion": checks[1]}]}}


@pytest.mark.parametrize("approved, entered, checks, status", [
    (["Deploy"], ["j2gha-Deploy"], ("deploy", "success"), "same"),
    ([], [], ("deploy", "success"), "same"),  # Jenkins skipped the gated stage, the converted run entered nothing
    ([], ["j2gha-Deploy"], ("deploy", "success"), "differs"),  # approval asked for a stage Jenkins skipped
    (["Deploy"], [], ("deploy", "success"), "differs"),  # the converted run skipped the approval
    (["Deploy"], ["j2gha-Deploy"], ("deploy", "failure"), "differs"),  # the environment's secret was not visible
    (["Unrelated stage"], [], ("deploy", "success"), "same"),  # an input step with no environment in the model
    (None, ["j2gha-Deploy"], ("deploy", "success"), "inconclusive"),  # reference recorded before P4.2
])
def test_environment_comparison(approved, entered, checks, status):
    assert envs.compare(ref(approved), rec(entered, checks), MODEL)["status"] == status


def test_trace_mode_references_reach_inputs_through_their_trace_events():
    jenkins = {"mode": "trace", "traces": [{"stage": "Deploy", "step": "input"}]}  # no approved_inputs: stubbed
    assert envs.compare(jenkins, rec(["j2gha-Deploy"]), MODEL)["status"] == "same"
    assert envs.compare({"mode": "trace", "traces": []}, rec(["j2gha-Deploy"]), MODEL)["status"] == "differs"


def test_environment_differences_decide_the_verdict():
    base = {"jenkinsfile_sha256": "h", "scenario": {"branch": "main"}, "mode": "trace"}
    jenkins = {"result": "SUCCESS", "traces": [{"stage": "Build", "step": "sh"}], "approved_inputs": [],
               "provenance": {"jenkinsfile_sha256": "h", "scenario": {"branch": "main"},
                              "localizer_version": execute.LOCALIZER_VERSION}}
    gha = {"result": "success", "traces": [{"stage": "Build", "step": "sh"}]}
    assert execute._compare(jenkins, gha, base, MODEL)["verdict"] == "equivalent"
    c = execute._compare(jenkins, {**gha, **rec(["j2gha-Deploy"])}, base, MODEL)
    assert c["verdict"] == "differs" and c["environments"]["expected"] == []
    old = {k: v for k, v in jenkins.items() if k != "approved_inputs"}
    c = execute._compare(old, {**gha, **rec([])}, base, MODEL)
    assert c["verdict"] == "inconclusive" and "environments" in c["inconclusive"]["reason"]


class FakeGH:
    def __init__(self, envs_listing=None, deployments=None):
        self.calls, self.envs_listing, self.deployments = [], envs_listing or [], deployments or []

    def request(self, method, path, **k):
        self.calls.append((method, path))

    def get(self, path, **k):
        if path.endswith("/deployments"):
            assert k["params"]["sha"] == "abc"
            return self.deployments
        return {"environments": [{"name": n} for n in self.envs_listing]}


def test_harness_environments_are_created_listed_and_cleaned(monkeypatch):
    calls = []
    monkeypatch.setattr(envs.shutil, "which", lambda n: "/usr/bin/gh")
    monkeypatch.setattr(envs.subprocess, "run", lambda cmd, **k: calls.append(cmd))
    gh = FakeGH(envs_listing=["Deploy", "j2gha-Deploy", "production"])
    envs.ensure(gh, "me/harness", {"j2gha-Deploy": "v1"})
    assert gh.calls == [("PUT", "/repos/me/harness/environments/j2gha-Deploy")]
    assert calls == [["gh", "secret", "set", envs.CANARY, "--env", "j2gha-Deploy", "--repo", "me/harness",
                      "--body", "v1"]]
    assert envs.list_harness(gh, "me/harness") == ["j2gha-Deploy"]
    assert envs.delete_harness(gh, "me/harness") == ["j2gha-Deploy"]  # the repository's own environments stay
    assert gh.calls[-1] == ("DELETE", "/repos/me/harness/environments/j2gha-Deploy")


def test_entered_environments_come_from_the_runs_deployments():
    gh = FakeGH(deployments=[{"environment": "j2gha-Deploy"}, {"environment": "j2gha-Deploy"}, {"environment": None}])
    assert envs.entered(gh, "me/harness", "abc") == ["j2gha-Deploy"]
    jobs = [{"name": "deploy", "steps": [{"name": envs.CHECK_STEP, "conclusion": "success"}, {"name": "x"}]},
            {"name": "build", "steps": [{"name": "Build: make", "conclusion": "success"}]}]
    assert envs.secret_checks(jobs) == [{"job": "deploy", "conclusion": "success"}]
