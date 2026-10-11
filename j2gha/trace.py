"""Shared definitions for differential *trace* runs.

In trace mode both sides (localised Jenkinsfile on Jenkins, converted workflow on act/GHA) replace side-effecting
steps with a marker line::

    J2GHA-TRACE {"stage": "<Jenkins STAGE_NAME>", "step": "<jenkins step name>"}

The sequence of markers per stage is the behavioural fingerprint that is compared across tiers. Commands are not
executed, so the comparison isolates *control-flow* fidelity (stage graph, when/post semantics, parallel/matrix
fan-out, script{} translation) from toolchain availability.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ir import Pipeline, Stage

MARKER = "J2GHA-TRACE"
MARKER_RE = re.compile(MARKER + r" (\{.*?\})\s*$")

PIPELINE_POST_STAGE = "Declarative: Post Actions"
IMPLICIT_CHECKOUT_STAGE = "Declarative: Checkout SCM"

def step_name_key(name: Any) -> str:
    """A step name as GitHub reports it: surrounding whitespace trimmed, internal runs collapsed (the generator names
    steps this way and the harness maps a failed step back to its stage by it)."""
    return " ".join(str(name or "").split())


# Leaf steps that are stubbed with a marker on the Jenkins side and emitted as markers on the GHA side.
TRACED_STEPS = [
    "sh", "bat", "powershell", "pwsh", "echo", "checkout", "git", "archiveArtifacts", "archive", "junit", "stash",
    "unstash", "input", "build", "error", "unstable", "mail", "emailext", "slackSend", "office365ConnectorSend",
    "publishHTML", "publishCoverage", "recordCoverage", "jacoco", "cobertura", "recordIssues", "deleteDir",
    "cleanWs", "sleep", "writeFile", "httpRequest", "copyArtifacts", "waitForQualityGate",
    "githubNotify", "setGitHubPullRequestStatus", "step", "fingerprint", "s3Upload", "s3Download",
]

# Steps stubbed silently: GHA maps them to workflow-level constructs (concurrency, on:), not to steps.
SILENT_STUBS = ["milestone", "properties", "buildDiscarder"]

# Block steps whose body is executed but which are stubbed so they need no real resources.
STUBBED_WRAPPERS = [
    "withCredentials", "sshagent", "withDockerRegistry", "withMaven", "withSonarQubeEnv", "container", "wrap",
    "ansiColor", "withAWS", "withKubeConfig", "withVault", "configFileProvider", "withGradle", "nodejs",
    "withPythonEnv", "timestamps", "withDockerContainer", "withDockerServer", "azureCLI", "retry", "podTemplate",
    "lock",  # a label/resource the disposable controller does not define; GHA maps it to concurrency
]


def marker_cmd(stage: str, step: str) -> str:
    """Shell command printing a trace marker (GString stage names are expanded by the shell)."""
    if "${" in stage:
        # Jenkins evaluates GString stage names (e.g. "${PLATFORM} - build" inside a matrix): let the shell expand
        # the same variables, which are exported as matrix env on the job
        shell_stage = stage.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
        return f"printf '%s {{\"stage\":\"%s\",\"step\":\"%s\"}}\\n' {MARKER} \"{shell_stage}\" '{step}'"
    payload = json.dumps({"stage": stage, "step": step}, separators=(",", ":")).replace("'", "'\"'\"'")
    return f"printf '%s %s\\n' {MARKER} '{payload}'"


def trace_line(stage: str, step: str) -> str:
    return f"{MARKER} " + json.dumps({"stage": stage, "step": step}, separators=(",", ":"))


def parse_traces(log: str) -> list[dict[str, Any]]:
    out = []
    for raw in log.splitlines():
        line = raw.rstrip()
        m = MARKER_RE.search(line)
        if not m:
            continue
        # skip echoed command lines (GHA prints the script before running it)
        prefix = line[: m.start()]
        if "printf" in prefix or "echo" in prefix.split()[-1:]:
            continue
        try:
            out.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    return out


def by_stage(traces: list[dict[str, Any]]) -> dict[str, list[str]]:
    acc: dict[str, list[str]] = defaultdict(list)
    for t in traces:
        acc[t.get("stage", "")].append(t.get("step", ""))
    return dict(acc)


# Run results normalised across Jenkins (SUCCESS...) and GitHub/act (success...); anything else is infrastructure
# (NOT_RUN, timeout, error, refused...) and never makes a comparison.
OUTCOMES = {"success": "success", "failure": "failure", "unstable": "unstable", "aborted": "cancelled",
            "cancelled": "cancelled"}


def outcome(result: Any) -> str:
    return OUTCOMES.get(str(result or "").lower(), "infra")


def concurrent_stages(model: dict[str, Any] | None) -> set[str]:
    """Stages whose trace events may legitimately interleave: emitted by several jobs (parallel branches split from
    one stage), by a matrix job (every cell), or inside a scripted `parallel` step. Elsewhere order is significant."""
    jobs_of: dict[str, set[str]] = defaultdict(set)
    out: set[str] = set()
    for jid, job in ((model or {}).get("jobs") or {}).items():
        matrix = bool((job.get("strategy") or {}).get("matrix"))
        for st in job.get("steps", []):
            meta = st.get("_j2gha") or {}
            stages = ([meta.get("stage", "")] if meta.get("trace") else []) + [e[0] for e in meta.get("trace_events", [])]
            for stage in stages:
                jobs_of[stage].add(jid)
                if matrix or meta.get("concurrent"):
                    out.add(stage)
    return out | {s for s, j in jobs_of.items() if len(j) > 1}


def stage_order(ir: "Pipeline | None") -> list[tuple[str, str]]:
    """The partial order the *original* pipeline imposes on its stages, as (before, after) pairs: stages run one after
    the other, except that the branches of a `parallel` are mutually unordered - each branch is a sequence of its own,
    and the whole `parallel` sits between its neighbours - and the inner stages of a matrix interleave across cells
    (no pairs inside it). Stages whose name is a runtime GString, or that occur twice, cannot be told apart in a trace
    and are left out. Scripted pipelines declare no stage structure: no pairs, so only per-stage sequences are
    compared there."""
    pairs: set[tuple[str, str]] = set()

    def names(st: "Stage") -> list[str]:
        out = [st.name]
        for child in [*st.parallel, *st.stages, *(st.matrix.stages if st.matrix else [])]:
            out += names(child)
        return out

    def connect(units: list[list[str]]) -> None:
        for i, early in enumerate(units):
            for late in units[i + 1:]:
                pairs.update((a, b) for a in early for b in late)

    def sequence(stages: list["Stage"]) -> list[list[str]]:
        units: list[list[str]] = []
        for st in stages:
            if st.parallel:
                for branch in st.parallel:  # each branch keeps the order of its own stages
                    connect(sequence([branch]))
                units.append([n for br in st.parallel for n in names(br)])
            elif st.matrix:
                units.append([n for c in st.matrix.stages for n in names(c)])
            elif st.stages:
                units += sequence(st.stages)
            else:
                units.append([st.name])
        return units

    if ir is not None:
        connect(sequence(ir.stages))
    count: dict[str, int] = defaultdict(int)
    for stage in (ir.stages if ir else []):
        for n in names(stage):
            count[n] += 1
    return sorted((a, b) for a, b in pairs if a != b and count[a] == 1 and count[b] == 1
                  and "${" not in a and "${" not in b)


def order_violations(traces: list[dict[str, Any]], order: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """(before, after) pairs the trace runs in the wrong order: an event of `after` that precedes an event of
    `before`. Pairs with a stage that has no events are skipped."""
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    for i, t in enumerate(traces):
        stage = t.get("stage", "")
        first.setdefault(stage, i)
        last[stage] = i
    return sorted({(a, b) for a, b in order if a in last and b in first and first[b] < last[a]})


def compare(reference: list[dict[str, Any]], candidate: list[dict[str, Any]],
            reference_result: str | None = None, candidate_result: str | None = None,
            concurrent: set[str] | frozenset[str] = frozenset(),
            order: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """Compare per-stage step sequences. Order matters within a stage. Across stages it matters as far as the
    original pipeline fixes it (``order``, see `stage_order`: the candidate may not run a stage before one that
    must precede it); without ``order`` only the per-stage sequences are compared. Steps of a
    ``concurrent`` stage (matrix cells, scripted parallel branches) may interleave too.

    ``verdict`` is equivalent, differs or inconclusive - never ``equivalent`` when the traces cannot show it:
    no events on either side, the two runs ending differently although their traces match (the difference lies
    outside the marker contract), or the Jenkins reference failing on the pipeline's own ``error`` step while the
    candidate did not (trace mode stubs the runtime values that decide such a branch)."""
    ref, cand = by_stage(reference), by_stage(candidate)
    stages = sorted(set(ref) | set(cand))
    rows = []
    matched = total = 0
    for s in stages:
        a, b = ref.get(s, []), cand.get(s, [])
        if a == b:
            status, same = "match", len(a)
        elif s in concurrent and sorted(a) == sorted(b):
            status, same = "reordered", len(a)
        else:
            status = "missing-stage" if not b else ("extra-stage" if not a else "differs")
            same = max(_lcs(a, b), _multiset_overlap(a, b) if s in concurrent else 0)
        matched += same
        total += max(len(a), len(b))
        rows.append({"stage": s, "status": status, "jenkins": a, "gha": b})
    score = round(100.0 * matched / total, 1) if total else 0.0
    misordered = sorted(set(order_violations(candidate, order or [])) - set(order_violations(reference, order or [])))
    for r in rows:
        if r["status"] in ("match", "reordered") and any(r["stage"] in pair for pair in misordered):
            r["status"] = "out-of-order"
    equivalent = all(r["status"] in ("match", "reordered") for r in rows)
    out = {"equivalent": equivalent, "verdict": "equivalent" if equivalent else "differs", "similarity_pct": score,
           "stages": rows, "reference_steps": len(reference), "candidate_steps": len(candidate)}
    if misordered:
        out["order_violations"] = [list(p) for p in misordered]
    ref_out, cand_out = outcome(reference_result), outcome(candidate_result)
    if not reference and not candidate:
        reason = "no trace events on either side"
    elif equivalent and candidate_result is not None and _ended_differently(ref_out, cand_out):
        reason = (f"traces match but the runs ended differently (Jenkins {reference_result}, candidate "
                  f"{candidate_result}): the difference lies outside the traced steps")
    else:
        reason = None
    if reason:
        out.update(equivalent=False, verdict="inconclusive", inconclusive={"reason": reason, "stage": None})
        return out
    stop = None if equivalent or reference_result != "FAILURE" else _own_error_stop(reference, cand, rows)
    if stop:
        out.update(verdict="inconclusive", inconclusive=stop)
    return out


def _ended_differently(ref: str, cand: str) -> bool:
    # GitHub has no UNSTABLE: the converted `unstable` step only warns, so an unstable reference ends successfully
    def norm(o: str) -> str:
        return "success" if o == "unstable" else o
    return norm(ref) != norm(cand)


def _own_error_stop(reference: list[dict[str, Any]], cand: dict[str, list[str]],
                    rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    i = next((i for i, t in enumerate(reference) if t.get("step") == "error"), None)
    if i is None:
        return None
    stage = reference[i].get("stage", "")
    if "error" in cand.get(stage, []):
        return None  # the candidate failed the same way: a real comparison
    status = {r["stage"]: r["status"] for r in rows}
    before = [s for s in dict.fromkeys(t.get("stage", "") for t in reference[:i]) if s != stage]
    return {"stage": stage, "stages_before": before,
            "stages_before_equivalent": all(status.get(s) in ("match", "reordered") for s in before),
            "reason": "Jenkins stopped on the pipeline's own error() - trace mode stubs the runtime values "
                      "that decide it"}


def _multiset_overlap(a: list[str], b: list[str]) -> int:
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    return sum(min(ca[k], cb[k]) for k in ca)


def _lcs(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]
