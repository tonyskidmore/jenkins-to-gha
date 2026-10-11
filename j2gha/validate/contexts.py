"""Structural checks on a generated workflow that no linter reports usefully, each the symptom of a bug class the
conversion has had (a remediation review, track D):

``job-if-context``     a job-level `if:` reads a context GitHub does not provide there (`env`, `steps`, `matrix`...)
``needs-reference``    `needs.<job>...` names a job that is not one of the job's direct `needs`
``step-env-scope``     an entry of a step's `env:` mapping reads another entry of the same mapping (GitHub evaluates the
                       mapping against the workflow/job env only; a step's `if:` *does* see the step's own `env:`,
                       verified on GitHub with a self-hosted run)
``unknown-function``   an expression calls a function GitHub does not have (act and GitHub reject the workflow)
``skip-propagation``   a job needs a job that can be skipped but has no status function, so it is skipped too
``decision-reevaluated``  a job that consumes a gate job's `run` output evaluates the gate's own condition again
``handoff-source``     a job restores a workspace (`j2gha-ws-<job>`) of a job it does not (transitively) need, or that
                       no job uploads: the artifact may not exist yet, or never
"""

from __future__ import annotations

import re
from typing import Any

FUNCTIONS = {"contains", "startsWith", "endsWith", "format", "join", "toJSON", "fromJSON", "hashFiles", "always",
             "failure", "success", "cancelled"}
STATUS = re.compile(r"\b(always|failure|success|cancelled)\(\)")
JOB_IF_FORBIDDEN = re.compile(r"\b(env|steps|matrix|secrets|job|runner|strategy)\.")
_STRING = re.compile(r"'(?:[^']|'')*'")
_EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)


def _can_skip(job_if: Any) -> bool:
    """Does the job's `if:` hold a condition beyond status functions (a bare `!failure() && !cancelled()` or
    `always()` never skips a job by itself)?"""
    rest = re.sub(r"!?\s*(always|failure|success|cancelled)\(\)|&&|\|\||[()\s]", "", _code(str(job_if)))
    return bool(rest)


def _code(expr: str) -> str:
    """An expression without its string literals (their text is not code)."""
    return _STRING.sub("''", expr)


def _expressions(value: Any, is_if: bool = False) -> list[str]:
    """The expressions inside a YAML value: `${{ }}` bodies, or the whole string of an `if:`."""
    if isinstance(value, str):
        inner = _EXPR.findall(value)
        return [x for x in inner] if inner else ([value] if is_if else [])
    if isinstance(value, dict):
        return [e for v in value.values() for e in _expressions(v)]
    if isinstance(value, list):
        return [e for v in value for e in _expressions(v)]
    return []


def _gate_entries(jobs: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """gate job id -> (name, condition) of the entry step whose output is the job's `run` output."""
    out: dict[str, tuple[str, str]] = {}
    for jid, job in jobs.items():
        ref = re.search(r"steps\.([\w-]+)\.outputs\.run", str((job.get("outputs") or {}).get("run", "")))
        if ref:
            step = next((st for st in job.get("steps") or [] if st.get("id") == ref.group(1)), None)
            if step and step.get("if"):
                out[jid] = (str(step.get("name")), str(step["if"]))
    return out


def context_checks(wf: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(rule: str, message: str) -> None:
        findings.append({"rule": rule, "severity": "error", "message": message})

    jobs = wf.get("jobs") or {}
    gates = _gate_entries(jobs)
    workflow_env = set((wf.get("env") or {}))
    for jid, job in jobs.items():
        needs = job.get("needs") or []
        needs = [needs] if isinstance(needs, str) else list(needs)
        job_if = job.get("if")
        if job_if is not None:
            code = _code(str(job_if))
            if bad := JOB_IF_FORBIDDEN.search(code):
                add("job-if-context", f"job '{jid}': `if:` reads `{bad.group(1)}`, which is not available at job level")
        scopes = [(f"job '{jid}'", e) for e in _expressions(job.get("outputs"))]
        scopes += [(f"job '{jid}'", e) for e in _expressions(job.get("env"))]
        if job_if is not None:
            scopes.append((f"job '{jid}' if", str(job_if)))
        job_env = workflow_env | set((job.get("env") or {}))
        for st in job.get("steps") or []:
            name = st.get("name") or st.get("id") or "?"
            own = set((st.get("env") or {})) - job_env  # defined by this step's env only
            parts = [("if", e) for e in _expressions(st.get("if"), is_if=True)] + \
                    [("env", e) for e in _expressions(st.get("env"))] + \
                    [("with", e) for e in _expressions(st.get("with"))]
            for where, expr in parts:
                scopes.append((f"job '{jid}' step '{name}' {where}", expr))
                if where == "env":
                    for var in re.findall(r"\benv\.([A-Za-z_]\w*)", _code(expr)):
                        if var in own:
                            add("step-env-scope", f"job '{jid}' step '{name}': an `env:` entry reads env.{var}, a sibling "
                                                  "entry of the same mapping (not visible there: it evaluates to '')")
        for where, expr in scopes:
            code = _code(expr)
            for ref in re.findall(r"\bneeds\.([A-Za-z_][\w-]*)\b", code):
                if ref not in needs:
                    add("needs-reference", f"{where}: needs.{ref} is not in the job's direct `needs` {needs}")
            for fn in re.findall(r"\b([A-Za-z_]\w*)\(", code):
                if fn not in FUNCTIONS:
                    add("unknown-function", f"{where}: `{fn}()` is not a GitHub Actions expression function")
        for gate_id, (entry_name, cond) in gates.items():
            if gate_id == jid:
                continue
            for st in job.get("steps") or []:
                # the stage's entry step by name, or any step of a job that consumes the gate (`needs` it directly)
                if cond in str(st.get("if")) and (st.get("name") == entry_name or gate_id in needs):
                    add("decision-reevaluated", f"job '{jid}' step '{st.get('name')}' evaluates `{cond}` again "
                                                f"although '{gate_id}' already decided it: the two can disagree")
        if needs and not STATUS.search(_code(str(job_if or ""))):
            for n in needs:
                dep_if = (jobs.get(n) or {}).get("if")
                if dep_if is not None and _can_skip(dep_if):
                    add("skip-propagation", f"job '{jid}' needs '{n}', which can be skipped (`if: {dep_if}`), "
                                            "but has no status function: it would be skipped too")
    _handoff_sources(jobs, add)
    return findings


def _handoff_sources(jobs: dict[str, Any], add: Any) -> None:
    def needs_of(jid: str) -> list[str]:
        n = (jobs.get(jid) or {}).get("needs") or []
        return [n] if isinstance(n, str) else list(n)

    def upstream(jid: str, seen: set[str]) -> set[str]:
        for n in needs_of(jid):
            if n not in seen:
                seen.add(n)
                upstream(n, seen)
        return seen

    def names(job: dict[str, Any], action: str) -> list[str]:
        return [str((st.get("with") or {}).get("name", "")) for st in job.get("steps") or []
                if str(st.get("uses", "")).startswith(action)
                and str((st.get("with") or {}).get("name", "")).startswith("j2gha-ws-")]

    uploaded = {name: jid for jid, job in jobs.items() for name in names(job, "actions/upload-artifact@")}
    for jid, job in jobs.items():
        before = upstream(jid, set())
        for name in names(job, "actions/download-artifact@"):
            producer = uploaded.get(name)
            if producer is None:
                add("handoff-source", f"job '{jid}' restores '{name}', which no job uploads")
            elif producer not in before:
                add("handoff-source", f"job '{jid}' restores '{name}' from job '{producer}', which it does not need: "
                                      "the workspace may not have been handed on yet")
