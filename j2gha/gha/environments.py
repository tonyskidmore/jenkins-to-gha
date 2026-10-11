"""Environments in remote execution variants (Phase 4, P4.2, opt-in with `run --environments`).

A converted `input` becomes a job `environment` (protected by required reviewers in production). Without this option
every execution variant removes `environment`, so no harness run ever enters one. With it, remote variants keep each
environment under a harness name (`j2gha-<name>`, so a run never touches a real environment of the harness
repository), and the run is checked for:

* *entry*: the environments the run entered (its deployments) are those of the stages whose `input` Jenkins reached
  (full mode: the controller records the stage of every input it auto-approves; trace mode: the stubbed input's trace
  event) - a skipped gated stage enters none;
* *secrets*: every job in an environment first checks that the environment's secret is visible to it. The harness sets
  a random canary value (`J2GHA_ENV_CANARY`, not a credential) per environment and the step compares its sha256, so a
  repository-level secret of the same name does not pass.

Not covered: the approval itself. Required reviewers on a private repository need GitHub Enterprise (on Free, Pro and
Team they are public-repository only), so the harness environments have no protection rules.
"""

from __future__ import annotations

import hashlib
import re
import secrets as _random
import shutil
import subprocess
from typing import Any

PREFIX = "j2gha-"
CANARY = "J2GHA_ENV_CANARY"
CHECK_STEP = "j2gha: environment secret check"


def environment_name(value: Any) -> str | None:
    """A job's `environment:` (a name, or a mapping with `name`)."""
    if isinstance(value, dict):
        value = value.get("name")
    return str(value) if value else None


def harness_name(name: str) -> str:
    return (PREFIX + re.sub(r"[^A-Za-z0-9_.-]", "-", name))[:255]


def environment_stages(model: dict[str, Any] | None) -> dict[str, set[str]]:
    """Harness environment name -> the Jenkins stages whose `input` it stands for (the job's input steps; a job
    without one stands for all of its stages)."""
    out: dict[str, set[str]] = {}
    for job in ((model or {}).get("jobs") or {}).values():
        name = environment_name(job.get("environment"))
        if not name:
            continue
        metas = [st.get("_j2gha") or {} for st in job.get("steps", [])]
        stages = {m["stage"] for m in metas if m.get("kind") == "input" and m.get("stage")} or \
                 {m["stage"] for m in metas if m.get("stage")}
        out.setdefault(harness_name(name), set()).update(stages)
    return out


def new_canaries(model: dict[str, Any] | None) -> dict[str, str]:
    """A fresh random canary value per harness environment of the model."""
    return {name: _random.token_hex(16) for name in environment_stages(model)}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def keep_in_variant(wf: dict[str, Any], digests: dict[str, str]) -> None:
    """Keep every job's environment under its harness name and put the canary check first. Runs after the variant's
    secrets were faked, so the check is the only reference to a real secret."""
    for job in wf["jobs"].values():
        name = environment_name(job.get("environment"))
        if not name:
            continue
        env = harness_name(name)
        job["environment"] = env
        check = (f'actual=$(printf %s "${CANARY}" | sha256sum | cut -d" " -f1)\n'
                 f'if [ "$actual" != "{digests[env]}" ]; then\n'
                 f'  echo "::error::secret {CANARY} of environment {env} is not visible to this job"\n'
                 f'  exit 1\n'
                 f'fi')
        job["steps"] = [{"name": CHECK_STEP, "env": {CANARY: f"${{{{ secrets.{CANARY} }}}}"}, "run": check},
                        *job.get("steps", [])]


def ensure(gh: Any, repo: str, canaries: dict[str, str]) -> None:
    """Create the harness environments (no protection rules) and set each one's canary secret (`gh` encrypts it)."""
    if canaries and not shutil.which("gh"):
        raise RuntimeError("run --environments needs the GitHub CLI (`gh`) to set environment secrets")
    for env, value in canaries.items():
        gh.request("PUT", f"/repos/{repo}/environments/{env}", json_body={})
        subprocess.run(["gh", "secret", "set", CANARY, "--env", env, "--repo", repo, "--body", value],
                       check=True, capture_output=True, text=True, timeout=60)


def entered(gh: Any, repo: str, sha: str) -> list[str]:
    """Environments the run of commit `sha` entered (GitHub creates a deployment for every job in an environment)."""
    deployments = gh.get(f"/repos/{repo}/deployments", params={"sha": sha, "per_page": 100}, use_cache=False) or []
    return sorted({d.get("environment") for d in deployments if d.get("environment")})


def secret_checks(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The canary check of every job that ran it: job name and the step's conclusion."""
    return [{"job": j.get("name"), "conclusion": s.get("conclusion")}
            for j in jobs for s in j.get("steps") or [] if s.get("name") == CHECK_STEP]


def compare(ref: dict[str, Any], rec: dict[str, Any], model: dict[str, Any] | None) -> dict[str, Any]:
    """{"status": same | differs | inconclusive, ...}: environments entered vs the inputs Jenkins reached, and the
    canary check of every job that entered one."""
    got = rec.get("environments") or {}
    # full mode: the stages whose input the controller approved; trace mode stubs `input` and traces it instead
    traced = {t.get("stage") for t in ref.get("traces") or [] if t.get("step") == "input"}
    if "approved_inputs" not in ref and ref.get("mode") != "trace":
        return {"status": "inconclusive",
                "reason": "the Jenkins reference did not record the inputs it reached (re-run the jenkins tier)"}
    stages = environment_stages(model)
    reached = set(ref.get("approved_inputs") or []) | traced
    expected = sorted(env for env, ss in stages.items() if ss & reached)
    actual = sorted(got.get("entered") or [])
    failed = [c["job"] for c in got.get("secret_checks") or [] if c.get("conclusion") != "success"]
    out = {"expected": expected, "entered": actual, "secret_not_visible": failed,
           "status": "same" if expected == actual and not failed else "differs"}
    if got.get("error"):
        out.update(status="inconclusive", reason=got["error"])
    return out


def list_harness(gh: Any, repo: str) -> list[str]:
    data = gh.get(f"/repos/{repo}/environments", params={"per_page": 100}, use_cache=False) or {}
    return sorted(e["name"] for e in data.get("environments") or [] if e["name"].startswith(PREFIX))


def delete_harness(gh: Any, repo: str) -> list[str]:
    """Delete the harness's own environments (`j2gha-*`) and their secrets; nothing else is touched."""
    names = list_harness(gh, repo)
    for name in names:
        gh.request("DELETE", f"/repos/{repo}/environments/{name}")
    return names
