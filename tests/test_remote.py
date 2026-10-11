"""Remote-run lifecycle: abnormal exits cancel and record, failure evidence. Every GitHub/Docker call is faked."""

import json
import re
from types import SimpleNamespace
from unittest import mock

import pytest
import requests

from j2gha import github
from j2gha.gha import budget, remote
from j2gha.github import GitHub, GitHubError

REPO = "me/harness"
SHA = "c0ffee" + "0" * 34
RUN = {"id": 1, "head_sha": SHA, "html_url": "https://github.com/me/harness/actions/runs/1", "status": "queued"}


def step(n, name, conclusion):
    return {"name": name, "number": n, "conclusion": conclusion, "status": "completed",
            "started_at": "2026-10-04T10:00:00Z", "completed_at": "2026-10-04T10:00:05Z"}


JOBS = [  # listed out of execution order on purpose
    {"id": 12, "name": "deploy", "status": "completed", "conclusion": "failure", "labels": ["ubuntu-latest"],
     "started_at": "2026-10-04T10:05:00Z", "completed_at": "2026-10-04T10:06:30Z",
     "steps": [step(1, "Set up job", "failure"), step(3, "Post results", "failure"),
               step(2, "Deploy: ./deploy.sh", "failure"), step(4, "Complete job", "success")]},
    {"id": 11, "name": "build", "status": "completed", "conclusion": "failure", "labels": ["ubuntu-latest"],
     "started_at": "2026-10-04T10:00:00Z", "completed_at": "2026-10-04T10:00:40Z",
     "steps": [step(1, "Set up job", "success"), step(2, "Checkout", "success"), step(3, "Build: make", "failure"),
               step(4, "Post Checkout", "failure"), step(5, "Complete job", "success")]},
]


class FakeGH:
    """Routes {(METHOD, path regex): value | exception | callable(params)}; every call is recorded."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, path, params=None, raw=False, **k):
        self.calls.append((method, path))
        for (m, pattern), v in self.routes.items():
            if m == method and re.fullmatch(pattern, path):
                if isinstance(v, BaseException):
                    raise v
                return v(params or {}) if callable(v) else v
        raise AssertionError(f"unexpected {method} {path}")

    def get(self, path, **k):
        return self.request("GET", path, **k)

    def did(self, method, pattern):
        return [i for i, c in enumerate(self.calls) if c[0] == method and re.fullmatch(pattern, c[1])]


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def blocked(*a, **k):
        raise AssertionError(f"blocked external call: {a[:2]}")

    monkeypatch.setattr(requests.Session, "request", blocked)
    monkeypatch.setattr(remote.subprocess, "run", blocked)
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("J2GHA_REPO", REPO)
    monkeypatch.setattr(budget, "LEDGER", tmp_path / "usage-ledger.jsonl")
    monkeypatch.setattr(budget, "ACTIVE_DIR", tmp_path / "remote-runs")
    monkeypatch.setattr(remote, "make_variant", lambda *a, **k: ({"jobs": {}}, {"jobs": 2}))
    monkeypatch.setattr(remote, "to_yaml", lambda *a, **k: "name: x\n")
    monkeypatch.setattr(remote, "estimate_minutes", lambda *a, **k: {"typical": 2, "worst_case": 20})
    monkeypatch.setattr(remote, "RunnerPool", mock.MagicMock(name="RunnerPool"))
    monkeypatch.setattr(remote.budget, "guard", lambda est, **k: {
        "allowed": True, "reasons": [], "estimate": est, "account": {"repo": REPO, "owner": "me"},
        "usage": {"used": 0}, "available_after_reserve": 1000, "pending_minutes": 0, "free_minutes": False,
        "usage_complete": True})
    monkeypatch.setattr(remote, "time", SimpleNamespace(time=lambda: 0.0, sleep=lambda s: None))


def make_gh(monkeypatch, **override):
    routes = {
        ("POST", f"/repos/{REPO}/git/blobs"): {"sha": "b1"},
        ("POST", f"/repos/{REPO}/git/trees"): {"sha": "t1"},
        ("POST", f"/repos/{REPO}/git/commits"): {"sha": SHA},
        ("POST", f"/repos/{REPO}/git/refs"): {},
        ("DELETE", f"/repos/{REPO}/git/refs/heads/j2gha/run/.+"): None,
        ("GET", f"/repos/{REPO}/actions/runs"): {"workflow_runs": [RUN]},
        ("GET", f"/repos/{REPO}/actions/runs/1"): {**RUN, "status": "in_progress"},
        ("POST", f"/repos/{REPO}/actions/runs/1/cancel"): {},
        ("GET", f"/repos/{REPO}/actions/runs/1/jobs"): {"jobs": JOBS},
        ("GET", f"/repos/{REPO}/actions/runs/1/logs"): GitHubError(404, "Not Found", "logs"),
        ("GET", f"/repos/{REPO}/actions/runs/1/artifacts"): {"artifacts": []},
        ("GET", rf"/repos/{REPO}/actions/jobs/\d+/logs"): SimpleNamespace(
            text='2026-10-04T10:00:01.0000000Z J2GHA-TRACE {"stage":"Build","step":"sh"}'),
    }
    routes.update({tuple(k.split(" ", 1)): v for k, v in override.items()})
    gh = FakeGH(routes)
    monkeypatch.setattr(remote, "GitHub", lambda *a, **k: gh)
    return gh


def go(tmp_path, tier="hosted", mode="full"):
    d = tmp_path / "903"
    d.mkdir(exist_ok=True)
    return remote.run_remote(d, {}, mode, tier, {"branch": "main"}, None, yes=True, max_minutes=10)


def ledger():
    return budget.read_ledger()


def states():
    return [json.loads(p.read_text()) for p in sorted(budget.ACTIVE_DIR.glob("*.json"))]


@pytest.mark.parametrize("tier", ["hosted", "selfhosted"])
def test_polling_error_cancels_the_run_and_keeps_the_reservation(monkeypatch, tmp_path, tier):
    gh = make_gh(monkeypatch, **{f"GET /repos/{REPO}/actions/runs/1": GitHubError(502, "Bad Gateway", "run")})
    with pytest.raises(GitHubError):
        go(tmp_path, tier)
    cancel, delete = gh.did("POST", r".*/actions/runs/1/cancel"), gh.did("DELETE", r".*/git/refs/heads/.*")
    assert len(cancel) == 1 and len(delete) == 1 and cancel[0] < delete[0]
    [s] = states()
    assert (s["run_id"], s["sha"], s["repo"], s["tier"], s["state"]) == (1, SHA, REPO, tier, "cancel-requested")
    assert "502" in s["error"]
    if tier == "hosted":
        [e] = ledger()
        assert (e["status"], e["run_id"], e["reserved_minutes"], e["sha"]) == ("pending", 1, 20, SHA)
        assert e["state"] == "cancel-requested" and e["branch"] == s["branch"]
    else:
        assert ledger() == [] and remote.RunnerPool.return_value.stop.called


def test_keyboard_interrupt_cancels_the_run(monkeypatch, tmp_path):
    gh = make_gh(monkeypatch)

    def ctrl_c(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(remote, "time", SimpleNamespace(time=lambda: 0.0, sleep=ctrl_c))
    with pytest.raises(KeyboardInterrupt):
        go(tmp_path)
    assert gh.did("POST", r".*/actions/runs/1/cancel") and gh.did("DELETE", r".*/git/refs/heads/.*")
    [e] = ledger()
    assert e["status"] == "pending" and e["run_id"] == 1 and e["error"] == "KeyboardInterrupt: "
    assert states()[0]["state"] == "cancel-requested"


@pytest.mark.parametrize("found_later", [True, False])
def test_run_not_found_gets_a_best_effort_lookup(monkeypatch, tmp_path, found_later):
    gh = make_gh(monkeypatch)
    lookups = []

    def find_run(gh_, repo, branch, sha, timeout=180):
        lookups.append(timeout)
        if len(lookups) == 1 or not found_later:
            raise RuntimeError(f"no workflow run appeared for {branch} within {timeout}s")
        return RUN

    monkeypatch.setattr(remote, "find_run", find_run)
    with pytest.raises(RuntimeError, match="no workflow run appeared"):
        go(tmp_path)
    assert lookups[0] == 180 and len(lookups) == 2 and lookups[1] <= 30
    assert bool(gh.did("POST", r".*/actions/runs/1/cancel")) is found_later
    assert gh.did("DELETE", r".*/git/refs/heads/.*")
    [e], [s] = ledger(), states()
    assert e["status"] == "pending" and e["run_id"] == (1 if found_later else None)
    assert s["state"] == ("cancel-requested" if found_later else "unknown")


def test_branch_never_created_releases_the_reservation(monkeypatch, tmp_path):
    gh = make_gh(monkeypatch, **{f"POST /repos/{REPO}/git/refs": GitHubError(422, "Reference update failed", "r"),
                                 f"GET /repos/{REPO}/git/ref/heads/.+": GitHubError(404, "Not Found", "ref")})
    with pytest.raises(GitHubError):
        go(tmp_path)
    assert not gh.did("POST", r".*/cancel") and not gh.did("GET", r".*/actions/runs")
    [e] = ledger()
    assert e["status"] == "released" and states() == []


@pytest.mark.parametrize("completes", [True, False])
def test_timeout_records_the_cancelled_state(monkeypatch, tmp_path, completes):
    clock = iter(range(0, 10**6, 100))  # 100 s per clock read: find_run succeeds, polling hits its limit
    monkeypatch.setattr(remote, "time", SimpleNamespace(time=lambda: float(next(clock)), sleep=lambda s: None))
    cancelled = []
    gh = make_gh(monkeypatch, **{
        f"POST /repos/{REPO}/actions/runs/1/cancel": lambda p: cancelled.append(1) or {},
        f"GET /repos/{REPO}/actions/runs/1": lambda p: (
            {**RUN, "status": "completed", "conclusion": "cancelled"} if cancelled and completes
            else {**RUN, "status": "in_progress", "conclusion": None})})
    rec = go(tmp_path)
    assert len(gh.did("POST", r".*/actions/runs/1/cancel")) == 1
    assert rec["result"] == "cancelled" and rec["error"].startswith("timed out")
    [e] = ledger()
    if completes:
        assert rec["billable_minutes"] == 3 and rec["error"] == "timed out; run cancelled"
        assert e["status"] == "reconciled" and e["billable_minutes"] == 3 and states() == []
    else:
        assert rec["billable_minutes"] is None and "reservation left pending" in rec["error"]
        assert e["status"] == "pending" and e["run_id"] == 1 and states()[0]["state"] == "cancel-requested"


def test_failed_steps_and_job_steps_are_recorded(monkeypatch, tmp_path):
    gh = make_gh(monkeypatch, **{f"GET /repos/{REPO}/actions/runs/1": {**RUN, "status": "completed",
                                                                       "conclusion": "failure"}})
    rec = go(tmp_path)
    assert rec["failed_steps"] == ["Build: make", "Deploy: ./deploy.sh", "Post results"]
    assert rec["result"] == "failure" and rec["run_url"] == RUN["html_url"] and rec["billable_minutes"] == 3
    assert rec["variant_notes"] == {"jobs": 2} and rec["traces"] == [{"stage": "Build", "step": "sh"}] * 2
    build = next(j for j in rec["jobs"] if j["name"] == "build")
    assert build["steps"][2] == {"name": "Build: make", "number": 3, "conclusion": "failure",
                                 "started_at": "2026-10-04T10:00:00Z", "completed_at": "2026-10-04T10:00:05Z"}
    assert not gh.did("POST", r".*/cancel") and gh.did("DELETE", r".*/git/refs/heads/.*")
    [e] = ledger()
    assert e["status"] == "reconciled" and e["billable_minutes"] == 3 and e["result"] == "failure"
    assert states() == []  # clean finish leaves no in-flight state


def test_github_request_retries_connection_errors(monkeypatch):
    monkeypatch.setattr(github.time, "sleep", lambda s: None)
    ok = SimpleNamespace(status_code=200, content=b'{"ok": 1}', json=lambda: {"ok": 1}, headers={})
    gh = GitHub(token="test-token", cache_ttl=0)
    gh.session.request = mock.Mock(side_effect=[requests.ConnectionError("reset"), requests.Timeout("slow"), ok])
    assert gh.get("/user", use_cache=False) == {"ok": 1} and gh.session.request.call_count == 3

    gh.session.request = mock.Mock(side_effect=requests.ConnectionError("down"))
    with pytest.raises(requests.ConnectionError):
        gh.get("/user", use_cache=False)
    assert gh.session.request.call_count == 4


def test_environments_are_prepared_and_checked_only_on_request(monkeypatch, tmp_path):
    from j2gha.gha import environments as envs
    model = {"jobs": {"deploy": {"environment": "Deploy", "steps": [
        {"name": "Deploy: input approval", "run": "true", "_j2gha": {"kind": "input", "stage": "Deploy"}}]}}}
    seen = {}
    monkeypatch.setattr(remote, "make_variant", lambda *a, **k: seen.update(k) or ({"jobs": {}}, {"jobs": 1}))
    prepared = []
    monkeypatch.setattr(envs, "ensure", lambda gh, repo, canaries: prepared.append(canaries))
    jobs = [{**JOBS[1], "steps": [step(1, envs.CHECK_STEP, "success"), *JOBS[1]["steps"]]}]
    make_gh(monkeypatch, **{f"GET /repos/{REPO}/actions/runs/1": {**RUN, "status": "completed", "conclusion": "success"},
                            f"GET /repos/{REPO}/actions/runs/1/jobs": {"jobs": jobs},
                            f"GET /repos/{REPO}/deployments": [{"environment": "j2gha-Deploy"}]})
    d = tmp_path / "903"
    d.mkdir()
    rec = remote.run_remote(d, model, "trace", "selfhosted", {"branch": "main"}, None, environments=True)
    [canaries] = prepared
    assert list(canaries) == ["j2gha-Deploy"] and seen["environments"] == {"j2gha-Deploy": envs.digest(canaries["j2gha-Deploy"])}
    assert rec["environments"] == {"secret_checks": [{"job": "build", "conclusion": "success"}], "entered": ["j2gha-Deploy"]}
    prepared.clear()
    rec = remote.run_remote(d, model, "trace", "selfhosted", {"branch": "main"}, None)
    assert prepared == [] and seen["environments"] is None and "environments" not in rec


def test_the_workspace_handoff_cost_is_measured_from_the_runs_steps_and_artifacts():
    """Third review of Phase 4: measure the whole-workspace transfer before optimising it."""
    def step(name, start, end):
        return {"name": name, "started_at": f"2026-10-08T10:00:{start:02d}Z", "completed_at": f"2026-10-08T10:00:{end:02d}Z"}
    jobs = [{"name": "build", "started_at": "2026-10-08T10:00:00Z", "completed_at": "2026-10-08T10:00:40Z",
             "steps": [step("Checkout", 0, 5), step("Build: make", 5, 30), step("Hand on the pipeline workspace (archive)", 30, 33),
                       step("Hand on the pipeline workspace (upload)", 33, 36)]},
            {"name": "after", "started_at": "2026-10-08T10:00:00Z", "completed_at": "2026-10-08T10:00:20Z",
             "steps": [step("Restore pipeline workspace (build)", 0, 4), step("Restore pipeline workspace (merge)", 4, 6),
                       step("After: ls", 6, 7)]}]
    artifacts = [{"name": "j2gha-ws-build", "size_in_bytes": 2_000_000}, {"name": "artifacts-3", "size_in_bytes": 10}]
    assert remote.handoff_cost(jobs, artifacts) == {"steps": 4, "seconds": 12, "job_seconds": 60, "archives": 1,
                                                    "bytes": 2_000_000}
    # end to end: the hand-off time on the critical path (`after` waits for `build`), against the run's elapsed time
    workflow = {"jobs": {"build": {"name": "build"}, "after": {"name": "after", "needs": "build"}}}
    jobs[1].update(started_at="2026-10-08T10:00:40Z", completed_at="2026-10-08T10:00:59Z")
    run = {"run_started_at": "2026-10-08T09:59:58Z", "updated_at": "2026-10-08T10:01:00Z"}
    cost = remote.handoff_cost(jobs, artifacts, workflow, run)
    assert cost["critical_path_seconds"] == 12 and cost["run_seconds"] == 62
    assert remote.handoff_cost([{"name": "x", "steps": [step("Build: make", 0, 1)]}], []) is None
