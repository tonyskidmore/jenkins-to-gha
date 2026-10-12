"""Derive executable variants of a converted workflow for the act / self-hosted / hosted tiers.

trace mode: every step that corresponds to a traced Jenkins step prints the same `J2GHA-TRACE` marker the
            localised Jenkinsfile prints; conversion-only steps (setup, artifact hand-off) are dropped; containers,
            services and environments are removed (environments are kept on request: `run --environments`,
            gha.environments); everything runs on ubuntu (no OS multipliers).
full mode:  the converted workflow as generated, with checkout pointed at the original source repository/commit,
            timeouts clamped and (for act) non-Linux jobs removed; archive uploads keep Jenkins' archive paths
            (outputs.root_marker) for the outputs comparison.
Both: `on:` is replaced for the target and Jenkins-compatible env (BRANCH_NAME...) is pinned to the scenario so
`when` conditions take the same branch as the Jenkins run. Converted pipelines are third-party code: every
`secrets.*` reference becomes the fake value the Jenkins reference is given (a credential id such as `github_token`
must never select a real operator or repository secret), and job-container options that would reach the host
(volumes, --privileged, ...) are dropped.
"""

from __future__ import annotations

import copy
import itertools
import re
import shlex
from typing import Any

from ..convert.generator import JENKINS_ENV
from ..jenkins.localize import FAKE_PASSWORD, FAKE_SECRET, FAKE_USER, STUB_VALUE, STUBBED_PROPERTY_CHANGE
from ..outputs import root_marker
from ..trace import marker_cmd

SECRET_REF = re.compile(r"\$\{\{\s*secrets\.([A-Za-z0-9_]+)\s*\}\}")
# docker run options a job container must not get in a harness run (host mounts, privileges, host namespaces)
# `docker create` options a converted container may keep in execution variants (an allowlist: anything else can reach
# the host - mounts, devices, namespaces, capabilities, networks - and is dropped, however it is spelled).
SAFE_VALUE_OPTIONS = {"-u", "--user", "-w", "--workdir", "-e", "--env", "--entrypoint", "--hostname", "--cpus", "-m",
                      "--memory", "--memory-swap", "--shm-size", "--ulimit", "-l", "--label", "--platform", "--tmpfs"}
SAFE_FLAG_OPTIONS = {"--init", "--read-only", "--rm", "-i", "--interactive", "-t", "--tty"}
MAX_MATRIX_JOBS = 256  # GitHub's per-matrix limit: the bound for matrices that cannot be expanded statically


_STUBBED = re.compile(re.escape(STUBBED_PROPERTY_CHANGE).replace(re.escape("{}"), "([^']+)"))


def stubbed_properties(reference: dict[str, Any] | None) -> list[str]:
    """Environment-like (upper-case) properties the Jenkins reference ran with as permissive stubs: an undeclared
    `TARGET_LOCATION` reads 'j2gha-stub' there, so the converted run gets the same value instead of an empty one."""
    changes = ((reference or {}).get("localisation") or {}).get("changes") or []
    names = (m.group(1) for c in changes if (m := _STUBBED.fullmatch(c)))
    return list(dict.fromkeys(n for n in names if re.fullmatch(r"[A-Z_][A-Z0-9_]*", n)))


def make_variant(model: dict[str, Any], mode: str, target: str, scenario: dict[str, Any],
                 source: dict[str, Any] | None = None, runner_label: str | None = None,
                 branch: str | None = None, max_minutes: int = 10,
                 environments: dict[str, str] | None = None,
                 stubbed: list[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """``environments`` (remote tiers, `run --environments`): harness environment name -> sha256 of its canary
    secret; the variant then keeps every job's environment under that name (gha.environments). Otherwise every
    `environment` is removed. ``stubbed``: stubbed_properties() of the Jenkins reference."""
    keep_env = bool(environments) and target != "act"
    wf = copy.deepcopy(model)
    # only declared parameters (the dispatch inputs) can be set by a scenario; pipeline and harness env cannot
    inputs = ((wf.get("on") or {}).get("workflow_dispatch") or {}).get("inputs") or {}
    notes: dict[str, Any] = {"dropped_jobs": [], "matrix_jobs": 0}
    if target == "act":
        wf["on"] = {"push": None, "workflow_dispatch": None}
    else:
        wf["on"] = {"push": {"branches": [branch or "j2gha/run/**"]}, "workflow_dispatch": None}
    wf.pop("concurrency", None)
    env = wf.setdefault("env", {})

    def pin(name: str, value: str, always: bool = False) -> None:
        """Pin a Jenkins-provided variable to the scenario - only where the generator emitted its default
        (JENKINS_ENV): a value the pipeline declares itself (environment {}, a parameter) is its own (review R8-8)."""
        if env.get(name, None if not always else JENKINS_ENV[name]) == JENKINS_ENV[name]:
            env[name] = value

    pin("BRANCH_NAME", scenario.get("branch", "main"), always=True)
    pin("TAG_NAME", scenario.get("tag", ""), always=True)
    pin("CHANGE_ID", scenario.get("change_id", ""), always=True)
    pin("GIT_BRANCH", scenario.get("git_branch", scenario.get("branch", "main")), always=True)
    for k in ("CHANGE_TARGET", "CHANGE_BRANCH", "CHANGE_AUTHOR", "CHANGE_TITLE", "CHANGE_URL"):
        pin(k, scenario.get(k.lower(), ""))
    for name in stubbed or []:
        if name not in env and name not in inputs:  # the pipeline's own value, or a parameter, is never replaced
            env[name] = STUB_VALUE
    if mode == "full" and source and source.get("sha"):
        # the checkout is pinned to the cited upstream commit on every target (act's workspace holds it too):
        # GIT_COMMIT names that commit, as Jenkins' does, not the harness run branch's `github.sha`
        pin("GIT_COMMIT", str(source["sha"]))
    for name, value in (scenario.get("params") or {}).items():
        if name in inputs and name in env:  # the scenario's value replaces the dispatch/default expression
            env[name] = str(value)
    for job_id in list(wf["jobs"]):
        job = wf["jobs"][job_id]
        ro = job.get("runs-on", "ubuntu-latest")
        non_linux = isinstance(ro, str) and (ro.startswith("windows") or ro.startswith("macos"))
        if target == "selfhosted":
            job["runs-on"] = ["self-hosted", runner_label or "j2gha"]
        elif mode == "trace":
            job["runs-on"] = "ubuntu-latest"
        elif target == "act" and non_linux:
            notes["dropped_jobs"].append(f"{job_id} ({ro}: not runnable under act)")
            del wf["jobs"][job_id]
            continue
        if not keep_env:
            job.pop("environment", None)
        if mode == "trace":
            job.pop("container", None)
            job.pop("services", None)
            job["timeout-minutes"] = 5
            job["steps"] = _trace_steps(job.get("steps", []))
        else:
            job["timeout-minutes"] = min(int(job.get("timeout-minutes") or max_minutes), max_minutes)
            _confine_container(job, job_id, notes)
            for st in job.get("steps", []):
                uses = str(st.get("uses", ""))
                if uses.startswith("actions/upload-artifact@") and target != "act":
                    st.setdefault("with", {})["retention-days"] = 1  # read once by the harness, then storage cost
                if uses.startswith("actions/upload-artifact@") and (marker := root_marker(st.get("_j2gha") or {})):
                    # files keep their Jenkins archive paths, the identity the outputs comparison uses
                    w = st.setdefault("with", {})
                    w["path"] = f"{str(w.get('path') or '**').rstrip()}\n{marker}"
                if not uses.startswith("actions/checkout@"):
                    continue
                w = st.setdefault("with", {})
                if SECRET_REF.search(str(w.get("token", ""))):
                    del w["token"]  # a fake token would fail even for a public repository
                if "repository" in w:
                    if target == "act":
                        notes.setdefault("unauthenticated_checkouts", []).append(w["repository"])
                elif source and target != "act":
                    w["repository"] = source["repository"]
                    if source.get("sha"):
                        w["ref"] = source["sha"]
                # act: the workspace already holds the source at the pinned commit (fetched on the host, see
                # runners.act), and act treats a checkout of its own repository as already done
        cells = _matrix_cells(job)
        notes["matrix_jobs"] += cells
    # drop dangling needs after removing jobs
    for job in wf["jobs"].values():
        needs = job.get("needs")
        if needs:
            lst = [needs] if isinstance(needs, str) else list(needs)
            lst = [n for n in lst if n in wf["jobs"]]
            if lst:
                job["needs"] = lst if len(lst) > 1 else lst[0]
            else:
                job.pop("needs")
    notes["jobs"] = sum(_matrix_cells(j) for j in wf["jobs"].values())
    wf = _fake_secrets(wf)
    if keep_env and environments:
        from ..gha.environments import keep_in_variant
        keep_in_variant(wf, environments)  # after faking: the canary check is the one real secret reference
        notes["environments"] = sorted(environments)
    return wf, notes


def fake_secret(name: str) -> str:
    return FAKE_USER if name.endswith("_USR") else FAKE_PASSWORD if name.endswith("_PSW") else FAKE_SECRET


def _fake_secrets(obj: Any) -> Any:
    if isinstance(obj, str):
        return SECRET_REF.sub(lambda m: fake_secret(m.group(1)), obj)
    if isinstance(obj, list):
        return [_fake_secrets(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _fake_secrets(v) for k, v in obj.items()}
    return obj


def _confine_container(job: dict[str, Any], job_id: str, notes: dict[str, Any]) -> None:
    container = job.get("container")
    if not isinstance(container, dict):
        return
    container.pop("credentials", None)  # registry login with fake credentials would fail; pull anonymously
    opts = container.get("options")
    if not opts:
        return
    try:
        words = shlex.split(str(opts))
    except ValueError:
        words = str(opts).split()
    kept, dropped = _allowed_options(words)
    if dropped:
        notes.setdefault("dropped_container_options", {})[job_id] = " ".join(dropped)
    if kept:
        container["options"] = " ".join(shlex.quote(w) for w in kept)
    else:
        container.pop("options")


def _allowed_options(words: list[str]) -> tuple[list[str], list[str]]:
    """Split `docker` options into (kept, dropped) by allowlist. Handles `--opt val`, `--opt=val`, `-o val`, `-oval`
    and clusters of flags (`-it`); an option that takes a value drops that value with it."""
    kept: list[str] = []
    dropped: list[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        i += 1
        if not w.startswith("-") or w == "-":
            dropped.append(w)  # a stray value: it belongs to no option we kept
            continue
        if w.startswith("--"):
            name, _, value = w.partition("=")
            inline = "=" in w
            is_flag = name in SAFE_FLAG_OPTIONS
            safe = is_flag or name in SAFE_VALUE_OPTIONS
        else:
            name, value = w[:2], w[2:]
            inline = bool(value)  # `-v/x:/y`: the value is attached
            is_flag = all(c in "it" for c in w[1:])
            safe = is_flag or name in SAFE_VALUE_OPTIONS
            if is_flag and inline:
                inline = False  # `-it`: a cluster of flags, no value
        group = [w]
        if not is_flag and not inline and i < len(words) and not words[i].startswith("-"):
            value = words[i]
            group.append(value)
            i += 1
        if name in ("-e", "--env") and "=" not in value:
            safe = False  # `-e NAME` copies the value from the host environment
        (kept if safe else dropped).extend(group)
    return kept, dropped


def _trace_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for st in steps:
        meta = st.get("_j2gha") or {}
        events: list[tuple[str, str]] = []
        if meta.get("trace"):
            events = [(meta.get("stage", ""), meta.get("kind", "?"))]
        elif meta.get("trace_events"):
            events = [(e[0], e[1]) for e in meta["trace_events"]]
        if not events and not meta.get("trace_run"):
            continue
        cmd = "\n".join(marker_cmd(stage, k) for stage, k in events)
        if meta.get("trace_run"):
            # control flow (variables later conditions read): runs, printing markers for the branch it takes
            cmd = "\n".join(x for x in (cmd, meta["trace_run"]) if x)
        if meta.get("kind") == "error":
            cmd += "\nexit 1"
        new = {"name": st.get("name", "trace")}
        for key in ("id", "if", "continue-on-error"):
            if key in st:
                new[key] = st[key]
        if "env" in st:
            new["env"] = st["env"]
        new["run"] = cmd
        new["_j2gha"] = meta
        out.append(new)
    return out or [{"name": "no traced steps", "run": "true"}]


def _matrix_cells(job: dict[str, Any]) -> int:
    return matrix_expansion(job)[0]


def matrix_expansion(job: dict[str, Any]) -> tuple[int, bool]:
    """(number of jobs, exact?) following GitHub's rules: the axes' product, minus combinations matching an exclude
    entry (partial matches allowed), plus include entries that cannot be merged into any remaining combination.
    Matrices built from expressions cannot be expanded here: they count as GitHub's 256-job maximum."""
    m = (job.get("strategy") or {}).get("matrix")
    if m is None:
        return 1, True
    if not isinstance(m, dict):
        return MAX_MATRIX_JOBS, False
    axes = {k: v for k, v in m.items() if k not in ("include", "exclude")}
    include, exclude = m.get("include") or [], m.get("exclude") or []
    literal = all(isinstance(v, list) for v in axes.values()) and isinstance(include, list) and \
        isinstance(exclude, list) and all(isinstance(e, dict) for e in [*include, *exclude]) and \
        "${{" not in repr(m)
    if not literal:
        return MAX_MATRIX_JOBS, False
    keys = list(axes)
    combos = [dict(zip(keys, vals, strict=True)) for vals in itertools.product(*axes.values())] if keys else []

    def same(a: Any, b: Any) -> bool:
        return str(a) == str(b)

    combos = [c for c in combos if not any(all(k in c and same(c[k], v) for k, v in e.items()) for e in exclude)]
    extra = 0
    for inc in include:
        if not any(all(same(c[k], v) for k, v in inc.items() if k in axes) for c in combos):
            extra += 1
    return min(max(1, len(combos) + extra), MAX_MATRIX_JOBS), True


def estimate_minutes(wf: dict[str, Any], mode: str) -> dict[str, int]:
    """Billable-minute estimate. Every job is rounded up to a whole minute; OS multipliers applied."""
    typical = worst = 0
    unbounded = False
    for job in wf["jobs"].values():
        cells, exact = matrix_expansion(job)
        unbounded = unbounded or not exact
        ro = str(job.get("runs-on", "ubuntu-latest"))
        mult = 10 if "macos" in ro else (2 if "windows" in ro else 1)
        if "self-hosted" in ro:
            mult = 0
        timeout = int(job.get("timeout-minutes") or 360)
        typical += cells * mult * (1 if mode == "trace" else max(1, min(timeout, 5)))
        worst += cells * mult * timeout
    return {"typical": typical, "worst_case": worst, "unbounded": unbounded}
