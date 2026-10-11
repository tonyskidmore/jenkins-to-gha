"""Structural invariants of generated workflows (j2gha/validate/contexts.py), checked on hand-made bad workflows,
on the committed corpus, and on a cross product of the constructs the converter combines (the review's point: fixes
were tested alone, their interactions were not)."""

import itertools
import json
import re
from pathlib import Path

import yaml

from j2gha.convert.generator import convert
from j2gha.ir import Agent, Condition, EnvValue, Matrix, Parameter, Pipeline, Stage, Step, When
from j2gha.validate.contexts import context_checks
from j2gha.validate.static import policy_checks

ROOT = Path(__file__).resolve().parent.parent


def rules(wf):
    return sorted({f["rule"] for f in context_checks(wf)})


def job(**kw):
    return {"runs-on": "ubuntu-latest", "steps": [{"run": "true"}], **kw}


# ------------------------------------------------------------------------------------ each rule fires on its bug
def test_job_if_may_not_read_env_or_steps():
    assert rules({"jobs": {"a": job(), "b": job(needs="a", **{"if": "env.X == 'y'"})}}) == ["job-if-context"]
    assert rules({"jobs": {"a": job(), "b": job(needs="a", **{"if": "steps.s1.outputs.run == 'true'"})}}) == \
        ["job-if-context"]
    # text inside a string literal is not code; needs/github/vars/inputs are fine
    assert rules({"jobs": {"a": job(), "b": job(needs="a", **{"if": "needs.a.result == 'env.X' && github.ref != ''"})}}) == []


def test_needs_references_must_name_a_direct_need():
    wf = {"jobs": {"a": job(outputs={"x": "1"}), "b": job(needs="a"),
                   "c": job(needs="b", steps=[{"run": "true", "if": "needs.a.outputs.x == '1'"}])}}
    assert rules(wf) == ["needs-reference"]
    wf["jobs"]["c"]["needs"] = ["a", "b"]
    assert rules(wf) == []
    assert rules({"jobs": {"a": job(), "b": job(needs="a", **{"if": "always() && contains(needs.*.result, 'failure')"})}}) == []


def test_a_step_if_reads_its_own_env_but_an_env_entry_cannot_read_a_sibling():
    """Verified on GitHub (self-hosted run 37643778302): `if:` sees the step's own `env:`; an `env:` entry that reads
    another entry of the same mapping gets ''."""
    own = {"run": "true", "env": {"TARGET": "prod"}, "if": "env.TARGET == 'prod'"}
    assert rules({"jobs": {"a": job(steps=[own])}}) == []
    sibling = {"run": "true", "env": {"A": "x", "B": "${{ env.A }}"}}
    assert rules({"jobs": {"a": job(steps=[sibling])}}) == ["step-env-scope"]
    # defined at workflow or job level, the same name is visible to the mapping
    assert rules({"env": {"A": "x"}, "jobs": {"a": job(steps=[{"run": "true", "env": {"A": "y", "B": "${{ env.A }}"}}])}}) == []


def test_unknown_functions_are_reported():
    assert rules({"jobs": {"a": job(steps=[{"run": "true", "if": "substring(env.X, 1) == 'a'"}])}}) == ["unknown-function"]
    assert rules({"jobs": {"a": job(steps=[{"run": "true", "env": {"V": "${{ toUpper(github.ref) }}"}}])}}) == \
        ["unknown-function"]


def test_a_job_after_a_skippable_job_needs_a_status_function():
    skipped = job(**{"if": "needs.gate.outputs.run == 'true'"}, needs="gate")
    wf = {"jobs": {"gate": job(outputs={"run": "x"}), "deploy": skipped, "after": job(needs="deploy")}}
    assert rules(wf) == ["skip-propagation"]
    wf["jobs"]["after"]["if"] = "!failure() && !cancelled()"
    assert rules(wf) == []
    wf["jobs"]["post"] = job(needs=["deploy"], **{"if": "always()"})
    assert rules(wf) == []


def test_a_gate_consumer_must_not_evaluate_the_gates_condition_again():
    gate = job(outputs={"run": "${{ steps.e.outputs.run }}"},
               steps=[{"id": "e", "name": "Deploy: enter stage", "run": "true", "if": "env.FLAG == 'yes'"}])
    ok = job(needs="gate", steps=[{"name": "Deploy: enter stage", "run": "true",
                                   "if": "needs.gate.outputs.run == 'true'"}])
    assert rules({"jobs": {"gate": gate, "stage": ok}}) == []
    bad = job(needs="gate", steps=[{"name": "Deploy: enter stage", "run": "true", "if": "env.FLAG == 'yes'"}])
    assert rules({"jobs": {"gate": gate, "stage": bad}}) == ["decision-reevaluated"]
    # any step of a job that consumes the gate, e.g. a stage's post action
    post = job(needs=["gate"], steps=[{"name": "post: echo", "run": "true", "if": "(always()) && (env.FLAG == 'yes')"}])
    assert rules({"jobs": {"gate": gate, "post": post}}) == ["decision-reevaluated"]
    # another stage may share the condition text
    other = job(needs="x", steps=[{"name": "Other: enter stage", "run": "true", "if": "env.FLAG == 'yes'"}])
    assert rules({"jobs": {"x": job(), "gate": gate, "other": other}}) == []


def test_the_checks_are_part_of_the_policy_findings():
    text = yaml.safe_dump({"permissions": {"contents": "read"}, "on": "push",
                           "jobs": {"a": job(**{"timeout-minutes": 5, "if": "env.X == '1'"})}})
    result = policy_checks(text)
    assert not result["ok"] and any(f["rule"] == "job-if-context" for f in result["findings"])


# ------------------------------------------------------------------------------------------------------ the corpus
def test_every_committed_workflow_satisfies_the_invariants():
    files = sorted((ROOT / "examples").glob("*/gha/workflow.model.json"))
    assert files, "no committed models"
    for f in files:
        found = context_checks(json.loads(f.read_text()))
        assert not found, (f.parent.parent.name, found[:3])


# ------------------------------------------------------------------------------------------------- cross product
def _body(script_if, extra):
    steps = [Step("echo", args=["start"])]
    if script_if:
        branch = [Step("echo", args=["a"])] + ([Step("echo", args=["b"])] if script_if == "multi" else [])
        steps.append(Step("script", body=[Step("<if>", source="env.STAGE_TARGET == 'prod'", body=branch,
                                               named={"_else": [Step("echo", args=["c"])]} if script_if == "multi" else {})]))
    if extra:
        steps.append(Step("writeFile", named={"file": "out.txt", "text": "v=${TARGET}"}, dynamic=True))
        steps = [Step("dir", args=["sub"], body=steps)]
    return steps


def _pipeline(kind, inp, when, stage_env, script_if, extra, post, computed_env, stage_post, subdir, first):
    body = _body(script_if, extra)
    cond = When([Condition("expression", text="env.FLAG == 'yes'")], before_input=inp == "before") if when else None
    kw = dict(when=cond, input={"message": "Go?"} if inp else None,
              environment={"STAGE_TARGET": EnvValue("literal", "prod")} if stage_env else {},
              post={"always": [Step("echo", args=["stage post"])]} if stage_post else {})
    if kind == "plain":
        st = Stage("Deploy", steps=body, **kw)
    elif kind == "parallel":
        st = Stage("Deploy", parallel=[Stage("A", steps=body), Stage("B", steps=[Step("echo", args=["b"])])], **kw)
    else:
        st = Stage("Deploy", matrix=Matrix(axes={"OS": ["a", "b"]}, stages=[Stage("Cell", steps=body)]), **kw)
    env = {"FLAG": EnvValue("shell", "printf yes")} if computed_env else {"FLAG": EnvValue("literal", "yes")}
    build, after = Stage("Build", steps=[Step("echo", args=["b"])]), Stage("After", steps=[Step("echo", args=["a"])])
    return Pipeline(dialect="declarative", agent=Agent("any"), environment=env,
                    options={"checkoutToSubdirectory": "src"} if subdir else {},
                    parameters=[Parameter("string", "TARGET", default="prod")],
                    stages=[st, build, after] if first else [build, st, after],
                    post={"always": [Step("echo", args=["done"])]} if post else {})


DIMENSIONS = dict(
    kind=("plain", "parallel", "matrix"),
    inp=(None, "after", "before"),
    when=(False, True),
    stage_env=(False, True),
    script_if=(None, "single", "multi"),
    extra=(False, True),
    post=(False, True),
    computed_env=(False, True),
    stage_post=(False, True),
    subdir=(False, True),
    first=(False, True),  # the stage under test is the pipeline's first stage
)


def _combos():
    for values in itertools.product(*DIMENSIONS.values()):
        combo = dict(zip(DIMENSIONS, values, strict=True))
        if combo["inp"] == "before" and not combo["when"]:
            continue  # `beforeInput` orders `when` against `input`: it needs both
        yield combo


def _semantic_findings(wf, combo):
    """Properties the structural rules cannot see, read from the model's `_j2gha` metadata."""
    out = []
    steps = [(jid, st) for jid, job in wf["jobs"].items() for st in job["steps"]]
    # Jenkins' implicit checkout is traced once (by the workflow's first job, whatever kind it is)
    events = [e for _, st in steps for e in st.get("_j2gha", {}).get("trace_events", [])]
    if sum(1 for e in events if e[0] == "Declarative: Checkout SCM") != 1:
        out.append("the implicit checkout event is not emitted exactly once")
    if combo["computed_env"] and sum(1 for e in events if e[1] == "sh") != 1:
        out.append("the pipeline environment's sh event is not emitted exactly once")
    # one checkout layout everywhere
    paths = {st.get("with", {}).get("path") for _, st in steps if st.get("_j2gha", {}).get("role") == "checkout"}
    if len(paths) > 1:
        out.append(f"checkouts disagree on the layout: {paths}")
    # a gated stage's condition is evaluated by its gate job only: none of its jobs (post actions included) repeat it
    if combo["when"] and combo["inp"] == "before":
        out += [f"job '{jid}' step '{st.get('name')}' evaluates the gated condition again" for jid, st in steps
                if not jid.endswith("-gate") and "env.FLAG == 'yes'" in str(st.get("if"))]
    # a decision step runs in the environment of the steps it decides for
    for jid, job in wf["jobs"].items():
        ids = {st["id"]: st for st in job["steps"] if st.get("id")}
        for st in job["steps"]:
            for ref in re.findall(r"steps\.([\w-]+)\.outputs\.taken", st.get("if", "")):
                decision = ids.get(ref)
                if decision and decision["_j2gha"]["kind"] == "if-decision" and \
                        not set(st.get("env") or {}) <= set(decision.get("env") or {}):
                    out.append(f"job '{jid}': decision step lacks the environment of the steps it decides for")
    return out


def test_no_combination_of_constructs_breaks_an_invariant():
    checked, failures = 0, []
    for combo in _combos():
        wf = convert(_pipeline(**combo), "FLAG TARGET STAGE_TARGET")["workflow"]
        found = [f"{f['rule']}: {f['message']}" for f in context_checks(wf)] + _semantic_findings(wf, combo)
        checked += 1
        if found:
            failures.append((combo, found[:2]))
    assert checked > 4000
    assert not failures, f"{len(failures)} of {checked} combinations break an invariant; first: {failures[0]}"
