"""Run a converted workflow on real GitHub Actions in this repository.

The workflow variant is committed to an *orphan* branch `j2gha/run/<id>-<mode>-<ts>` through the Git Data API
(no local git state is touched); the branch push triggers it (`on.push.branches: [that branch]`). After the run the
jobs, logs and billable minutes are collected and the branch is deleted (the run history remains).

Hosted runs reserve their worst-case minutes in the budget ledger before the branch is created. The in-flight state
(run id, branch, sha) is kept in .j2gha/remote-runs/ until the run finishes normally; on any abnormal exit
(API error, Ctrl-C) a dispatched, unfinished run is cancelled and its reservation is left pending for reconciliation.

tiers:
  hosted      GitHub-hosted runners - costs minutes on a private repo; guarded by gha.budget.guard()
  selfhosted  ephemeral just-in-time (JIT) self-hosted runners started locally in Docker
              (config.RUNNER_IMAGE: ghcr.io/actions/actions-runner plus the Jenkins image's toolchain,
              docker/runner/Dockerfile) - real GitHub orchestration, zero hosted minutes
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import ROOT, RUNNER_IMAGE
from ..convert.generator import to_yaml
from ..github import GitHub, GitHubError
from ..runners.variants import estimate_minutes, make_variant
from ..trace import parse_traces
from . import budget
from . import environments as env_check

WORKFLOW_PATH = ".github/workflows/j2gha-run.yml"
# Every remote run commits the same file, and GitHub lists all of its runs under the `name:` it saw first (one
# example's), so the committed copy gets this fixed name; the run title (the commit message) names the example.
REMOTE_WORKFLOW_NAME = "j2gha harness run"


def log(msg: str) -> None:
    print(f"[gha] {msg}", file=sys.stderr, flush=True)


def harness_repo() -> str:
    import os
    if os.environ.get("J2GHA_REPO"):
        return os.environ["J2GHA_REPO"]
    url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], capture_output=True,
                         text=True).stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
    if not m:
        raise RuntimeError("cannot determine the GitHub repository for remote runs (set J2GHA_REPO=owner/repo)")
    return m.group(1)


def orphan_commit(gh: GitHub, repo: str, files: dict[str, str], message: str) -> str:
    """Parentless commit of `files`; nothing is triggered until a branch points at it."""
    tree = []
    for path, content in files.items():
        blob = gh.request("POST", f"/repos/{repo}/git/blobs", json_body={"content": content, "encoding": "utf-8"})
        tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    t = gh.request("POST", f"/repos/{repo}/git/trees", json_body={"tree": tree})
    c = gh.request("POST", f"/repos/{repo}/git/commits", json_body={"message": message, "tree": t["sha"], "parents": []})
    return c["sha"]


def create_branch(gh: GitHub, repo: str, branch: str, sha: str) -> None:
    gh.request("POST", f"/repos/{repo}/git/refs", json_body={"ref": f"refs/heads/{branch}", "sha": sha})


def branch_exists(gh: GitHub, repo: str, branch: str) -> bool | None:
    try:
        gh.get(f"/repos/{repo}/git/ref/heads/{branch}", use_cache=False)
        return True
    except GitHubError as e:
        return False if e.status == 404 else None


def delete_branch(gh: GitHub, repo: str, branch: str) -> None:
    try:
        gh.request("DELETE", f"/repos/{repo}/git/refs/heads/{branch}")
    except GitHubError as e:
        log(f"could not delete {branch}: {e.status}")


def find_run(gh: GitHub, repo: str, branch: str, sha: str, timeout: int = 180) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = gh.get(f"/repos/{repo}/actions/runs", params={"branch": branch, "head_sha": sha, "per_page": 10},
                      use_cache=False)
        for r in runs.get("workflow_runs", []):
            if r.get("head_sha") == sha:
                return r
        time.sleep(5)
    raise RuntimeError(f"no workflow run appeared for {branch} within {timeout}s")


def cancel_run(gh: GitHub, repo: str, run_id: int) -> bool:
    """Request cancellation; False when the run had already completed (409)."""
    try:
        gh.request("POST", f"/repos/{repo}/actions/runs/{run_id}/cancel")
        return True
    except GitHubError as e:
        if e.status == 409:
            return False
        raise


def await_completion(gh: GitHub, repo: str, run_id: int, timeout: int = 120) -> dict[str, Any]:
    deadline = time.time() + timeout
    while True:
        run = gh.get(f"/repos/{repo}/actions/runs/{run_id}", use_cache=False)
        if run.get("status") == "completed" or time.time() >= deadline:
            return run
        time.sleep(5)


def list_jobs(gh: GitHub, repo: str, run_id: int) -> list[dict[str, Any]]:
    jobs, page = [], 1
    while True:
        data = gh.get(f"/repos/{repo}/actions/runs/{run_id}/jobs", params={"filter": "latest", "per_page": 100,
                                                                         "page": page}, use_cache=False)
        jobs += data.get("jobs", [])
        if len(data.get("jobs", [])) < 100:
            break
        page += 1
    return jobs


def job_log(gh: GitHub, repo: str, job_id: int) -> str:
    try:
        r = gh.request("GET", f"/repos/{repo}/actions/jobs/{job_id}/logs", raw=True, use_cache=False)
        return r.text
    except GitHubError:
        return ""


def run_logs_zip(gh: GitHub, repo: str, run_id: int) -> dict[str, str]:
    try:
        r = gh.request("GET", f"/repos/{repo}/actions/runs/{run_id}/logs", raw=True, use_cache=False)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        return {n: z.read(n).decode("utf-8", errors="replace") for n in z.namelist()}
    except (GitHubError, zipfile.BadZipFile):
        return {}


def list_artifacts(gh: GitHub, repo: str, run_id: int) -> tuple[list[dict[str, Any]], str | None]:
    """Every artifact of a run (all pages), and a problem when the listing was cut short."""
    listed: list[dict[str, Any]] = []
    data: dict[str, Any] = {}
    for page in range(1, 101):  # 100 per page at most; the list is complete when total_count is reached
        data = gh.get(f"/repos/{repo}/actions/runs/{run_id}/artifacts", params={"per_page": 100, "page": page},
                      use_cache=False) or {}
        batch = data.get("artifacts") or []
        listed += batch
        if not batch or len(listed) >= int(data.get("total_count") or 0):
            break
    short = len(listed) < int(data.get("total_count") or 0)
    return listed, f"run artifacts: listed {len(listed)} of {data.get('total_count')}" if short else None


def run_outputs(gh: GitHub, repo: str, run_id: int, model: dict[str, Any],
                listing: tuple[list[dict[str, Any]], str | None] | None = None,
                injected: dict[str, str] | None = None) -> dict[str, Any]:
    """Archived files and test results of a run (full mode), from the artifacts its upload steps made."""
    from ..outputs import DOWNLOAD_CAP, artifact_kind, gha_outputs, upload_kinds, wanted
    kinds = upload_kinds(model)
    blobs: dict[str, bytes | None] = {}
    skipped: list[str] = []
    room = DOWNLOAD_CAP
    try:
        listed, short = listing or list_artifacts(gh, repo, run_id)
    except GitHubError as e:
        return {"archived": [], "tests": None, "problems": [f"run artifacts unreadable: {e}"]}
    if short:
        skipped.append(short)
    for a in listed:
        if not wanted(artifact_kind(a["name"], kinds)):
            continue
        if a.get("expired") or a.get("size_in_bytes", 0) > room:
            skipped.append(f"{a['name']}: {'expired' if a.get('expired') else 'over the download cap'}")
            continue
        try:
            blobs[a["name"]] = gh.request("GET", a["archive_download_url"], raw=True, use_cache=False).content
            room -= len(blobs[a["name"]] or b"")
        except GitHubError as e:
            skipped.append(f"{a['name']}: {e}")
    return gha_outputs(blobs, model, skipped, injected)


_STEP_KEYS = ("name", "number", "conclusion", "started_at", "completed_at")


def _seconds(x: dict[str, Any]) -> float:
    try:
        return (datetime.fromisoformat(str(x["completed_at"]).replace("Z", "+00:00"))
                - datetime.fromisoformat(str(x["started_at"]).replace("Z", "+00:00"))).total_seconds()
    except (KeyError, TypeError, ValueError):
        return 0.0


def handoff_cost(jobs: list[dict[str, Any]], artifacts: list[dict[str, Any]], workflow: dict[str, Any] | None = None,
                 run: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """What the workspace hand-off cost a run: its archives' size; its steps' time summed over all jobs (concurrent
    jobs overlap, so this is not elapsed time) against all jobs' time; and, given the workflow (for `needs`) and the
    run, the hand-off time on the critical path against the run's elapsed time - an estimate of what the hand-off adds
    end to end (scheduling gaps between jobs are not counted)."""
    from ..convert.workspace import STEP_NAMES

    def handoff_seconds(job: dict[str, Any]) -> float:
        return sum(_seconds(s) for s in job.get("steps") or [] if str(s.get("name") or "").startswith(STEP_NAMES))

    steps = [s for j in jobs for s in j.get("steps") or [] if str(s.get("name") or "").startswith(STEP_NAMES)]
    archives = [a for a in artifacts if str(a.get("name", "")).startswith("j2gha-ws-")]
    if not steps and not archives:
        return None
    out: dict[str, Any] = {"steps": len(steps), "seconds": round(sum(handoff_seconds(j) for j in jobs)),
                           "job_seconds": round(sum(_seconds(j) for j in jobs)), "archives": len(archives),
                           "bytes": sum(int(a.get("size_in_bytes") or 0) for a in archives)}
    if run and run.get("run_started_at") and run.get("updated_at"):
        out["run_seconds"] = round(_seconds({"started_at": run["run_started_at"], "completed_at": run["updated_at"]}))
    done = [j for j in jobs if j.get("completed_at")]
    if workflow and done:
        # job names on GitHub: the workflow's `name` (matrix cells add " (values)")
        name_of = {jid: str(j.get("name") or jid) for jid, j in (workflow.get("jobs") or {}).items()}

        def job_id(name: str) -> str | None:
            return next((jid for jid, n in name_of.items() if name == n or name.startswith(n + " (")), None)

        def needed(job: dict[str, Any]) -> list[dict[str, Any]]:
            n = ((workflow.get("jobs") or {}).get(job_id(job["name"]) or "") or {}).get("needs") or []
            ids = {n} if isinstance(n, str) else set(n)
            return [j for j in done if job_id(j["name"]) in ids]

        # the critical path: from the job that finished last, back through the needed job that finished last
        job = max(done, key=lambda j: str(j["completed_at"]))
        total = handoff_seconds(job)
        while needed(job):
            job = max(needed(job), key=lambda j: str(j["completed_at"]))
            total += handoff_seconds(job)
        out["critical_path_seconds"] = round(total)
    return out


def job_record(job: dict[str, Any]) -> dict[str, Any]:
    return {"name": job["name"], "status": job.get("status"), "conclusion": job.get("conclusion"),
            "labels": job.get("labels"), "started_at": job.get("started_at"), "completed_at": job.get("completed_at"),
            "steps": [{k: s.get(k) for k in _STEP_KEYS} for s in job.get("steps") or []]}


def failed_steps(jobs: list[dict[str, Any]]) -> list[str]:
    """Failing step names in execution order (job start, then step number), like act's `failed_steps`. GitHub's own
    "Set up job"/"Complete job" steps and the "Post <step>" cleanup of an action step are left out."""
    out = []
    for job in sorted(jobs, key=lambda j: (j.get("started_at") is None, j.get("started_at") or "")):
        steps = sorted(job.get("steps") or [], key=lambda s: s.get("number") or 0)
        names = {s.get("name") for s in steps}
        for s in steps:
            name = str(s.get("name") or "")
            if name in ("Set up job", "Complete job") or (name.startswith("Post ") and name[5:] in names):
                continue
            if s.get("conclusion") in ("failure", "timed_out"):
                out.append(name)
    return out


# ------------------------------------------------------------------------------------------- JIT runners
class RunnerPool:
    def __init__(self, gh: GitHub, repo: str, label: str, max_parallel: int = 4):
        self.gh, self.repo, self.label, self.max_parallel = gh, repo, label, max_parallel
        self.containers: list[str] = []
        self.runner_ids: list[int] = []

    def start_one(self) -> None:
        name = f"{self.label}-{len(self.containers) + 1}"
        cfg = self.gh.request("POST", f"/repos/{self.repo}/actions/runners/generate-jitconfig", json_body={
            "name": name, "runner_group_id": 1, "labels": ["self-hosted", self.label], "work_folder": "_work"})
        self.runner_ids.append(cfg["runner"]["id"])
        cid = subprocess.run(["docker", "run", "-d", "--rm", "--name", name, RUNNER_IMAGE, "./run.sh", "--jitconfig",
                              cfg["encoded_jit_config"]], capture_output=True, text=True, check=True).stdout.strip()
        self.containers.append(cid)
        log(f"started JIT runner {name}")

    def alive(self) -> int:
        out = subprocess.run(["docker", "ps", "-q", "--filter", f"name={self.label}-"], capture_output=True, text=True)
        return len([x for x in out.stdout.split() if x])

    def ensure(self, queued: int, running: int = 0) -> None:
        # One spare runner beyond the queued jobs. A JIT runner that is handed its job about a minute after
        # registering can find its registration gone ("Registration ... was not found" in the runner log, exit 0
        # without a job); GitHub then cancels the job assigned to it after a few minutes. A single-job run has no
        # second runner to fall back on, so the spare takes the job instead (seen on the 004/012/014 trace runs).
        # Live containers include the ones busy with `running` jobs, which cannot take a queued one.
        want = min(self.max_parallel, running + queued + 1)
        while self.alive() < want:
            self.start_one()

    def stop(self) -> None:
        for c in self.containers:
            subprocess.run(["docker", "rm", "-f", c], capture_output=True)
        for rid in self.runner_ids:
            try:
                self.gh.request("DELETE", f"/repos/{self.repo}/actions/runners/{rid}")
            except GitHubError:
                pass  # JIT runners de-register themselves after their job


# ------------------------------------------------------------------------------------------- run state
def _state_path(branch: str) -> Path:
    return budget.ACTIVE_DIR / f"{branch.replace('/', '_')}.json"


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path(state["branch"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")


def _quietly(what: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - cleanup must not mask the original outcome
        log(f"{what} failed: {e}")
        return None


def _abort(gh: GitHub, repo: str, state: dict[str, Any], run: dict[str, Any], reservation: dict[str, Any] | None,
           exc: BaseException) -> None:
    """Abnormal exit: cancel a dispatched, unfinished run; its reservation stays pending with what is known."""
    state["error"] = f"{type(exc).__name__}: {exc}"[:500]
    if state["state"] == "dispatching" and _quietly("checking the branch", branch_exists, gh, repo,
                                                    state["branch"]) is False:
        state["state"] = "not-dispatched"  # the branch was never created, so no run was triggered
        if reservation:
            _quietly("releasing the reservation", budget.release, reservation["id"], state["error"])
        _quietly("removing the run state", _state_path(state["branch"]).unlink, missing_ok=True)
        return
    if state.get("run_id") is None:
        found = _quietly("looking up the run", find_run, gh, repo, state["branch"], state["sha"], timeout=15)
        if found:
            state["run_id"], run = found["id"], found
    if state.get("run_id") is None:
        state["state"] = "unknown"
        log(f"{state['branch']} was dispatched but its run was not found: check {repo}'s Actions runs "
            f"for {state['sha'][:7]}")
    elif run.get("status") == "completed":
        state["state"] = "completed"
    else:
        try:
            state["state"] = "cancel-requested" if cancel_run(gh, repo, state["run_id"]) else "completed"
            log(f"run {state['run_id']}: {state['state']} after {state['error']}")
        except Exception as e:  # noqa: BLE001
            state.update(state="cancel-failed", cancel_error=str(e))
            log(f"run {state['run_id']}: cancel failed ({e}) - cancel it by hand")
    _quietly("saving the run state", _save_state, state)
    if reservation:
        _quietly("updating the reservation", budget.update_reservation, reservation["id"], run_id=state["run_id"],
                 state=state["state"], error=state["error"])


# ------------------------------------------------------------------------------------------- entry point
def run_remote(d: Path, model: dict[str, Any], mode: str, tier: str, scenario: dict[str, Any],
               source: dict[str, Any] | None, yes: bool = False, max_minutes: int | None = None,
               environments: bool = False, stubbed: list[str] | None = None) -> dict[str, Any]:
    gh = GitHub(cache_ttl=0)
    repo = harness_repo()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    branch = f"j2gha/run/{d.name}-{mode}-{tier}-{ts}"
    label = f"j2gha-{uuid.uuid4().hex[:8]}" if tier == "selfhosted" else None
    # `run --environments`: keep environments (as j2gha-<name>, each with a fresh canary secret) - gha.environments
    canaries = env_check.new_canaries(model) if environments else {}
    variant, notes = make_variant(model, mode, tier, scenario, source, runner_label=label, branch=branch,
                                  max_minutes=max_minutes or 10,
                                  environments={e: env_check.digest(v) for e, v in canaries.items()} or None,
                                  stubbed=stubbed)
    est = estimate_minutes(variant, mode)
    record: dict[str, Any] = {"tier": tier, "mode": mode, "repo": repo, "branch": branch, "estimate": est,
                              "variant_notes": notes}
    decision = None
    if tier == "hosted":
        decision = budget.guard(est, yes=yes, max_minutes=max_minutes, repo=repo)
        record["budget"] = {k: decision.get(k) for k in ("allowed", "reasons", "available_after_reserve",
                                                         "pending_minutes", "free_minutes", "usage_complete")}
        record["budget"].update(owner=(decision.get("account") or {}).get("owner"),
                                used_before=(decision.get("usage") or {}).get("used"))
        if not decision["allowed"]:
            record.update(result="refused", traces=[])
            return record
    if tier == "selfhosted" and notes["jobs"] > 50:
        record.update(result="refused", traces=[], error=f"{notes['jobs']} jobs is too many for local JIT runners")
        return record
    out = d / "runs" / f"{tier}-{mode}"
    out.mkdir(parents=True, exist_ok=True)
    if canaries:
        env_check.ensure(gh, repo, canaries)
        log(f"environments ready in {repo}: {', '.join(sorted(canaries))}")
    variant = {**variant, "name": REMOTE_WORKFLOW_NAME}
    yml = to_yaml(variant, f"# j2gha {tier} variant ({mode}) of examples/{d.name}\n")
    (out / "workflow.yml").write_text(yml)
    sha = orphan_commit(gh, repo, {WORKFLOW_PATH: yml}, f"j2gha {tier} {mode} run of examples/{d.name}")
    reservation = None
    if decision is not None:
        reservation = budget.reserve(decision, example=d.name, mode=mode, tier=tier, repo=repo, branch=branch,
                                     sha=sha, estimate=est)
        if reservation is None:
            record["budget"].update(allowed=False, reasons=[*record["budget"]["reasons"],
                                                            "allowance taken by concurrent reservations"])
            record.update(result="refused", traces=[])
            return record
        record["budget"]["reservation"] = reservation["id"]
    state: dict[str, Any] = {"run_id": None, "branch": branch, "sha": sha, "repo": repo, "tier": tier,
                             "example": d.name, "mode": mode, "reservation": reservation and reservation["id"],
                             "state": "dispatching", "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    pool = RunnerPool(gh, repo, label) if label else None
    started = time.time()
    run: dict[str, Any] = {}
    try:
        _save_state(state)
        create_branch(gh, repo, branch, sha)
        state["state"] = "dispatched"
        _save_state(state)
        log(f"pushed {branch} ({sha[:7]}) to {repo}")
        run = find_run(gh, repo, branch, sha)
        state.update(run_id=run["id"], state="running", run_url=run["html_url"])
        _save_state(state)
        if reservation:
            budget.update_reservation(reservation["id"], run_id=run["id"])
        record["run_url"] = run["html_url"]
        log(f"run {run['id']}: {run['html_url']}")
        limit = 60 * (5 + 2 * (max_minutes or 10)) if mode == "full" else 60 * 20
        timed_out = False
        while time.time() - started < limit:
            run = gh.get(f"/repos/{repo}/actions/runs/{run['id']}", use_cache=False)
            if pool is not None:
                jobs = list_jobs(gh, repo, run["id"])
                queued = sum(1 for j in jobs if j["status"] in ("queued", "waiting", "pending"))
                if queued:
                    pool.ensure(queued, sum(1 for j in jobs if j["status"] == "in_progress"))
            if run["status"] == "completed":
                break
            time.sleep(10 if pool is None else 5)
        else:
            timed_out = True
            log(f"run {run['id']}: timed out after {limit // 60} min; cancelling")
            cancel_run(gh, repo, run["id"])
            run = await_completion(gh, repo, run["id"])
        done = run.get("status") == "completed"
        jobs = list_jobs(gh, repo, run["id"])
        logs = run_logs_zip(gh, repo, run["id"])
        if not logs:
            logs = {f"{j['name']}.txt": job_log(gh, repo, j["id"]) for j in jobs}
        (out / "logs.json").write_text(json.dumps({k: v[-200_000:] for k, v in logs.items()}))
        top_level = {k: v for k, v in logs.items() if "/" not in k} or logs
        traces = _timed_traces(top_level)
        billable = sum(budget.job_billable_minutes(j) for j in jobs) if done else None
        record.update(result=run.get("conclusion") or ("cancelled" if timed_out else run.get("status")),
                      run_id=run["id"], traces=traces, jobs=[job_record(j) for j in jobs],
                      failed_steps=failed_steps(jobs), billable_minutes=billable,
                      seconds=round(time.time() - started, 1))
        if mode == "full" and done:
            try:
                listing = list_artifacts(gh, repo, run["id"])
            except GitHubError as e:
                listing = None
                record["outputs"] = {"archived": [], "tests": None, "problems": [f"run artifacts unreadable: {e}"]}
            if listing is not None:
                record["outputs"] = run_outputs(gh, repo, run["id"], model, listing, {WORKFLOW_PATH: yml})
                if cost := handoff_cost(jobs, listing[0], variant, run):
                    record["handoff"] = cost
        if environments:
            record["environments"] = {"secret_checks": env_check.secret_checks(jobs)}
            try:
                record["environments"]["entered"] = env_check.entered(gh, repo, sha)
            except GitHubError as e:
                record["environments"]["error"] = f"deployments unreadable: {e}"
        if timed_out:
            record["error"] = ("timed out; run cancelled" if done else
                               "timed out; cancel requested but the run had not completed (reservation left pending)")
        if reservation:
            if done:
                budget.settle(reservation["id"], billable, result=record["result"])
            else:
                budget.update_reservation(reservation["id"], state="cancel-requested")
        if done:
            _state_path(branch).unlink(missing_ok=True)
        else:
            state["state"] = "cancel-requested"
            _save_state(state)
        log(f"run {run['id']} -> {record['result']} ({len(traces)} trace events, "
            f"{billable if done else '?'} billable min)")
    except BaseException as e:
        _abort(gh, repo, state, run, reservation, e)
        raise
    finally:
        if pool is not None:
            _quietly("stopping the runners", pool.stop)
        _quietly(f"deleting {branch}", delete_branch, gh, repo, branch)
    return record


_TS = re.compile(r"^\ufeff?\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ?")


def _timed_traces(logs: dict[str, str]) -> list[dict[str, Any]]:
    """Trace events of all job logs in the order they happened: by the runner's log timestamps (a log without them
    keeps the previous line's), falling back to log order for ties."""
    timed: list[tuple[str, int, int, dict[str, Any]]] = []
    for n, (_, text) in enumerate(sorted(logs.items())):
        ts = ""
        for i, line in enumerate(text.splitlines()):
            m = _TS.match(line)
            if m:
                ts = m.group(0).strip().lstrip("\ufeff")
            timed += [(ts, n, i, ev) for ev in parse_traces(_TS.sub("", line))]
    return [ev for *_, ev in sorted(timed, key=lambda t: t[:3])]
