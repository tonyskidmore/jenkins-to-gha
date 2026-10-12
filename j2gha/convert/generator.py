"""Deterministic IR -> GitHub Actions workflow generation.

Design decisions (see docs/architecture.md):
  * Consecutive stages that share an agent become *one job* (Jenkins stages share a workspace; GHA jobs do not).
    Parallel branches, matrix stages, stages with their own agent and input-gated stages become separate jobs
    chained with `needs`.
  * `when` conditions compile to step-level `if:` against the `env` context (Jenkins `when` is env-based). The
    workflow defines Jenkins-compatible env (BRANCH_NAME, TAG_NAME, CHANGE_ID, BUILD_NUMBER...) at workflow level.
  * Stage `post` blocks use the outcomes of that stage's step ids; pipeline `post` uses job status functions (single
    job) or `needs.*.result` in a final job.
  * Every generated step carries `_j2gha` metadata (Jenkins step, stage, line, traced?) used by the report and by
    the trace/full execution variants. It is stripped from the canonical workflow.yml.
"""

from __future__ import annotations

import copy
import os
import re
import shlex
import textwrap
from dataclasses import dataclass, field
from typing import Any

import yaml

from ..ir import Agent, EnvValue, Pipeline, Stage, Step, literal_scope, resolve_credential_id
from ..trace import IMPLICIT_CHECKOUT_STAGE, PIPELINE_POST_STAGE, TRACED_STEPS, marker_cmd, step_name_key
from . import workspace
from .expressions import PARAM_TYPES, SCRIPT_VARS, STATUS_RANK, bash_condition, translate_groovy, when_expr

ACTIONS = {
    "checkout": "actions/checkout@v4",
    "upload-artifact": "actions/upload-artifact@v4",
    "download-artifact": "actions/download-artifact@v4",
    "setup-java": "actions/setup-java@v4",
    "setup-node": "actions/setup-node@v4",
    "setup-python": "actions/setup-python@v5",
    "setup-go": "actions/setup-go@v5",
    "setup-gradle": "gradle/actions/setup-gradle@v4",
}

POST_ORDER = ["always", "changed", "fixed", "regression", "aborted", "failure", "success", "unstable",
              "unsuccessful", "cleanup"]

JENKINS_ENV = {
    "BRANCH_NAME": "${{ github.head_ref || github.ref_name }}",
    "TAG_NAME": "${{ github.ref_type == 'tag' && github.ref_name || '' }}",
    "CHANGE_ID": "${{ github.event.pull_request.number }}",
    "CHANGE_TARGET": "${{ github.base_ref }}",
    "CHANGE_BRANCH": "${{ github.head_ref }}",
    "CHANGE_AUTHOR": "${{ github.event.pull_request.user.login }}",
    "CHANGE_TITLE": "${{ github.event.pull_request.title }}",
    "CHANGE_URL": "${{ github.event.pull_request.html_url }}",
    "BUILD_NUMBER": "${{ github.run_number }}",
    "BUILD_ID": "${{ github.run_id }}",
    "BUILD_TAG": "gha-${{ github.repository_owner }}-${{ github.event.repository.name }}-${{ github.run_number }}",
    "JOB_NAME": "${{ github.workflow }}",
    "JOB_BASE_NAME": "${{ github.workflow }}",
    "BUILD_URL": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}",
    "GIT_COMMIT": "${{ github.sha }}",
    "GIT_BRANCH": "${{ github.head_ref || github.ref_name }}",
    "GIT_URL": "${{ github.server_url }}/${{ github.repository }}.git",
    "WORKSPACE": "${{ github.workspace }}",
    "NODE_NAME": "${{ runner.name }}",
}
ALWAYS_ENV = ("BRANCH_NAME", "TAG_NAME", "CHANGE_ID")
# Jenkins' git plugin exports these to every step after a checkout, so scripts the pipeline calls may read them even
# when the Jenkinsfile never mentions them: emitted whenever the workflow checks out (C5).
SCM_ENV = ("GIT_COMMIT", "GIT_BRANCH", "GIT_URL")
# Jenkins leaves these unset outside their context (a tag build, a change request); Groovy renders an unset `env.X`
# inside a GString as the string `null`, which the shell form `${X:-null}` reproduces (C2).
NULL_WHEN_UNSET = frozenset({"TAG_NAME", "CHANGE_ID", "CHANGE_TARGET", "CHANGE_BRANCH", "CHANGE_AUTHOR",
                             "CHANGE_TITLE", "CHANGE_URL", "CHANGE_FORK"})
DEFAULT_TIMEOUT = int(os.environ.get("J2GHA_DEFAULT_TIMEOUT", "60"))


@dataclass
class Item:
    """One line of the migration report."""

    jenkins: str
    line: int | None
    stage: str | None
    status: str  # mapped | approximated | manual | dropped
    gha: str
    note: str = ""


@dataclass
class Ctx:
    ir: Pipeline
    source_text: str
    items: list[Item] = field(default_factory=list)
    secrets: dict[str, str] = field(default_factory=dict)  # secret name -> purpose
    notes: list[str] = field(default_factory=list)
    stashes: dict[str, str] = field(default_factory=dict)  # stash name -> artifact root, relative to the stash dir
    stash_allow_empty: set[str] = field(default_factory=set)  # stash names declared `allowEmpty: true`
    runtime_env: list[tuple[str, str]] = field(default_factory=list)  # pipeline env evaluated by the shell
    env_trace: list[list[str]] = field(default_factory=list)  # Jenkins trace events of pipeline env evaluation
    counter: int = 0
    job_ids: set[str] = field(default_factory=set)
    job: str = ""  # job being generated
    var_producers: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # script var -> [(job, step id)]
    assigned: set[str] = field(default_factory=set)  # script variables carried on through $GITHUB_ENV so far
    handoff: dict[str, Any] = field(default_factory=dict)  # the workspace hand-off, for the migration report

    def sid(self, prefix: str = "s") -> str:
        self.counter += 1
        return f"{prefix}{self.counter}"

    def add(self, jenkins: str, line: int | None, stage: str | None, status: str, gha: str, note: str = "") -> None:
        self.items.append(Item(jenkins, line, stage, status, gha, note))

    def secret(self, cred_id: str, suffix: str = "") -> str:
        name = re.sub(r"[^A-Za-z0-9_]", "_", cred_id).upper().strip("_") or "SECRET"
        if name[0].isdigit():
            name = "S_" + name
        if name.startswith("GITHUB_"):
            # GitHub reserves GITHUB_* secret names (secrets.GITHUB_TOKEN is the workflow's own token)
            name = "JENKINS_" + name
        name += suffix
        self.secrets.setdefault(name, f"Jenkins credential '{cred_id}'")
        return name


@dataclass
class Inherit:
    """Context inherited by nested steps (wrappers such as dir/withEnv/withCredentials/timeout)."""

    env: dict[str, str] = field(default_factory=dict)
    working_dir: str | None = None
    cond: str | None = None  # stage/when condition (env-context expression)
    continue_on_error: bool = False
    timeout: int | None = None
    retry: int | None = None
    wrap_image: str | None = None  # run inside `docker run <image>` (dockerfile agents, docker.image().inside, container())
    exports: list[tuple[str, str]] = field(default_factory=list)  # stage env evaluated by the shell before run steps
    inline_depth: int = 0
    stage: str = ""
    shell: str | None = None
    concurrent: bool = False  # inside a scripted `parallel` step: Jenkins interleaves these steps' trace events

    def child(self, **kw: Any) -> "Inherit":
        d = dict(self.__dict__)
        d["env"] = dict(self.env)
        d["exports"] = list(self.exports)
        d.update(kw)
        return Inherit(**d)


# =================================================================================================================
def convert(ir: Pipeline, source_text: str, title: str = "converted pipeline") -> dict[str, Any]:
    """Return {'workflow': <model with _j2gha metadata>, 'report': {...}}."""
    ctx = Ctx(ir=ir, source_text=source_text)
    token = SCRIPT_VARS.set(_dispatch_vars(ir))
    types_token = PARAM_TYPES.set({p.name: p.kind for p in ir.parameters})
    try:
        wf: dict[str, Any] = {"name": f"{title} (j2gha)"}
        wf["on"] = _triggers(ir, ctx)
        wf["permissions"] = {"contents": "read"}
        conc = _concurrency(ir, ctx)
        if conc:
            wf["concurrency"] = conc
        wf["env"] = _workflow_env(ir, ctx)
        wf["defaults"] = {"run": {"shell": "bash"}}
        wf["jobs"] = _jobs(ir, ctx)
        used = repr(wf["jobs"])
        wf["env"].update({k: v for k, v in JENKINS_ENV.items() if k not in wf["env"] and f"env.{k}" in used})
        if _has_checkout(wf["jobs"]):
            wf["env"].update({k: JENKINS_ENV[k] for k in SCM_ENV if k not in wf["env"]})
            # a support detail of the checkout items, not a Jenkins element of its own: listed, never scored
            ctx.add("checkout: SCM environment (" + ", ".join(SCM_ENV) + ")", None, None, "info", "env",
                    "Jenkins' git plugin exports them to every step after a checkout, so called scripts may read "
                    "them; defined at workflow level even when the Jenkinsfile does not")
        _options_items(ir, ctx)
        report = _report(ctx, wf)
    finally:
        SCRIPT_VARS.reset(token)
        PARAM_TYPES.reset(types_token)
    return {"workflow": wf, "report": report}


# ----------------------------------------------------------------------------------------------- workflow level
def _triggers(ir: Pipeline, ctx: Ctx) -> dict[str, Any]:
    on: dict[str, Any] = {"push": {"branches": ["**"]}, "pull_request": None}
    inputs: dict[str, Any] = {}
    for p in ir.parameters:
        spec: dict[str, Any] = {"description": (p.description or p.name)[:120], "required": False}
        status, note = "mapped", ""
        if p.kind == "booleanParam":
            spec["type"] = "boolean"
            spec["default"] = bool(p.default)
        elif p.kind == "choice":
            spec["type"] = "choice"
            spec["options"] = [str(c) for c in p.choices] or ["(none)"]
            spec["default"] = spec["options"][0]
        elif p.kind in ("string", "text"):
            spec["type"] = "string"
            if p.default is not None:
                spec["default"] = str(p.default)
        else:
            spec["type"] = "string"
            status, note = "approximated", f"{p.kind} parameters have no workflow_dispatch equivalent"
            if p.kind == "password":
                note += "; use a secret instead of a password input"
        inputs[p.name] = spec
        ctx.add(f"parameters: {p.kind} {p.name}", p.line, None, status, "on.workflow_dispatch.inputs", note)
    on["workflow_dispatch"] = {"inputs": inputs} if inputs else None
    sched = []
    for t in ir.triggers:
        if t.kind == "cron" and isinstance(t.value, str):
            for spec in [s for s in t.value.splitlines() if s.strip() and not s.strip().startswith("#")]:
                cron, approx = _cron(spec.strip())
                sched.append({"cron": cron})
                ctx.add(f"triggers: cron '{spec.strip()}'", t.line, None, "approximated" if approx else "mapped",
                        f"on.schedule cron '{cron}'", "Jenkins H (hash) replaced with fixed values" if approx else
                        "runs on the default branch only")
        elif t.kind == "pollSCM":
            ctx.add("triggers: pollSCM", t.line, None, "approximated", "on.push", "event-driven instead of polling")
        elif t.kind == "upstream":
            ctx.add(f"triggers: upstream {t.value}", t.line, None, "manual", "on.workflow_run",
                    "name the upstream workflow(s) once migrated")
        else:
            ctx.add(f"triggers: {t.value}", t.line, None, "manual", "-", "unsupported trigger")
    if sched:
        on["schedule"] = sched
    return on


def _cron(spec: str) -> tuple[str, bool]:
    if spec.startswith("@"):
        return {"@daily": "0 0 * * *", "@midnight": "0 0 * * *", "@hourly": "0 * * * *",
                "@weekly": "0 0 * * 0", "@monthly": "0 0 1 * *", "@yearly": "0 0 1 1 *",
                "@annually": "0 0 1 1 *"}.get(spec, "0 0 * * *"), True
    fields = spec.split()
    approx = False
    out = []
    defaults = [7, 3, 1, 1, 0]
    for i, f in enumerate(fields[:5]):
        if "H" in f:
            approx = True
            f = re.sub(r"H\((\d+)-\d+\)", r"\1", f)
            f = f.replace("H/", "*/").replace("H", str(defaults[i]))
        out.append(f)
    return " ".join(out), approx


def _concurrency(ir: Pipeline, ctx: Ctx) -> dict[str, Any] | None:
    opt = ir.options.get("disableConcurrentBuilds")
    if not opt:
        return None
    abort = isinstance(opt, dict) and opt.get("abortPrevious")
    ctx.add("options: disableConcurrentBuilds", None, None, "mapped", "concurrency",
            "GHA keeps only the latest pending run per group")
    return {"group": "${{ github.workflow }}-${{ github.ref }}", "cancel-in-progress": bool(abort)}


def _workflow_env(ir: Pipeline, ctx: Ctx) -> dict[str, Any]:
    env: dict[str, Any] = {}
    text = ctx.source_text
    for k, v in JENKINS_ENV.items():
        if k in ALWAYS_ENV or re.search(r"\b" + k + r"\b", text):
            env[k] = v
    for p in ir.parameters:
        default = p.default if p.default is not None else (p.choices[0] if p.choices else "")
        if isinstance(default, bool):
            default = str(default).lower()
        # the default is chosen by the event alone: `dispatch && input || default` would swap an empty input for it
        env[p.name] = (f"${{{{ github.event_name != 'workflow_dispatch' && "
                       f"'{str(default).replace(chr(39), chr(39) * 2)}' || format('{{0}}', inputs.{p.name}) }}}}")
    env.update(_env_block(ir.environment, ctx, None, runtime=ctx.runtime_env, trace=ctx.env_trace))
    return env


def _env_block(env: dict[str, EnvValue], ctx: Ctx, stage: str | None,
               runtime: list[tuple[str, str]] | None = None, trace: list[list[str]] | None = None) -> dict[str, str]:
    """Static env -> returned dict. Values needing runtime evaluation (GStrings referencing other variables,
    `sh(returnStdout: true)`) are appended to ``runtime`` as (name, shell-expression)."""
    out: dict[str, str] = {}
    for k, v in env.items():
        if trace is not None and v.kind == "shell":
            trace.append([stage or "", "sh"])
        if v.kind == "call":
            if trace is not None:
                trace.append([stage or "", str(v.value)])
            out[k] = f"TODO-j2gha: {v.value}()"
            ctx.add(f"environment {k} = {v.value}(...)", v.line, stage, "manual", "env",
                    "value computed by a library/plugin function - compute in a step and write to $GITHUB_ENV")
            continue
        if runtime is not None and v.kind in ("expression", "shell"):
            shell_val = _runtime_value(v)
            if shell_val is not None:
                runtime.append((k, shell_val))
                ctx.add(f"environment {k}", v.line, stage, "approximated", "evaluated by shell at runtime",
                        "pipeline-level: written to $GITHUB_ENV; stage-level: exported before each run step")
                continue
        if v.kind == "literal":
            out[k] = str(v.value).lower() if isinstance(v.value, bool) else str(v.value)
            ctx.add(f"environment {k}", v.line, stage, "mapped", "env")
        elif v.kind == "credentials":
            sec = ctx.secret(v.credential_id or k)
            out[k] = f"${{{{ secrets.{sec} }}}}"
            if re.search(r"\b" + k + r"_(USR|PSW)\b", ctx.source_text):
                out[f"{k}_USR"] = f"${{{{ secrets.{ctx.secret(v.credential_id or k, '_USR')} }}}}"
                out[f"{k}_PSW"] = f"${{{{ secrets.{ctx.secret(v.credential_id or k, '_PSW')} }}}}"
            ctx.add(f"environment {k} = credentials('{v.credential_id}')", v.line, stage, "mapped",
                    f"env from secrets.{sec}", "create the repository/environment secret")
        else:
            expr = _groovy_to_shell_value(str(v.value))
            if expr is not None:
                out[k] = expr
                ctx.add(f"environment {k}", v.line, stage, "approximated", "env",
                        f"Groovy expression `{str(v.value)[:60]}` translated")
            else:
                out[k] = f"TODO-j2gha: {str(v.value)[:80]}"
                ctx.add(f"environment {k}", v.line, stage, "manual", "env",
                        f"runtime Groovy expression `{str(v.value)[:60]}` - compute in a step and write to $GITHUB_ENV")
    return out


def _runtime_value(v: EnvValue) -> str | None:
    if v.kind == "shell":
        cmd, _ = _groovy_text_to_shell(str(v.value or ""))
        cmd, _shell = _shell_for(cmd)
        return f"$({cmd})" if cmd else None
    text = str(v.value or "")
    if re.fullmatch(r"[^${}]*(\$\{(env\.|params\.)?[A-Za-z_][A-Za-z0-9_]*\}[^${}]*)+", text):
        return re.sub(r"\$\{(?:env\.|params\.)?([A-Za-z_][A-Za-z0-9_]*)\}", r"${\1}", text)
    return None


def _groovy_to_shell_value(expr: str) -> str | None:
    """`"${env.BUILD_NUMBER}-x"` style GStrings -> GHA expression strings."""
    s = expr.strip()
    if re.fullmatch(r"[\w.\-/:@ ]*(\$\{(env\.|params\.)?[A-Z_][A-Z0-9_]*\}[\w.\-/:@ ]*)+", s):
        return re.sub(r"\$\{(?:env\.|params\.)?([A-Z_][A-Z0-9_]*)\}",
                      lambda m: "${{ env." + m.group(1) + " }}" if m.group(1) not in JENKINS_ENV
                      else JENKINS_ENV[m.group(1)], s)
    return None


# ----------------------------------------------------------------------------------------------------- jobs
@dataclass
class JobPlan:
    id: str
    name: str
    stages: list[tuple[Stage, list[str]]] = field(default_factory=list)  # stage + path names
    agent: Agent | None = None
    kind: str = "steps"  # steps | matrix | parallel-branch | stage-input | stage-gate | stage-post
    matrix_stage: Stage | None = None
    needs: list[str] = field(default_factory=list)
    environment: str | None = None
    first_with_agent: bool = False  # the job's stage has its own agent -> Jenkins checks out in that stage
    implicit_checkout: bool = False  # Jenkins' pipeline-level "Declarative: Checkout SCM" maps to this job
    checkout_stage: str = IMPLICIT_CHECKOUT_STAGE
    parent: Stage | None = None  # parallel parent of a branch; fan-out stage of a stage-input/stage-post job
    first_branch: bool = False
    decision: str | None = None  # `beforeInput` stage: the stage-gate job whose `run` output decides this job
    input_split: bool = False  # the stage's input step lives in its own approval job (parallel/matrix stages)


def _job_id(ctx: Ctx, name: str) -> str:
    base = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")[:40] or "job"
    if base[0].isdigit():
        base = "j-" + base
    jid, i = base, 2
    while jid in ctx.job_ids:
        jid, i = f"{base}-{i}", i + 1
    ctx.job_ids.add(jid)
    return jid


def _plan(ir: Pipeline, ctx: Ctx) -> list[JobPlan]:
    plans: list[JobPlan] = []
    prev: list[str] = []
    top_agent = ir.agent if ir.agent and ir.agent.kind != "none" else None
    current: JobPlan | None = None

    def flush():
        nonlocal current, prev
        if current and current.stages:
            plans.append(current)
            prev = [current.id]
        current = None

    for st in ir.stages:
        own_agent = st.agent if st.agent and st.agent.kind not in ("none", "inherit") else None
        if own_agent is not None and current is not None and current.agent is own_agent and not st.input \
                and not st.parallel and not st.matrix:
            # stages of one scripted node {} share its agent object (and workspace): one job
            current.stages.append((st, [st.name]))
            if st.name:
                current.name = f"{current.name}, {st.name}" if len(current.name) < 80 else current.name
            continue
        needs_own_job = bool(st.parallel or st.matrix or own_agent or st.input)
        if needs_own_job:
            flush()
            if st.parallel:
                cond, status = when_expr(st.when)
                if st.when:
                    ctx.add(f"stage '{st.name}' when", _when_line(st), st.name, status, f"if: {cond}", _when_note(status))
                prev, gate_id = _stage_input_plan(st, ctx, plans, prev, ir)
                branch_ids = []
                for i, br in enumerate(st.parallel):
                    jp = JobPlan(id=_job_id(ctx, f"{st.name}-{br.name}"), name=f"{st.name} / {br.name}",
                                 stages=[(br, [st.name, br.name])], agent=br.agent or top_agent,
                                 kind="parallel-branch", needs=prev + ([gate_id] if gate_id else []), parent=st,
                                 first_branch=i == 0, decision=gate_id)
                    jp.first_with_agent = br.agent is not None and br.agent.kind not in ("none",)
                    jp.checkout_stage = br.name
                    plans.append(jp)
                    branch_ids.append(jp.id)
                if st.fail_fast or ir.options.get("parallelsAlwaysFailFast"):
                    ctx.add(f"stage '{st.name}' failFast", st.line, st.name, "approximated", "-",
                            "GHA cannot cancel sibling jobs outside a matrix; consider strategy.fail-fast")
                # Jenkins' branches (and later stages) share one workspace; GHA jobs do not. The converter cannot
                # know which files a branch reads, so it cannot establish that an explicit hand-off covers them
                ctx.add(f"stage '{st.name}' parallel ({len(st.parallel)} branches)", st.line, st.name,
                        "approximated", "parallel jobs with needs", _split_note(ir, st))
                # later stages need every branch (and the stage post job, which runs whatever the branches' result)
                prev = branch_ids + _stage_post_plan(st, ctx, plans, branch_ids, gate_id)
                continue
            if st.matrix:
                prev, gate_id = _stage_input_plan(st, ctx, plans, prev, ir)
                jp = JobPlan(id=_job_id(ctx, st.name), name=st.name, stages=[(st, [st.name])],
                             agent=st.matrix.agent or st.agent or top_agent, kind="matrix", matrix_stage=st,
                             needs=prev + ([gate_id] if gate_id else []), decision=gate_id)
                jp.first_with_agent = (st.matrix.agent or st.agent) is not None
                jp.checkout_stage = st.name
                plans.append(jp)
                prev = [jp.id] + _stage_post_plan(st, ctx, plans, [jp.id], gate_id)
                continue
            jp = JobPlan(id=_job_id(ctx, st.name or "main"), name=st.name or "main", stages=[(st, [st.name])],
                         agent=st.agent if st.agent and st.agent.kind != "none" else top_agent, needs=list(prev))
            jp.first_with_agent = st.agent is not None and st.agent.kind not in ("none",)
            jp.checkout_stage = st.name
            if st.input and _input_after_when(st):
                # `beforeInput true`: the stage job itself carries the protected environment, so its environment
                # secrets stay available; a gate job decides `when` first, and a skipped job asks nobody
                gate = _gate_plan(st, ctx, plans, prev, ir)
                jp.needs = list(prev) + [gate.id]
                jp.decision = gate.id
                jp.environment = re.sub(r"[^A-Za-z0-9_-]", "-", st.name)[:60]
                ctx.add(f"stage '{st.name}' input", st.input.get("line"), st.name, "approximated",
                        f"job environment '{jp.environment}'",
                        "configure required reviewers on the environment; input parameters are not supported")
                plans.append(jp)
                prev = [jp.id]
            elif st.input:
                jp.environment = re.sub(r"[^A-Za-z0-9_-]", "-", st.name)[:60]
                ctx.add(f"stage '{st.name}' input", st.input.get("line"), st.name, "approximated",
                        f"job environment '{jp.environment}'",
                        "configure required reviewers on the environment; input parameters are not supported")
                plans.append(jp)
                prev = [jp.id]
            else:
                current = jp  # later stages on the same (scripted node) agent object join it
            continue
        if current is None:
            current = JobPlan(id=_job_id(ctx, st.name or "main"), name=st.name or "main", agent=top_agent,
                              needs=list(prev))
            current.first_with_agent = False  # the implicit pipeline checkout is assigned to plans[0] below
        elif current.agent is not top_agent:
            flush()  # a stage without its own agent runs on the pipeline agent, not the previous stage's
            current = JobPlan(id=_job_id(ctx, st.name or "main"), name=st.name or "main", agent=top_agent,
                              needs=list(prev))
        elif st.name:
            current.name = f"{current.name}, {st.name}" if len(current.name) < 80 else current.name
        current.stages.append((st, [st.name]))
    flush()
    if not plans:
        plans.append(JobPlan(id=_job_id(ctx, "build"), name="build", agent=top_agent))
    if plans and top_agent is not None and not ir.options.get("skipDefaultCheckout"):
        plans[0].implicit_checkout = True
    return plans


def _split_note(ir: Pipeline, st: Stage) -> str:
    if _handoff_enabled(ir) and any(_in_pipeline_workspace(br.agent, ir.agent) for br in st.parallel):
        return ("branches run as separate jobs: the pipeline workspace is handed on to them and from them to later "
                "stages (j2gha-ws-* artifacts), but branches running at the same time do not see each other's files, "
                "and a file two branches write takes the later branch's version")
    # Jenkins' branches (and later stages) share one workspace; GHA jobs do not. The converter cannot know which files
    # a branch reads, so it cannot establish that an explicit hand-off covers them
    return ("branches and later stages no longer share the workspace: files made by earlier stages are not available"
            + (" except through the pipeline's stash/artifact steps - check that they cover every file the branches "
               "read" if _hands_off_files(ir.stages) else " (add stash/unstash or artifacts)"))


def _input_after_when(st: Stage) -> bool:
    return bool(st.input and st.when and st.when.before_input)


def _gate_plan(st: Stage, ctx: Ctx, plans: list[JobPlan], prev: list[str], ir: Pipeline) -> JobPlan:
    """The job that decides a `beforeInput` stage's `when` once, before any protected environment is entered. Every
    job of the stage consumes its output; none evaluates the condition again."""
    gate = JobPlan(id=_job_id(ctx, f"{st.name}-gate"), name=f"{st.name} (when)", kind="stage-gate",
                   needs=list(prev), parent=st)
    plans.append(gate)
    ctx.add(f"stage '{st.name}' beforeInput", st.line, st.name, "approximated", f"gate job '{gate.id}'",
            "`when` is decided in a gate job " + ("(in the restored pipeline workspace)" if _handoff_enabled(ir) and
                                                  _in_pipeline_workspace(st.agent, ir.agent) else "(in a fresh checkout)")
            + " so a skipped stage asks for no approval")
    return gate


def _stage_input_plan(st: Stage, ctx: Ctx, plans: list[JobPlan], prev: list[str],
                      ir: Pipeline) -> tuple[list[str], str | None]:
    """A parallel/matrix stage's `input` is answered once before the fan-out: an approval job the fan-out needs.
    Returns the jobs the fan-out depends on and the gate job id (`beforeInput`), which it must also depend on.
    The approval job is the only protected job: environment secrets are not available to the branch jobs."""
    if not st.input:
        return prev, None
    gate = _gate_plan(st, ctx, plans, prev, ir) if _input_after_when(st) else None
    jp = JobPlan(id=_job_id(ctx, f"{st.name}-input"), name=f"{st.name} (input)", kind="stage-input",
                 needs=[gate.id] if gate else list(prev), parent=st, decision=gate.id if gate else None)
    jp.environment = re.sub(r"[^A-Za-z0-9_-]", "-", st.name)[:60]
    ctx.add(f"stage '{st.name}' input", st.input.get("line"), st.name, "approximated",
            f"approval job (environment '{jp.environment}')",
            "configure required reviewers on the environment; input parameters are not supported; environment "
            "secrets are not available to the branch jobs")
    plans.append(jp)
    return [jp.id], gate.id if gate else None


def _stage_post_plan(st: Stage, ctx: Ctx, plans: list[JobPlan], needs: list[str],
                     gate_id: str | None = None) -> list[str]:
    """A parallel/matrix stage's own `post` runs once after the fan-out: a fan-in job."""
    if not st.post:
        return []
    jp = JobPlan(id=_job_id(ctx, f"{st.name}-post"), name=f"{st.name} (post)", kind="stage-post",
                 needs=list(needs) + ([gate_id] if gate_id else []), parent=st, decision=gate_id)
    plans.append(jp)
    return [jp.id]


def _jobs(ir: Pipeline, ctx: Ctx) -> dict[str, Any]:
    plans = _plan(ir, ctx)
    # jobs a `beforeInput` gate can skip (a stage's post job always runs: its steps are conditioned instead)
    skippable = {jp.id for jp in plans if jp.decision and jp.kind != "stage-post"}
    jobs: dict[str, Any] = {}
    timeout = (ir.options.get("timeout") or {}).get("minutes") if isinstance(ir.options.get("timeout"), dict) else None
    for jp in plans:
        ctx.job = jp.id
        if jp.kind == "stage-input":
            jobs[jp.id] = _stage_input_job(jp, ctx, timeout or DEFAULT_TIMEOUT, skippable, ir, first=not jobs)
            continue
        if jp.kind == "stage-gate":
            jobs[jp.id] = _stage_gate_job(jp, ctx, timeout or DEFAULT_TIMEOUT, ir, skippable, first=not jobs)
            continue
        if jp.kind == "stage-post":
            st = jp.parent
            # a gated stage's post actions follow the gate's decision, like the stage's own jobs
            jobs[jp.id] = _fanin_post_job(st.post, ctx, jp.needs, st.name, _decided(jp) or when_expr(st.when)[0], ir.agent,
                                          f"stage '{st.name}' post")
            jobs[jp.id]["timeout-minutes"] = timeout or DEFAULT_TIMEOUT
            continue
        job: dict[str, Any] = {"name": jp.name}
        if jp.needs:
            job["needs"] = jp.needs if len(jp.needs) > 1 else jp.needs[0]
        runs_on, container, wrap_image, setup_steps = _agent(jp.agent, ctx, jp.name)
        job["runs-on"] = runs_on
        if cond := _job_condition(jp, skippable):
            job["if"] = cond
        if jp.environment:
            job["environment"] = jp.environment
        if container:
            job["container"] = container
        job["timeout-minutes"] = timeout or DEFAULT_TIMEOUT
        steps: list[dict[str, Any]] = []
        inherit = Inherit(wrap_image=wrap_image)
        scope: list[dict[str, Any]] = []
        if jp.kind == "parallel-branch" and jp.parent is not None:
            inherit, scope = _parent_scope(jp.parent, ctx, inherit, jp.first_branch, _decided(jp))
        entry = next((x for x in scope if x["_j2gha"]["kind"] == "stage-entry"), None)
        if entry is not None:
            steps.append(entry)  # the parallel stage's `when` decides before any branch allocates its agent
        # implicit checkout (Declarative does `checkout scm` when an agent is allocated, unless skipDefaultCheckout;
        # a scripted node {} never checks out on its own)
        skip_co = bool(ir.options.get("skipDefaultCheckout")) or ir.dialect != "declarative"
        events = []
        if jp.implicit_checkout and not skip_co:
            events.append([IMPLICIT_CHECKOUT_STAGE, "checkout"])
        if jp.first_with_agent and not skip_co:
            events.append([jp.checkout_stage, "checkout"])
        if jp.kind == "matrix" and not skip_co:
            # matrix inner stages with their own agent check out again in every cell
            events += [[c.name, "checkout"] for c in jp.matrix_stage.matrix.stages
                       if c.agent and c.agent.kind not in ("none",)]
        co = _checkout_step(ir, events)
        if entry is not None:
            co["if"] = _gate(entry)
        if not ir.options.get("skipDefaultCheckout") or any(_uses_checkout(s) for s, _ in jp.stages):
            steps.append(co)
        steps += setup_steps
        env_step = _pipeline_env_step(ctx, first=not jobs)
        if env_step:
            steps.append(env_step)
        cell_tools = jp.matrix_stage.matrix.tools if jp.kind == "matrix" else {}
        steps += _tools_steps({**ir.tools, **{k: v for s, _ in jp.stages for k, v in s.tools.items()}, **cell_tools},
                              ctx)
        steps += [x for x in scope if x is not entry]
        if jp.kind == "matrix":
            st = jp.matrix_stage
            job.update(_matrix_strategy(st, ctx))
            # axis values are env vars in Jenkins; job-level env makes them visible to step `if:` conditions
            job["env"] = {k: f"${{{{ matrix.{k} }}}}" for k in st.matrix.axes}
            if st.matrix.input:
                job["environment"] = re.sub(r"[^A-Za-z0-9_-]", "-", st.name)[:60]
                ctx.add(f"matrix '{st.name}' input", st.matrix.input.get("line"), st.name, "approximated",
                        f"job environment '{job['environment']}' (every cell)",
                        "configure required reviewers on the environment; input parameters are not supported")
            # the stage's own input and post run once around the fan-out (stage-input / stage-post jobs)
            steps += _unique_matrix_artifacts(_stage_steps(st, ctx, inherit, [st.name], with_input=False,
                                                           with_post=False, decided=_decided(jp)),
                                            list(st.matrix.axes))
        else:
            for st, path in jp.stages:
                steps += _stage_steps(st, ctx, inherit, path, decided=_decided(jp) if jp.kind == "steps" else None)
        if len(plans) == 1:
            steps += _pipeline_post_single(ir, ctx, inherit)
        job["steps"] = steps or [{"name": "No steps", "run": "true", "_j2gha": {"kind": "noop", "trace": False}}]
        jobs[jp.id] = job
    post_id = None
    if len(plans) > 1 and ir.post:
        post_id = _job_id(ctx, "post")
        jobs[post_id] = _fanin_post_job(ir.post, ctx, list(jobs.keys()), _post_stage(ir), None, ir.agent, "post",
                                        restores=_handoff_enabled(ir))
        jobs[post_id]["timeout-minutes"] = timeout or DEFAULT_TIMEOUT
    if _handoff_enabled(ir):
        _workspace_handoff(jobs, plans, ir, post_id, ctx)
    if not timeout:
        ctx.add("(no pipeline timeout)", None, None, "approximated", f"timeout-minutes: {DEFAULT_TIMEOUT}",
                "explicit job timeout added (GitHub's default is 360 minutes); set J2GHA_DEFAULT_TIMEOUT to change")
    _wire_script_vars(jobs, ctx)
    return jobs


# ------------------------------------------------------------------------------------------- workspace hand-off
def _handoff_enabled(ir: Pipeline) -> bool:
    """Jenkins runs every stage without an agent of its own in the pipeline agent's one workspace; the converted jobs
    hand that workspace on (Phase 4, P4.3). Off with J2GHA_WORKSPACE_HANDOFF=0, with no pipeline agent (`agent none`:
    every stage has its own workspace) and for non-Linux pipeline agents (not generated yet)."""
    top = ir.agent
    return (os.environ.get("J2GHA_WORKSPACE_HANDOFF", "1") != "0" and top is not None
            and top.kind not in ("none", "unknown") and _linux_agent(top))


def _linux_agent(agent: Agent) -> bool:
    lab = (agent.label or "").lower() if agent.kind == "label" else ""
    return not any(x in lab for x in ("win", "mac", "osx", "darwin", "ios"))


def _in_pipeline_workspace(agent: Agent | None, top: Agent | None) -> bool:
    """Does a stage on `agent` run in the pipeline agent's workspace? (No agent of its own, or `reuseNode true`.)"""
    return agent is None or agent is top or agent.kind in ("none", "inherit") or agent.reuse_node


def _workspace_handoff(jobs: dict[str, Any], plans: list[JobPlan], ir: Pipeline, post_id: str | None,
                       ctx: Ctx) -> None:
    """Which jobs share the pipeline workspace (convert.workspace plans and generates the hand-off itself).

    *Producers* change the workspace and hand it on: ordinary stage jobs, parallel branches and a parallel/matrix
    stage's post job, when they run on the pipeline agent. A matrix job hands on each cell's changes instead of a
    workspace (up to 256 cells: a *delta* producer, convert.workspace); one with no producer before it starts from
    the checkout, so its cells' changes are not handed on (reported). *Consumers* start from it instead of a
    checkout: producers, matrix cells, `beforeInput` gate jobs and the pipeline post job."""
    top = ir.agent
    by_id = {jp.id: jp for jp in plans}

    def runs_here(jid: str) -> bool:
        ro = jobs[jid].get("runs-on")
        return isinstance(ro, str) and ro.startswith("ubuntu")

    def shares(jp: JobPlan) -> bool:
        if jp.kind in ("stage-gate", "stage-post"):
            return _in_pipeline_workspace(jp.parent.agent if jp.parent else None, top)
        return jp.kind != "stage-input" and _in_pipeline_workspace(jp.agent, top)

    matrices = {jp.id for jp in plans if jp.kind == "matrix" and shares(jp) and runs_here(jp.id)}
    producers = {jp.id for jp in plans if jp.kind in ("steps", "parallel-branch", "stage-post") and shares(jp)
                 and runs_here(jp.id)} | matrices
    consumers = {jp.id for jp in plans if jp.kind != "stage-input" and shares(jp) and runs_here(jp.id)}
    if post_id and runs_here(post_id):
        consumers.add(post_id)
    needs = {jid: list(by_id[jid].needs) if jid in by_id else [j for j in jobs if j != jid] for jid in jobs}
    hp = workspace.plan(list(jobs), needs, producers, consumers, deltas=matrices)
    producers = (producers - matrices) | hp.deltas  # a matrix the plan could not hand on stays a consumer only
    for jid in sorted(matrices - hp.deltas, key=list(jobs).index):
        ctx.add(f"matrix workspace of '{jid}'", None, None, "approximated", "cells' changes not handed on",
                "no job hands a workspace on before the matrix (it starts from the checkout): later jobs do not see "
                "what its cells wrote")
    if hp.restores:
        ctx.handoff = {"handed_on": sorted(hp.handed_on & producers, key=list(jobs).index),
                       "merged": sorted(hp.mergeable & hp.handed_on, key=list(jobs).index),
                       "restored_by": list(hp.restores)}
        for key, ids in (("matrix", hp.deltas), ("matrix_not_handed_on", matrices - hp.deltas)):
            if ids:
                ctx.handoff[key] = sorted(ids, key=list(jobs).index)
    images = {_container_image(jobs[j]) for j in [*hp.restores, *hp.handed_on]} - {None}
    for image in sorted(i for i in images if re.search(r"alpine|busybox", i, re.I)):
        ctx.add(f"workspace hand-off in container '{image}'", None, None, "manual", "bash, GNU tar/findutils/coreutils",
                "the image looks busybox/Alpine-based: the hand-off steps need bash and GNU tools and would fail. Use a "
                "Debian/Ubuntu-based image, or convert with J2GHA_WORKSPACE_HANDOFF=0 and hand files on with "
                "stash/unstash")
    for jid, r in hp.restores.items():
        if r.dropped:
            ctx.add(f"workspace hand-off into '{jid}'", None, None, "approximated", "download-artifact",
                    f"{r.dropped} fallback workspace(s) not generated (limit {workspace.MAX_HANDOFF_FALLBACKS}): if the "
                    "nearest jobs were skipped, an older workspace may be restored")
    for jid in jobs:
        steps = jobs[jid]["steps"]
        restore = workspace.restore_steps(hp.restores[jid], ACTIONS["download-artifact"]) if jid in hp.restores else []
        for st in steps if restore else []:
            meta = st.get("_j2gha") or {}
            if meta.get("role") == "checkout" and not meta.get("trace_events"):
                # the restored workspace replaces the checkout (Jenkins does not check out again in it)
                st["if"] = _and(st.get("if"), f"steps.{workspace.RESTORE_ID}.outputs.restored != 'true'")
        steps[:] = [*restore, *steps]  # first: a stage-entry step may read files (`fileExists`) to decide `when`
        if jid not in producers or jid not in hp.handed_on:  # only a workspace some job restores
            continue
        if jid in hp.mergeable or jid in hp.deltas:
            # the snapshot it starts from: after the restore or checkout, before the stage's own steps
            at = max([i + 1 for i, st in enumerate(steps) if (st.get("_j2gha") or {}).get("role") == "checkout"
                      or st.get("id") == workspace.RESTORE_ID], default=0)
            steps.insert(at, workspace.record_step())
        cell = _matrix_cell(jobs[jid]) if jid in hp.deltas else None
        steps += workspace.handon_steps(jid, jid in hp.mergeable, ACTIONS["upload-artifact"], cell=cell)


def _matrix_cell(job: dict[str, Any]) -> str:
    """A matrix cell's name in artifact names: its axis values (act leaves strategy.job-index empty)."""
    axes = [k for k in (job.get("strategy") or {}).get("matrix", {}) if k not in ("include", "exclude")]
    return "-".join(f"${{{{ matrix.{k} }}}}" for k in axes) or "${{ strategy.job-index }}"


def _container_image(job: dict[str, Any]) -> str | None:
    c = job.get("container")
    return str(c.get("image")) if isinstance(c, dict) and c.get("image") else str(c) if c else None


def _checkout_step(ir: Pipeline, events: list[list[str]]) -> dict[str, Any]:
    """The pipeline's implicit checkout (shared by ordinary jobs and gate jobs: same layout, same trace events)."""
    co: dict[str, Any] = {"name": "Checkout", "uses": ACTIONS["checkout"], "with": {"persist-credentials": False}}
    if sub := ir.options.get("checkoutToSubdirectory"):
        co["with"]["path"] = str(sub)
    co["_j2gha"] = {"kind": "checkout", "line": None, "trace": False, "trace_events": events, "role": "checkout"}
    return co


def _decided(jp: JobPlan) -> str | None:
    """The gate's decision as an expression usable in a step `if:` of a job that needs the gate."""
    return f"needs.{jp.decision}.outputs.run == 'true'" if jp.decision else None


def _job_condition(jp: JobPlan, skippable: set[str]) -> str | None:
    """Job-level `if:` (only `needs`/`github`/`vars`/`inputs` are available there): the gate's decision, and a status
    function when a job it needs may have been skipped (`success()` is false then, which would skip it too)."""
    parts = []
    if set(jp.needs) & skippable:
        parts.append("!failure() && !cancelled()")
    if jp.decision:
        parts.append(_decided(jp) or "")
    return " && ".join(parts) or None


def _stage_input_job(jp: JobPlan, ctx: Ctx, timeout: int, skippable: set[str], ir: Pipeline,
                     first: bool) -> dict[str, Any]:
    st = jp.parent
    job: dict[str, Any] = {"name": jp.name, "runs-on": "ubuntu-latest", "environment": jp.environment,
                           "timeout-minutes": timeout}
    if jp.needs:
        job["needs"] = jp.needs if len(jp.needs) > 1 else jp.needs[0]
    if cond := _job_condition(jp, skippable):
        job["if"] = cond
    steps: list[dict[str, Any]] = []
    if first:
        # the workflow's first job carries Jenkins' implicit checkout and pipeline-environment events, even when
        # that job is only an approval
        if jp.implicit_checkout and ir.dialect == "declarative":
            steps.append(_checkout_step(ir, [[IMPLICIT_CHECKOUT_STAGE, "checkout"]]))
        if env_step := _pipeline_env_step(ctx, first=True):
            steps.append(env_step)
    job["steps"] = steps + [_input_step(st, ctx, Inherit(stage=st.name))]
    return job


def _stage_gate_job(jp: JobPlan, ctx: Ctx, timeout: int, ir: Pipeline, skippable: set[str],
                    first: bool) -> dict[str, Any]:
    """Decides a stage's `when` once, outside any protected environment (`beforeInput true`). It sees what the stage
    would: the same checkout and the same pipeline environment."""
    st = jp.parent
    job: dict[str, Any] = {"name": jp.name, "runs-on": "ubuntu-latest", "timeout-minutes": timeout}
    if jp.needs:
        job["needs"] = jp.needs if len(jp.needs) > 1 else jp.needs[0]
    if cond := _job_condition(jp, skippable):
        job["if"] = cond
    steps: list[dict[str, Any]] = []
    if ir.dialect == "declarative" and not ir.options.get("skipDefaultCheckout"):
        # the first job of the workflow carries Jenkins' implicit checkout and environment events, gate or not
        steps.append(_checkout_step(ir, [[IMPLICIT_CHECKOUT_STAGE, "checkout"]] if jp.implicit_checkout else []))
    env_step = _pipeline_env_step(ctx, first=first)
    if env_step:
        steps.append(env_step)
    entry = _entry_step(st.name, ctx, Inherit(stage=st.name), when_expr(st.when)[0], st.line)
    steps.append(entry)
    job["outputs"] = {"run": f"${{{{ steps.{entry['id']}.outputs.run }}}}"}
    job["steps"] = steps
    return job


def _pipeline_env_step(ctx: Ctx, first: bool = False) -> dict[str, Any] | None:
    """Pipeline `environment {}` values computed by the shell (`sh(returnStdout)`, GStrings over other variables):
    every job that reads them evaluates them (job outputs cannot cross a chain of `needs`). The Jenkins trace events
    of the evaluation belong to the first job only."""
    if not (ctx.runtime_env or (ctx.env_trace and first)):
        return None
    lines = [f'{_export(k, v)}; echo "{k}=${{{k}}}" >> "$GITHUB_ENV"' for k, v in ctx.runtime_env] or ["true"]
    return {"name": "Set pipeline environment (Jenkins environment {})", "run": "\n".join(lines),
            "_j2gha": {"kind": "environment", "trace": False, "role": "setup",
                       "trace_events": list(ctx.env_trace) if first else []}}


def _parent_scope(st: Stage, ctx: Ctx, inherit: Inherit, first: bool, decided: str | None = None
                  ) -> tuple[Inherit, list[dict[str, Any]]]:
    """A parallel stage's own `when`, `environment` and `options` wrap every branch job. Reported (and its
    environment traced, as Jenkins evaluates it once) for the first branch only."""
    n_items = len(ctx.items)
    cond, _ = when_expr(st.when)
    cond = decided or cond  # a gated stage's condition was decided once, by its gate job
    inh = inherit.child(stage=st.name)
    out: list[dict[str, Any]] = []
    if cond:
        entry = _entry_step(st.name, ctx, inh, cond, st.line)
        out.append(entry)
        inh = inh.child(cond=_gate(entry))
    inh, env_steps = _apply_scope(st.environment, st.options, ctx, st.name, st.line, inh)
    if not first:
        del ctx.items[n_items:]
        for x in env_steps:
            x["_j2gha"]["trace_events"] = []
    return inh, out + env_steps


def _wire_script_vars(jobs: dict[str, Any], ctx: Ctx) -> None:
    """$GITHUB_ENV does not cross jobs: a later job reading env.<var> needs the producing job and maps its output."""
    order = list(jobs)
    for var, producers in ctx.var_producers.items():
        for jid in order:
            job = jobs[jid]
            if not re.search(rf"\benv\.{re.escape(var)}\b", repr(job.get("steps", []))):
                continue
            ups = [p for p in producers if p[0] in jobs and order.index(p[0]) < order.index(jid)]
            if not ups:
                continue
            pj, sid = ups[-1]
            jobs[pj].setdefault("outputs", {})[var] = f"${{{{ steps.{sid}.outputs.{var} }}}}"
            needs = job.get("needs")
            lst = [needs] if isinstance(needs, str) else list(needs or [])
            if pj not in lst:
                job["needs"] = [*lst, pj] if lst else pj
            job.setdefault("env", {})[var] = f"${{{{ needs.{pj}.outputs.{var} }}}}"


def _unique_matrix_artifacts(steps: list[dict[str, Any]], axes: list[str]) -> list[dict[str, Any]]:
    """Every matrix cell runs the same upload steps and artifact names must be unique per run: suffix the cell's axis
    values (act leaves strategy.job-index empty). A stash keeps its name (later jobs unstash it by name) and
    overwrites, as the last cell's stash wins in Jenkins."""
    suffix = "".join(f"-${{{{ matrix.{k} }}}}" for k in axes)
    for st in steps:
        if str(st.get("uses", "")).startswith("actions/upload-artifact@"):
            if st["_j2gha"]["kind"] == "stash":
                st["with"]["overwrite"] = True
            else:
                st["with"]["name"] += suffix
    return steps


HANDOFF_STEPS = {"stash", "unstash", "archiveArtifacts", "archive", "copyArtifacts"}


def _hands_off_files(stages: list[Stage]) -> bool:
    """Does any stage move files between workspaces explicitly (stash/unstash, artifacts)?"""
    def rec(steps: list[Step]) -> bool:
        return any(s.name in HANDOFF_STEPS or rec(s.body) for s in steps)

    def walk(sts: list[Stage]) -> bool:
        return any(rec(st.steps) or walk(st.parallel) or walk(st.stages) or
                   (st.matrix is not None and walk(st.matrix.stages)) for st in sts)
    return walk(stages)


def _uses_checkout(st: Stage) -> bool:
    def rec(steps):
        return any(s.name in ("checkout",) or rec(s.body) for s in steps)
    return rec(st.steps)


def _has_checkout(jobs: dict[str, Any]) -> bool:
    """Does any generated job check the source out (the implicit Declarative checkout, `checkout`, `git`)?"""
    return any((st.get("_j2gha") or {}).get("kind") in ("checkout", "git") or
               str(st.get("uses", "")).startswith("actions/checkout@")
               for job in jobs.values() for st in job.get("steps", []))


_REF = re.compile(r"\$\{(?:env\.)?([A-Za-z_]\w*)\}|\$(?:env\.)?([A-Za-z_]\w*)")


def _fixed_value(text: str, ir: Pipeline) -> tuple[str, list[str]]:
    """Substitute GString references whose value is fixed before the run (top-level script constants, literal pipeline
    environment values) -> (text, names left unresolved). For keys GitHub evaluates before any step runs, such as
    jobs.<id>.container, which neither expands shell references nor offers the env context."""
    unresolved: list[str] = []

    def sub(m: re.Match[str]) -> str:
        name = m.group(1) or m.group(2)
        if name in ir.constants:
            return ir.constants[name]
        ev = ir.environment.get(name)
        if ev is not None and ev.kind == "literal" and isinstance(ev.value, str) and "$" not in ev.value:
            return ev.value
        unresolved.append(name)
        return m.group(0)

    return _REF.sub(sub, text), unresolved


def _agent(agent: Agent | None, ctx: Ctx, where: str) -> tuple[Any, Any, str | None, list[dict[str, Any]]]:
    """-> runs-on, container, wrap_image, extra setup steps"""
    if agent is None or agent.kind in ("any", "none", "inherit"):
        return "ubuntu-latest", None, None, []
    if agent.kind == "label":
        lab = (agent.label or "").lower()
        if "win" in lab:
            ro = "windows-latest"
        elif any(x in lab for x in ("mac", "osx", "darwin", "ios")):
            ro = "macos-latest"
        elif any(x in lab for x in ("arm", "aarch64")):
            ro = "ubuntu-24.04-arm"
        else:
            ro = "ubuntu-latest"
        ctx.add(f"agent label '{agent.label}'", agent.line, where, "approximated" if lab not in ("", "linux") else "mapped",
                f"runs-on: {ro}", "use a self-hosted runner label if the agent provides special tooling/network")
        return ro, None, None, []
    if agent.kind == "docker":
        image, unresolved = _fixed_value(agent.image or "TODO-image", ctx.ir)
        container: dict[str, Any] = {"image": image}
        if agent.args:
            args, more = _fixed_value(str(agent.args), ctx.ir)
            unresolved += more
            opts = re.sub(r"(^|\s)--network[= ]\S+", " ", args).strip()
            if opts:
                container["options"] = opts
        if agent.raw.get("registryCredentialsId"):
            sec = ctx.secret(str(agent.raw["registryCredentialsId"]))
            container["credentials"] = {"username": f"${{{{ secrets.{sec}_USR }}}}",
                                        "password": f"${{{{ secrets.{sec}_PSW }}}}"}
        if unresolved:
            ctx.add(f"agent docker '{agent.image}'", agent.line, where, "manual", "job container",
                    f"the image/args use run-time values ({', '.join(sorted(set(unresolved)))}) that GitHub does not "
                    "expand in jobs.<id>.container: set them literally")
        else:
            ctx.add(f"agent docker '{agent.image}'", agent.line, where, "mapped", "job container",
                    "job containers run as root; reuseNode has no equivalent")
        return "ubuntu-latest", container, None, []
    if agent.kind == "dockerfile":
        fname = agent.filename or "Dockerfile"
        d = agent.dir or "."
        build = {"name": "Build agent image (agent dockerfile)",
                 "run": f"docker build -t j2gha-agent:local -f {shlex.quote(str(d) + '/' + str(fname) if d != '.' else str(fname))} {shlex.quote(str(d))}",
                 "_j2gha": {"kind": "dockerfile-agent", "trace": False, "role": "setup"}}
        ctx.add(f"agent dockerfile '{fname}'", agent.line, where, "approximated", "docker build + docker run wrapper",
                "steps run via `docker run` in the built image")
        return "ubuntu-latest", None, "j2gha-agent:local", [build]
    if agent.kind == "kubernetes":
        ctx.add("agent kubernetes", agent.line, where, "manual", "runs-on: ubuntu-latest",
                "pod templates need job containers/services or ARC runner scale sets")
        return "ubuntu-latest", None, None, []
    ctx.add(f"agent {agent.kind}", agent.line, where, "manual", "runs-on: ubuntu-latest")
    return "ubuntu-latest", None, None, []


def _tools_steps(tools: dict[str, str], ctx: Ctx) -> list[dict[str, Any]]:
    out = []
    for kind, name in tools.items():
        ver = re.findall(r"\d+(?:\.\d+)?", str(name))
        v = ver[0] if ver else None
        meta = {"kind": f"tools:{kind}", "trace": False, "role": "setup"}
        if kind in ("jdk", "java"):
            out.append({"name": f"Set up JDK ({name})", "uses": ACTIONS["setup-java"],
                        "with": {"distribution": "temurin", "java-version": v if v and float(v) >= 8 else "17"},
                        "_j2gha": meta})
        elif kind in ("nodejs", "node"):
            out.append({"name": f"Set up Node.js ({name})", "uses": ACTIONS["setup-node"],
                        "with": {"node-version": v or "lts/*"}, "_j2gha": meta})
        elif kind == "go":
            out.append({"name": f"Set up Go ({name})", "uses": ACTIONS["setup-go"], "with": {"go-version": v or "stable"},
                        "_j2gha": meta})
        elif kind == "gradle":
            out.append({"name": f"Set up Gradle ({name})", "uses": ACTIONS["setup-gradle"], "_j2gha": meta})
        elif kind == "maven":
            ctx.add(f"tools maven '{name}'", None, None, "approximated", "runner-provided Maven",
                    "GitHub-hosted Ubuntu runners include Maven; pin a version with a setup action if required")
            continue
        else:
            ctx.add(f"tools {kind} '{name}'", None, None, "manual", "-", "no setup action mapping")
            continue
        ctx.add(f"tools {kind} '{name}'", None, None, "approximated", out[-1]["uses"],
                "Jenkins tool name mapped by version heuristics")
    return out


# --------------------------------------------------------------------------------------------- stages & steps
def _and(*conds: str | None) -> str | None:
    parts = [c for c in conds if c]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return " && ".join(f"({p})" for p in parts)


def _when_line(st: Stage) -> int | None:
    return st.when.conditions[0].line if st.when and st.when.conditions else st.line


def _when_note(status: str) -> str:
    if status == "manual":
        return ("untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false');"
                " unset, the stage runs only where it would run whatever that condition's value")
    return "evaluated once at stage entry against env"


def _gate(entry: dict[str, Any]) -> str:
    return f"steps.{entry['id']}.outputs.run == 'true'"


def _entry_step(stage: str, ctx: Ctx, inh: Inherit, cond: str | None, line: int | None) -> dict[str, Any]:
    """Stage entry. Jenkins evaluates `when` once; the stage's steps test this step's output instead of re-evaluating
    an env-based condition per step (a step in the stage may change that env). Stage `post` anchors on it."""
    step = _mk(f"{stage}: enter stage", ctx, Inherit(cond=_and(inh.cond, cond), stage=stage), "stage-entry", line,
               run='echo "run=true" >> "$GITHUB_OUTPUT"', trace=False)
    step["_j2gha"]["trace_run"] = step["run"]  # control flow: kept in trace variants
    return step


def _input_step(st: Stage, ctx: Ctx, inh: Inherit) -> dict[str, Any]:
    return _mk(f"{st.name}: input approval", ctx, inh, "input", st.input.get("line"),
               run=f"echo \"Approved via environment protection: {_sh_escape(str(st.input.get('message', '')))}\"",
               trace=True)


def _apply_scope(environment: dict[str, EnvValue], options: dict[str, Any], ctx: Ctx, stage: str, line: int | None,
                 inh: Inherit) -> tuple[Inherit, list[dict[str, Any]]]:
    """environment {} and options {} (timeout, retry) of a stage, matrix cell or parallel stage."""
    exports: list[tuple[str, str]] = []
    env_trace: list[list[str]] = []
    inh = inh.child()
    block = _env_block(environment, ctx, stage, runtime=exports, trace=env_trace)
    inh.env.update(block)
    # a nearer static value supersedes an outer shell export of the same name (review R9-2)
    static = set(block) - {k for k, _ in exports}
    inh.exports = [(k, v) for k, v in inh.exports if k not in static] + exports
    if options.get("timeout"):
        t = options["timeout"]
        inh.timeout = t.get("minutes") if isinstance(t, dict) else None
        ctx.add(f"stage '{stage}' options: timeout", line, stage, "approximated",
                f"timeout-minutes: {inh.timeout} per step", "Jenkins times out the whole stage")
    if options.get("retry"):
        try:
            inh.retry = int(options["retry"])
            ctx.add(f"stage '{stage}' options: retry({inh.retry})", line, stage, "approximated", "per-step retry",
                    "Jenkins retries the whole stage; here each run step is retried on its own")
        except (TypeError, ValueError):
            ctx.add(f"stage '{stage}' options: retry", line, stage, "manual", "-", "retry count is not a literal")
    out = []
    if env_trace:
        # Jenkins evaluates the environment once at stage entry; values are re-evaluated per run step here
        env_step = _mk(f"{stage}: stage environment", ctx, inh.child(env={}, exports=[], retry=None), "environment",
                       line, run="true", trace=False)
        env_step["_j2gha"]["trace_events"] = env_trace
        out.append(env_step)
    return inh, out


def _stage_steps(st: Stage, ctx: Ctx, inherit: Inherit, path: list[str], with_input: bool = True,
                 with_post: bool = True, decided: str | None = None) -> list[dict[str, Any]]:
    """Jenkins order: options wrappers, input (unless `beforeInput`), when, environment, steps, post."""
    cond, status = when_expr(st.when)
    if st.when:
        ctx.add(f"stage '{st.name}' when", _when_line(st), st.name, status, f"if: {cond}", _when_note(status))
    cond = decided or cond  # a gated stage's condition was decided once, by its gate job
    inh = inherit.child(stage=st.name)
    out: list[dict[str, Any]] = []
    has_input = with_input and st.input and not st.parallel
    before_input = bool(st.when and st.when.before_input)
    if has_input and not before_input:
        out.append(_input_step(st, ctx, inh))
    entry = None
    if cond or (with_post and st.post):
        entry = _entry_step(st.name, ctx, inh, cond, st.line)
        out.append(entry)
        inh = inh.child(cond=_gate(entry))
    if has_input and before_input:
        out.append(_input_step(st, ctx, inh))
    inh, env_steps = _apply_scope(st.environment, st.options, ctx, st.name, st.line, inh)
    out += env_steps
    body: list[dict[str, Any]] = []
    if st.stages:
        for child in st.stages:
            body += _stage_steps(child, ctx, inh, path + [child.name])
    elif st.parallel:
        # nested parallel inside a job (e.g. parallel within sequential stages) -> run sequentially
        ctx.add(f"stage '{st.name}' nested parallel", st.line, st.name, "approximated", "sequential steps",
                "nested parallel branches serialised inside one job")
        for br in st.parallel:
            body += _stage_steps(br, ctx, inh, path + [br.name])
    elif st.matrix:
        body += _matrix_steps(st, ctx, inh)
    else:
        body += _steps(st.steps, ctx, inh)
    out += body
    if with_post:
        out += _stage_post(st.post, ctx, inh, body, st.name, entry)
    return out


def _steps(steps: list[Step], ctx: Ctx, inh: Inherit) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in steps:
        out += _step(s, ctx, inh)
    return out


def _mk(name: str, ctx: Ctx, inh: Inherit, kind: str, line: int | None, *, run: str | None = None,
        uses: str | None = None, with_: dict | None = None, trace: bool = True, extra_env: dict | None = None,
        cond: str | None = None, shell: str | None = None) -> dict[str, Any]:
    # GitHub trims step names (the harness maps a failed step back to its stage by name): no surrounding
    # whitespace, internal runs collapsed to one space, and none left by the length cut either
    step: dict[str, Any] = {"name": step_name_key(name)[:120].rstrip()}
    sid = ctx.sid()
    step["id"] = sid
    c = _and(inh.cond, cond)
    if c:
        step["if"] = c
    if uses:
        step["uses"] = uses
        if uses == ACTIONS["checkout"] and inh.working_dir:
            with_ = {**(with_ or {}), "path": inh.working_dir}  # `dir('x') { checkout scm }` checks out into x
        if with_:
            step["with"] = with_
    bare = None  # the command without the `docker run` wrapper (execution variants: no Docker on the reference)
    if run is not None:
        if inh.exports and kind in ("sh", "echo", "writeFile"):
            run = "\n".join(_export(k, v) for k, v in inh.exports) + "\n" + run
        if inh.wrap_image and kind in ("sh",):
            bare = run
            run = (f"docker run --rm -v \"$PWD\":\"$PWD\" -w \"$PWD\" --env-file <(env | grep -v '^PATH=') "
                   f"{inh.wrap_image} sh -c {shlex.quote(run)}")
        shell = shell or inh.shell
        if inh.retry and inh.retry > 1:
            if bare is not None:
                bare = _retry_loop(bare, shell, inh.retry, ctx, inh.stage, line)[0]
            run, shell = _retry_loop(run, shell, inh.retry, ctx, inh.stage, line)
        step["run"] = run
        if shell:
            step["shell"] = shell
        if inh.working_dir:
            step["working-directory"] = inh.working_dir
    env = {**inh.env, **(extra_env or {})}
    if env:
        step["env"] = env
    if inh.continue_on_error:
        step["continue-on-error"] = True
    if inh.timeout:
        step["timeout-minutes"] = inh.timeout
    step["_j2gha"] = {"kind": kind, "stage": inh.stage, "line": line, "trace": trace}
    if bare is not None:
        step["_j2gha"]["run_without_docker"] = bare
    if inh.concurrent:
        step["_j2gha"]["concurrent"] = True
    return step


def _retry_loop(run: str, shell: str | None, count: int, ctx: Ctx, stage: str, line: int | None) -> tuple[str, str | None]:
    """retry(n): every attempt runs the script as its own process with the step's shell semantics, so a failing
    command fails the attempt (inside `if (...)` bash would ignore `set -e`) and the last exit status is kept."""
    if shell and shell.split()[0] in ("cmd", "pwsh", "powershell"):
        ctx.add("retry", line, stage, "manual", "-", f"retry of a {shell.split()[0]} step is not generated")
        return run, shell
    inner = (shell or "bash --noprofile --norc -eo pipefail {0}").replace("{0}", '"$j2gha_script"')
    if inner.split()[0] in ("bash", "sh") and len(inner.split()) == 2:
        inner = inner.replace(" ", " -e ", 1)  # GitHub runs `shell: bash|sh` as `bash -e {0}` / `sh -e {0}`
    loop = (f'j2gha_script="$(mktemp "${{RUNNER_TEMP:-/tmp}}/j2gha-retry.XXXXXX")"\n'
            f"cat > \"$j2gha_script\" <<'J2GHA_RETRY_EOF'\n{run}\nJ2GHA_RETRY_EOF\n"
            f"for attempt in $(seq 1 {count}); do\n"
            f"  rc=0\n  {inner} || rc=$?\n"
            f"  if [ \"$rc\" = 0 ]; then break; fi\n"
            f"  if [ \"$attempt\" = {count} ]; then exit \"$rc\"; fi\n"
            f"  echo \"retrying ($attempt/{count})\" >&2\n"
            f"done")
    return loop, "bash"


def _export(name: str, value: str) -> str:
    # `export X="$(cmd)"` would mask the command's exit status (shellcheck SC2155)
    return f'{name}="{value}"; export {name}' if "$(" in value else f'export {name}="{value}"'


def _indent(text: str, n: int) -> str:
    return "\n".join((" " * n + line) if line else line for line in text.splitlines())


def _sh_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")


def _arg(s: Step, *names: str, index: int = 0) -> Any:
    for n in names:
        if n in s.named:
            return s.named[n]
    return s.args[index] if len(s.args) > index else None


# Shell-only parameter expansions (${#X}, ${X:-d}, ${X%.*}, ${X/a/b}...): never Groovy, so never translated. They
# reach a GString escaped (`\${X:-d}`) and arrive here unescaped.
SHELL_EXPANSION = re.compile(r"#[A-Za-z_]\w*|[A-Za-z_]\w*(?::?[-+=?]|%|#|/|\^|,).*", re.S)


def _shell_arg(s: Step, value: Any, nulls: set[str] | None = None) -> tuple[str, bool]:
    """A step's shell text: a Groovy GString is translated, a plain string ('...' / '''...''') reaches the shell
    verbatim, so its ${...} is shell syntax. Returns (text, approximated?)."""
    return _groovy_text_to_shell(str(value), nulls) if s.dynamic else (str(value), False)


def _null_note(nulls: set[str]) -> str:
    """Report note for the NULL_WHEN_UNSET names a GString interpolated (collected by _groovy_text_to_shell)."""
    if not nulls:
        return ""
    names = sorted(nulls)
    return ("an unset env." + "/".join(names) + " is the string 'null' in Jenkins; reproduced with ${"
            + "}/${".join(f"{n}:-null" for n in names) + "}; if the pipeline meant 'empty', drop the default")


def _groovy_text_to_shell(text: str, nulls: set[str] | None = None) -> tuple[str, bool]:
    """Groovy GString interpolation -> shell. Returns (text, approximated?). `nulls` collects the NULL_WHEN_UNSET
    names emitted as `${X:-null}`."""
    approx = False

    def repl(m: re.Match) -> str:
        nonlocal approx
        inner = m.group(1)
        if SHELL_EXPANSION.fullmatch(inner):
            return m.group(0)
        mm = re.fullmatch(r"(env\.|params\.)?([A-Za-z_][A-Za-z0-9_]*)", inner)
        if mm:
            if not mm.group(1) and not mm.group(2).isupper():
                approx = True  # probably a Groovy local variable, not an environment variable
            # a declared parameter is always set (possibly to ''): Jenkins renders '' for X, env.X and params.X alike
            if mm.group(2) in NULL_WHEN_UNSET and mm.group(1) != "params." and mm.group(2) not in (PARAM_TYPES.get() or {}):
                if nulls is not None:
                    nulls.add(mm.group(2))
                return "${" + mm.group(2) + ":-null}"  # Groovy renders the unset variable as `null`
            return "${" + mm.group(2) + "}"
        approx = True
        return "${J2GHA_TODO_" + re.sub(r"\W", "_", inner)[:30] + "}"

    out = re.sub(r"(?<!\\)\$\{([^}]+)\}", repl, text)
    return out, approx


def _groovy_text_to_expr(text: str) -> str:
    """Groovy GString -> GHA expression string for non-shell fields (paths, working-directory, with:)."""
    def repl(m: re.Match) -> str:
        inner = m.group(1)
        mm = re.fullmatch(r"(?:env\.|params\.)?([A-Za-z_][A-Za-z0-9_]*)", inner)
        if mm:
            return "${{ env." + mm.group(1) + " }}"
        return "J2GHA_TODO_" + re.sub(r"\W", "_", inner)[:30]
    return re.sub(r"(?<!\\)\$\{([^}]+)\}", repl, text)


def _shell_for(script: str) -> tuple[str, str | None]:
    """Dedent a Jenkins script; honour a leading shebang (Jenkins executes scripts with their interpreter)."""
    body = textwrap.dedent(script).strip("\n")
    body = "\n".join(line.rstrip() for line in body.splitlines()).strip()
    if body.startswith("#!"):
        first, _, rest = body.partition("\n")
        interp = first[2:].strip()
        if interp.startswith("/usr/bin/env "):
            interp = interp[len("/usr/bin/env "):]
        interp = interp.replace("/bin/bash", "bash").replace("/usr/bin/bash", "bash").replace("/bin/sh", "sh")
        return rest.strip(), f"{interp} {{0}}"
    return body, None


def _step(s: Step, ctx: Ctx, inh: Inherit) -> list[dict[str, Any]]:
    n = s.name
    st = inh.stage
    label = "post: " if st == PIPELINE_POST_STAGE else (f"{st}: " if st else "")
    if s.receiver and s.receiver not in ("this", "steps") and not s.receiver.startswith("docker"):
        return _unmapped(s, ctx, inh, label)  # Lib.build() is a library method, not the step it is named like
    # ------------------------------------------------------------ shell
    if n in ("sh", "bat", "powershell", "pwsh"):
        script = _arg(s, "script")
        if script is None:
            ctx.add(n, s.line, st, "manual", "-", "no script argument")
            return []
        nulls: set[str] = set()
        cmd, approx = _shell_arg(s, script, nulls)
        for flag in ("returnStdout", "returnStatus"):
            if s.named.get(flag):
                approx = True
        cmd, shebang_shell = _shell_for(cmd)
        shell = {"bat": "cmd", "powershell": "powershell", "pwsh": "pwsh"}.get(n) or shebang_shell
        first = next((ln.strip() for ln in cmd.splitlines() if ln.strip()), n)
        title = s.named.get("label") or first
        status = "approximated" if (approx or s.dynamic) else "mapped"
        note = "; ".join(x for x in ("Groovy interpolation of non-env values needs review" if approx else "",
                                     _null_note(nulls)) if x)
        ctx.add(n, s.line, st, status, "run" + (f" (shell: {shell})" if shell else ""), note)
        return [_mk(f"{label}{str(title)[:70]}", ctx, inh, n, s.line, run=cmd or "true", shell=shell)]
    if n == "echo":
        msg = _arg(s, "message")
        nulls = set()
        text, approx = _shell_arg(s, msg if msg is not None else "", nulls)
        ctx.add("echo", s.line, st, "approximated" if approx else "mapped", "run: echo", _null_note(nulls))
        quoted = _sh_escape_keep_vars(text) if s.dynamic else _sh_escape(text)
        return [_mk(f"{label}echo", ctx, inh, "echo", s.line, run=f"echo \"{quoted}\"")]
    if n == "error":
        msg = str(_arg(s, "message") or "error")
        ctx.add("error", s.line, st, "mapped", "run: ::error:: + exit 1")
        return [_mk(f"{label}error", ctx, inh, "error", s.line, run=f"echo \"::error::{_sh_escape(msg)}\"\nexit 1")]
    if n == "unstable":
        msg = str(_arg(s, "message") or "unstable")
        ctx.add("unstable", s.line, st, "approximated", "::warning::", "GHA has no UNSTABLE result")
        return [_mk(f"{label}unstable", ctx, inh, "unstable", s.line, run=f"echo \"::warning::{_sh_escape(msg)}\"")]
    if n == "sleep":
        t = _arg(s, "time") or 1
        unit = str(s.named.get("unit", "SECONDS")).upper()
        secs = int(float(t)) * {"MINUTES": 60, "HOURS": 3600, "MILLISECONDS": 0}.get(unit, 1) if str(t).replace(".", "").isdigit() else 1
        ctx.add("sleep", s.line, st, "mapped", "run: sleep")
        return [_mk(f"{label}sleep", ctx, inh, "sleep", s.line, run=f"sleep {max(secs, 0)}")]
    # ------------------------------------------------------------ scm
    if n == "checkout":
        arg = _arg(s, "scm")
        if arg in (None, "scm") or (isinstance(arg, str) and arg.strip() == "scm"):
            ctx.add("checkout scm", s.line, st, "mapped", ACTIONS["checkout"])
            return [_mk(f"{label}checkout", ctx, inh, "checkout", s.line, uses=ACTIONS["checkout"],
                        with_={"persist-credentials": False})]
        ctx.add("checkout (explicit SCM)", s.line, st, "approximated", ACTIONS["checkout"],
                "explicit SCM configuration - verify repository/ref")
        return [_mk(f"{label}checkout", ctx, inh, "checkout", s.line, uses=ACTIONS["checkout"],
                    with_={"persist-credentials": False})]
    if n == "git":
        url = str(_arg(s, "url") or "")
        branch = s.named.get("branch")
        m = re.match(r"(?:https://github\.com/|git@github\.com:)([^/]+/[^/.]+?)(?:\.git)?/?$", url)
        with_: dict[str, Any] = {"persist-credentials": False}
        if m:
            with_["repository"] = m.group(1)
        if branch:
            with_["ref"] = str(branch)
        if s.named.get("credentialsId"):
            with_["token"] = f"${{{{ secrets.{ctx.secret(str(s.named['credentialsId']))} }}}}"
        if m or not url:
            ctx.add("git", s.line, st, "mapped" if m else "approximated", ACTIONS["checkout"])
            return [_mk(f"{label}git checkout", ctx, inh, "git", s.line, uses=ACTIONS["checkout"], with_=with_ or None)]
        ctx.add("git", s.line, st, "approximated", "run: git clone", "non-GitHub remote")
        return [_mk(f"{label}git clone", ctx, inh, "git", s.line,
                    run=f"git clone {'-b ' + shlex.quote(str(branch)) + ' ' if branch else ''}{shlex.quote(url)} .")]
    # ------------------------------------------------------------ artifacts & tests
    if n in ("archiveArtifacts", "archive"):
        pattern = _groovy_text_to_expr(str(_arg(s, "artifacts", "includes") or ""))
        paths = "\n".join(_artifact_paths(inh, pattern, _groovy_text_to_expr(str(s.named.get("excludes") or "")),
                                           default_excludes=_flag(s, "defaultExcludes")))
        allow_empty = bool(s.named.get("allowEmptyArchive"))
        ctx.add(n, s.line, st, "mapped", ACTIONS["upload-artifact"],
                "fingerprinting has no equivalent" if s.named.get("fingerprint") else "")
        step = _mk(f"{label}archive artifacts", ctx, inh, n, s.line, uses=ACTIONS["upload-artifact"],
                   with_={"name": f"artifacts-{ctx.counter + 1}", "path": paths or "**",
                          "if-no-files-found": "ignore" if allow_empty else "error",
                          # archiveArtifacts keeps dotfiles; upload-artifact drops them unless told otherwise (013:
                          # 933 of 4,863 archived files were .project/.settings/.github entries)
                          "include-hidden-files": True})
        # Jenkins archives paths relative to the current dir(): the full-mode comparison uploads them the same way
        step["_j2gha"]["root"] = inh.working_dir or ""
        return [step]
    if n == "junit":
        pattern = _groovy_text_to_expr(str(_arg(s, "testResults") or ""))
        allow_empty = bool(s.named.get("allowEmptyResults"))
        ctx.add("junit", s.line, st, "approximated", "upload-artifact + step summary",
                "no native test UI; failing tests cannot mark the run UNSTABLE")
        # patterns may hold ${{ }} expressions (matrix dirs): pass them as env, not into the script (zizmor)
        summary = ("python3 - <<'PY'\nimport glob, os, xml.etree.ElementTree as ET\n"
                   "files = [f for p in os.environ['J2GHA_JUNIT'].splitlines() "
                   "for f in glob.glob(p, recursive=True)]\nt = f = e = s = 0\nfor x in files:\n"
                   "    r = ET.parse(x).getroot()\n    for ts in ([r] if r.tag == 'testsuite' else r.iter('testsuite')):\n"
                   "        t += int(ts.get('tests', 0)); f += int(ts.get('failures', 0)); e += int(ts.get('errors', 0)); "
                   "s += int(ts.get('skipped', 0))\n"
                   "with open(os.environ.get('GITHUB_STEP_SUMMARY', os.devnull), 'a') as out:\n"
                   "    out.write(f'### JUnit: {t} tests, {f} failures, {e} errors, {s} skipped ({len(files)} files)\\n')\n"
                   f"if not files and not {allow_empty!r}:\n    raise SystemExit('no test report files found')\nPY")
        return [
            _mk(f"{label}junit summary", ctx, inh, "junit", s.line, run=summary, cond="always()",
                extra_env={"J2GHA_JUNIT": "\n".join(p.strip() for p in pattern.split(",") if p.strip())}),
            _mk(f"{label}upload test reports", ctx, inh, "junit-upload", s.line, uses=ACTIONS["upload-artifact"],
                with_={"name": f"test-reports-{ctx.counter + 1}",
                       "path": "\n".join(_artifact_paths(inh, pattern, default_excludes=False)),
                       "if-no-files-found": "ignore" if allow_empty else "warn"}, trace=False, cond="always()"),
        ]
    if n == "stash":
        name = str(_arg(s, "name") or "stash")
        includes = _groovy_text_to_expr(str(s.named.get("includes") or "**"))
        ctx.stashes[name] = _glob_root([p.strip() for p in includes.split(",") if p.strip()] or ["**"])
        # Jenkins: a stash matching nothing fails the build unless `allowEmpty: true`, which then stashes nothing
        # (and the later unstash restores nothing); upload-artifact creates no artifact for an empty upload
        allow_empty = bool(s.named.get("allowEmpty"))
        if allow_empty:
            ctx.stash_allow_empty.add(name)
        ctx.add(f"stash '{name}'", s.line, st, "approximated", ACTIONS["upload-artifact"],
                "artifact hand-off between jobs; file permissions are not preserved" +
                ("; allowEmpty: no artifact is created when nothing matches (if-no-files-found: ignore) and the "
                 "matching unstash then restores nothing (download by pattern)" if allow_empty else
                 "; no matching files fails the step, as the stash does in Jenkins (if-no-files-found: error)"))
        paths = _artifact_paths(inh, includes, _groovy_text_to_expr(str(s.named.get("excludes") or "")),
                                default_excludes=_flag(s, "useDefaultExcludes"))
        return [_mk(f"{label}stash {name}", ctx, inh, "stash", s.line, uses=ACTIONS["upload-artifact"],
                    with_={"name": _stash_artifact(name), "path": "\n".join(paths), "retention-days": 1,
                           "include-hidden-files": True, "if-no-files-found": "ignore" if allow_empty else "error"})]
    if n == "unstash":
        name = str(_arg(s, "name") or "stash")
        allow_empty = name in ctx.stash_allow_empty
        ctx.add(f"unstash '{name}'", s.line, st, "approximated", ACTIONS["download-artifact"],
                "the stash was declared allowEmpty: downloaded by pattern, so an absent (empty) stash restores "
                "nothing and succeeds, while any other download error still fails the step" if allow_empty else "")
        # upload-artifact strips the patterns' common directory; Jenkins restores paths relative to the unstash dir
        dest = "/".join(x for x in (inh.working_dir, ctx.stashes.get(name, "")) if x)
        # an empty stash is a successful restore of nothing, not a tolerated failure: `continue-on-error` would leave
        # the step's outcome 'failure', which stage post conditions read (review R8-6)
        what = {"pattern": _stash_artifact(name), "merge-multiple": True} if allow_empty else \
            {"name": _stash_artifact(name)}
        return [_mk(f"{label}unstash {name}", ctx, inh, "unstash", s.line, uses=ACTIONS["download-artifact"],
                    with_={**what, **({"path": dest} if dest else {})})]
    if n in ("publishHTML",):
        target = s.args[0] if s.args else s.named.get("target")
        ctx.add(n, s.line, st, "approximated", ACTIONS["upload-artifact"], "HTML report published as artifact")
        return [_mk(f"{label}publish HTML report", ctx, inh, n, s.line, uses=ACTIONS["upload-artifact"],
                    with_={"name": f"html-report-{ctx.counter + 1}", "path": _in_dir(inh, _report_dir(target))},
                    cond="always()")]
    if n in ("recordIssues", "jacoco", "cobertura", "publishCoverage", "recordCoverage", "publishChecks",
             "fingerprint"):
        ctx.add(n, s.line, st, "approximated", "echo placeholder", "use an approved reporting action (SARIF/coverage)")
        return [_mk(f"{label}{n} (report placeholder)", ctx, inh, n, s.line,
                    run=f"echo \"::notice::Jenkins '{n}' report - publish with an approved action\"")]
    # ------------------------------------------------------------ orchestration / governance
    if n == "input":
        ctx.add("input", s.line, st, "approximated", "environment protection",
                "split the workflow at the gate; inline input step replaced by a notice")
        msg = str(_arg(s, "message") or "")
        return [_mk(f"{label}input", ctx, inh, "input", s.line,
                    run=f"echo \"::notice::Manual approval point: {_sh_escape(msg)} (use a protected environment)\"")]
    if n == "build":
        job = str(_arg(s, "job") or "?")
        ctx.add(f"build job: {job}", s.line, st, "manual", "workflow_call / workflow_dispatch",
                "downstream Jenkins job must be migrated; trigger with `gh workflow run` or a reusable workflow")
        return [_mk(f"{label}trigger downstream '{job}'", ctx, inh, "build", s.line,
                    run=f"echo \"::warning::Downstream Jenkins job '{_sh_escape(job)}' - migrate to a reusable workflow "
                        f"or call: gh workflow run <workflow> --ref <ref>\"")]
    if n in ("mail", "emailext", "slackSend", "office365ConnectorSend"):
        ctx.add(n, s.line, st, "approximated", "notification placeholder",
                "use an approved notification action (e.g. slackapi/slack-github-action)")
        return [_mk(f"{label}{n} notification", ctx, inh, n, s.line,
                    run=f"echo \"::notice::{n} notification (configure an approved notification action)\"")]
    if n in ("deleteDir", "cleanWs"):
        ctx.add(n, s.line, st, "mapped", "run: workspace cleanup", "runners are ephemeral; kept for parity")
        return [_mk(f"{label}{n}", ctx, inh, n, s.line, run="find . -mindepth 1 -delete || true")]
    if n in ("zip", "unzip", "tar", "untar"):
        return _archive_step(s, ctx, inh, label)
    if n == "writeFile":
        fname = str(_arg(s, "file") or "file.txt")
        nulls: set[str] = set()
        text, approx = _shell_arg(s, _arg(s, "text", index=1) or "", nulls)
        target = f'"{_groovy_text_to_shell(fname)[0]}"' if "${" in fname else shlex.quote(fname)
        # a GString is interpolated, so the heredoc must expand ${VAR} and nothing else
        delim = "J2GHA_EOF" if s.dynamic else "'J2GHA_EOF'"
        body = _heredoc_escape(text) if s.dynamic else text
        ctx.add("writeFile", s.line, st, "approximated" if approx else "mapped", "run: heredoc", _null_note(nulls))
        if text.endswith("\n"):
            body = body[:-1]  # the heredoc adds the final newline
            run = f"cat > {target} <<{delim}\n{body}\nJ2GHA_EOF"
        elif s.dynamic:
            # no final newline in the text: the heredoc adds one, and `$(...)` would also strip the interpolated
            # value's own trailing newlines - a sentinel keeps those, then the heredoc's newline is removed
            run = (f"J2GHA_W=\"$(cat <<{delim}\n{body}\nJ2GHA_EOF\nprintf x)\"; J2GHA_W=${{J2GHA_W%x}}; "
                   f"printf '%s' \"${{J2GHA_W%$'\\n'}}\" > {target}")
        else:
            run = f"printf '%s' {shlex.quote(text)} > {target}"
        return [_mk(f"{label}writeFile {fname}", ctx, inh, "writeFile", s.line, run=run)]
    if n in ("milestone", "lock"):
        ctx.add(n, s.line, st, "approximated", "concurrency", "use workflow/job concurrency groups")
        return _steps(s.body, ctx, inh) if s.body else []
    if n in ("githubNotify", "setGitHubPullRequestStatus", "timestamps", "ansiColor") and not s.body:
        ctx.add(n, s.line, st, "dropped", "-", "native in GitHub Actions")
        return []
    # ------------------------------------------------------------ wrappers with bodies
    if n == "dir":
        path = _groovy_text_to_expr(str(_arg(s, "path") or "."))
        ctx.add("dir", s.line, st, "mapped", "working-directory")
        base = inh.working_dir
        mkdir = []
        if path not in ("", "."):  # Jenkins' dir creates the directory; working-directory needs it to exist
            mkdir = [_mk(f"{label}dir" if "${{" in path else f"{label}dir {path}"[:60], ctx, inh, "dir", None, run='mkdir -p -- "$J2GHA_DIR"',
                         trace=False, extra_env={"J2GHA_DIR": path})]
        return mkdir + _steps(s.body, ctx, inh.child(working_dir=f"{base}/{path}" if base else path))
    if n == "withEnv":
        return _with_env(s, ctx, inh)
    if n == "withCredentials":
        env = dict(inh.env)
        # credentialsId: "${ocir_creds}" (007): the nearest literal definition - stage/withEnv values in the step env
        # (shell-evaluated exports and expressions are not literals), then the pipeline environment
        step_scope: dict[str, str | None] = {k: (None if "$" in str(v) else str(v)) for k, v in inh.env.items()}
        step_scope.update({k: None for k, _ in inh.exports})
        scopes = [step_scope, literal_scope(ctx.ir.environment)]
        for b in s.named.get("bindings", []):
            cid = resolve_credential_id(str(b.get("credentialsId", "?")), scopes)
            t = b.get("type")
            if t in ("string", "file"):
                env[str(b.get("variable", "SECRET"))] = f"${{{{ secrets.{ctx.secret(cid)} }}}}"
            elif t in ("usernamePassword",):
                env[str(b.get("usernameVariable", "USERNAME"))] = f"${{{{ secrets.{ctx.secret(cid, '_USR')} }}}}"
                env[str(b.get("passwordVariable", "PASSWORD"))] = f"${{{{ secrets.{ctx.secret(cid, '_PSW')} }}}}"
            elif t == "usernameColonPassword":
                env[str(b.get("variable", "USERPASS"))] = f"${{{{ secrets.{ctx.secret(cid)} }}}}"
            elif t == "sshUserPrivateKey":
                env[str(b.get("keyFileVariable", "SSH_KEY"))] = f"${{{{ secrets.{ctx.secret(cid)} }}}}"
            elif t == "aws":  # AmazonWebServicesCredentialsBinding: an access key id and a secret key
                env[str(b.get("accessKeyVariable", "AWS_ACCESS_KEY_ID"))] = f"${{{{ secrets.{ctx.secret(cid, '_USR')} }}}}"
                env[str(b.get("secretKeyVariable", "AWS_SECRET_ACCESS_KEY"))] = f"${{{{ secrets.{ctx.secret(cid, '_PSW')} }}}}"
            else:
                env[str(b.get("variable", "SECRET"))] = f"${{{{ secrets.{ctx.secret(cid)} }}}}"
            if "$" in cid:
                # the id is computed at run time (or by a non-literal nearer definition): never guessed from an outer
                # scope, so the secret name stands for "whichever credential this selects"
                ctx.add(f"withCredentials {t} '{cid}'", s.line, st, "manual", "secrets -> step env",
                        f"credential id is not a literal where it is used: choose the secret behind {ctx.secret(cid)}")
                continue
            ctx.add(f"withCredentials {t} '{cid}'", s.line, st, "approximated" if t in ("file", "sshUserPrivateKey") else "mapped",
                    "secrets -> step env", "file/ssh credentials hold the secret *content*; write to a temp file"
                    if t in ("file", "sshUserPrivateKey") else "")
        return _steps(s.body, ctx, inh.child(env=env))
    if n == "timeout":
        t = _arg(s, "time")
        unit = str(s.named.get("unit", "MINUTES")).upper()
        try:
            mins = max(1, int(round(float(t) * {"SECONDS": 1 / 60, "HOURS": 60, "DAYS": 1440}.get(unit, 1))))
        except (TypeError, ValueError):
            mins = None
        ctx.add("timeout", s.line, st, "approximated", "timeout-minutes per step", "Jenkins timeout covers the whole block")
        return _steps(s.body, ctx, inh.child(timeout=mins))
    if n == "retry":
        try:
            count = int(_arg(s, "count"))
        except (TypeError, ValueError):
            count = 2
        ctx.add("retry", s.line, st, "approximated", "shell retry loop", "only run steps are retried")
        return _steps(s.body, ctx, inh.child(retry=count))
    if n in ("catchError", "warnError"):
        ctx.add(n, s.line, st, "approximated", "continue-on-error", "stage/build result overrides not representable")
        return _steps(s.body, ctx, inh.child(continue_on_error=True))
    if n in ("timestamps", "ansiColor", "wrap", "withMaven", "withGradle", "nodejs", "withPythonEnv",
             "configFileProvider", "lock", "milestone"):
        ctx.add(n, s.line, st, "approximated" if n not in ("timestamps", "ansiColor") else "dropped",
                "body inlined", "wrapper semantics not reproduced" if n not in ("timestamps", "ansiColor") else
                "native in GitHub Actions")
        return _steps(s.body, ctx, inh)
    if n in ("sshagent",):
        ids = s.args[0] if s.args and isinstance(s.args[0], list) else []
        env = dict(inh.env)
        for cid in (x["expr"] if isinstance(x, dict) else x for x in ids):
            env[f"SSH_KEY_{ctx.secret(str(cid))}"] = f"${{{{ secrets.{ctx.secret(str(cid))} }}}}"
        ctx.add("sshagent", s.line, st, "approximated", "webfactory/ssh-agent (recommended)",
                "keys exposed as env; load into an agent with an approved action")
        return _steps(s.body, ctx, inh.child(env=env))
    if n in ("withDockerRegistry", "withRegistry") or (s.receiver and "docker" in s.receiver and n == "withRegistry"):
        ctx.add("docker registry login", s.line, st, "approximated", "docker/login-action (recommended)")
        return _steps(s.body, ctx, inh)
    if n == "inside" and s.receiver and "docker" in s.receiver:
        m = re.search(r"image\((['\"])(.+?)\1\)", s.receiver)
        image = m.group(2) if m else None
        ctx.add("docker.image().inside", s.line, st, "approximated", "docker run wrapper",
                "consider a job container instead")
        return _steps(s.body, ctx, inh.child(wrap_image=image or inh.wrap_image))
    if n == "container":
        ctx.add("container (kubernetes)", s.line, st, "manual", "steps inlined",
                "map the pod container image to a job container or docker run")
        return _steps(s.body, ctx, inh)
    if n in ("withSonarQubeEnv", "withAWS", "withKubeConfig", "withVault", "azureCLI", "withDockerServer",
             "withDockerContainer"):
        ctx.add(n, s.line, st, "approximated", "body inlined", "configure identity via OIDC / approved action")
        return _steps(s.body, ctx, inh)
    if n == "node":
        ctx.add("node (in steps)", s.line, st, "approximated", "inlined", "nested agent allocation flattened")
        return _steps(s.body, ctx, inh)
    if n == "stage":  # scripted stage nested in steps/script
        name = str(_arg(s, "name") or "?")
        return _steps(s.body, ctx, inh.child(stage=name))
    if n == "parallel":
        ctx.add("parallel (step)", s.line, st, "approximated", "sequential steps",
                "scripted parallel branches serialised; split into jobs/matrix for real parallelism")
        out = []
        for b in s.body:
            out += _step(b, ctx, inh.child(concurrent=True))
        return out
    if n in ctx.ir.method_defs and s.category in ("unknown", "local") and not s.receiver:
        return _inline_method(s, ctx, inh)
    if n == "script":
        return _script(s, ctx, inh)
    if n.startswith("<"):
        return _script_stmt(s, ctx, inh)
    # ------------------------------------------------------------ docker.* global variable
    if s.receiver and s.receiver.startswith("docker"):
        ctx.add(f"{s.receiver}.{n}", s.line, st, "manual", "docker CLI", "translate docker DSL to docker CLI/actions")
        return [_mk(f"{label}docker.{n} (manual)", ctx, inh, f"docker.{n}", s.line,
                    run=f"echo \"::warning::docker DSL call '{_sh_escape(s.receiver)}.{n}' needs manual migration\"",
                    trace=False)]
    return _unmapped(s, ctx, inh, label)


def _archive_step(s: Step, ctx: Ctx, inh: Inherit, label: str) -> list[dict[str, Any]]:
    """pipeline-utility-steps zip/unzip/tar/untar -> the same command line tools (on GitHub's runner images)."""
    n, st = s.name, inh.stage
    f = _arg(s, "zipFile" if n in ("zip", "unzip") else "file")
    if f is None:
        ctx.add(n, s.line, st, "manual", "-", "no archive file argument")
        return []
    q = (lambda v: f'"{_groovy_text_to_shell(str(v))[0]}"') if s.dynamic else (lambda v: shlex.quote(str(v)))
    d = s.named.get("dir")
    glob = s.named.get("glob")
    if n == "zip":
        cmd = (f'j2gha_zip="$PWD"/{q(f)}; (cd {q(d or ".")} && zip -qr "$j2gha_zip" .'
               + (f" -i {q(glob)})" if glob else ")"))
    elif n == "unzip":
        cmd = f"unzip -qo {q(f)} -d {q(d or '.')}" + (f" {q(glob)}" if glob else "")
    elif n == "tar":
        cmd = f"tar -c{'z' if s.named.get('compress') else ''}f {q(f)} -C {q(d or '.')} ."
    else:
        cmd = f"mkdir -p {q(d or '.')} && tar -xf {q(f)} -C {q(d or '.')}"
    approx = bool(glob or s.named.get("exclude") or s.dynamic)
    ctx.add(n, s.line, st, "approximated" if approx else "mapped", f"run: {cmd.split()[0]}",
            "Ant glob/exclude patterns need review" if glob or s.named.get("exclude") else "")
    return [_mk(f"{label}{n} {f}", ctx, inh, n, s.line, run=cmd, trace=n in TRACED_STEPS)]


def _with_env(s: Step, ctx: Ctx, inh: Inherit) -> list[dict[str, Any]]:
    """withEnv(['K=v', "K=${x}", 'PATH+X=dir']): literal values reach the environment unexpanded (as in Jenkins);
    interpolated values are evaluated by the shell before run steps; PATH+X prepends to PATH."""
    st = inh.stage
    arg = s.args[0] if s.args else None
    if not isinstance(arg, list):
        ctx.add("withEnv", s.line, st, "manual", "-", f"environment list computed at runtime: {str(arg)[:60]}")
        return _steps(s.body, ctx, inh)
    env, exports, status, notes = dict(inh.env), list(inh.exports), "mapped", []
    for item in arg:
        text = item["expr"] if isinstance(item, dict) else item
        key, sep, value = str(text).partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z_]\w*(\+\w*)?", key):
            status = "manual"
            notes.append(f"binding `{str(text)[:40]}` not translated")
            continue
        if isinstance(item, dict):
            value, approx = _groovy_text_to_shell(value)
        if "+" in key:  # PATH+MAVEN=/opt/maven/bin
            exports.append((key.split("+")[0], f"{value}:${{{key.split('+')[0]}}}"))
            status = _worse(status, "approximated")
            notes.append(f"{key} prepended to {key.split('+')[0]} in run steps")
        elif isinstance(item, dict):
            exports.append((key, value))
            status = _worse(status, "approximated")
            notes.append(f"{key} evaluated by the shell in run steps" + (" (Groovy values need review)" if approx else ""))
        else:
            env[key] = value
            # a nearer literal supersedes an outer shell export of the same name (review R9-2)
            exports = [(k, v) for k, v in exports if k != key]
    ctx.add("withEnv", s.line, st, status, "step env" + (" + shell exports" if exports != inh.exports else ""),
            "; ".join(notes))
    return _steps(s.body, ctx, inh.child(env=env, exports=exports))


def _worse(a: str, b: str) -> str:
    return max(a, b, key=lambda x: STATUS_RANK.get(x, 0))


def _unmapped(s: Step, ctx: Ctx, inh: Inherit, label: str) -> list[dict[str, Any]]:
    n, st = s.name, inh.stage
    if s.category in ("groovy", "local") or n in ("println", "print"):
        ctx.add(n, s.line, st, "manual", "-", "Groovy method / helper call - port logic to a script")
        return []
    if s.category in ("noop",):
        ctx.add(n, s.line, st, "dropped", "-", "no GHA equivalent needed")
        return []
    kind = n
    ctx.add(n, s.line, st, "manual", "placeholder step",
            f"{s.category} step with no deterministic mapping" + (" (plugin/shared-library step)" if s.category == "unknown" else ""))
    body = _steps(s.body, ctx, inh) if s.body else []
    # traced only when the Jenkins localiser traces it too: TRACED_STEPS and unknown plugin/library steps called by
    # bare name. Methods on objects and constructors (Lib.build(), new Lib()) hit silent J2ghaAny stubs there.
    traced = s.receiver in (None, "this") and (n in TRACED_STEPS or (
        s.category == "unknown" and not n.startswith("new ") and not n[:1].isupper()))
    return [_mk(f"{label}{n} (manual migration)", ctx, inh, kind, s.line,
                run=f"echo \"::warning::Jenkins step '{n}' requires manual migration\"", trace=traced)] + body


def _sh_escape_keep_vars(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")


def _heredoc_escape(s: str) -> str:
    """Body of an unquoted heredoc: expand ${VAR} (translated GString interpolation, including the `${X:-null}`
    form of NULL_WHEN_UNSET names), keep every other $ literal."""
    parts = re.split(r"(\$\{[A-Za-z_]\w*(?::-null)?\})", s)
    return "".join(p if i % 2 else p.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
                   for i, p in enumerate(parts))


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", s).strip("-") or "x"


def _stash_artifact(name: str) -> str:
    """A stash's artifact name: `stash name: "ROBOT_${ROBOT}_urdf"` in a matrix cell is that cell's value, so the
    interpolation becomes an expression and only the literal text is slugged (`unstash 'ROBOT_fr3_urdf'` finds it)."""
    parts = re.split(r"(\$\{\{.*?\}\})", _groovy_text_to_expr(name))
    out = "".join(x if x.startswith("${{") else re.sub(r"[^A-Za-z0-9_.-]+", "-", x) for x in parts).strip("-")
    return f"stash-{out or 'x'}"


def _in_dir(inh: Inherit, path: str) -> str:
    """A workspace-relative path for a `uses:` step (working-directory only applies to run steps)."""
    if not inh.working_dir:
        return path
    path = path[2:] if path.startswith("./") else path
    return inh.working_dir if path in ("", ".") else f"{inh.working_dir.rstrip('/')}/{path}"


# Ant's default excludes, which Jenkins' archiveArtifacts/stash apply unless defaultExcludes/useDefaultExcludes is
# false: upload-artifact with include-hidden-files would otherwise ship .git/** (013 archived '**' on failure).
ANT_DEFAULT_EXCLUDES = ("**/.git", "**/.git/**", "**/.gitignore", "**/.gitattributes", "**/.gitmodules",
                        "**/.svn", "**/.svn/**", "**/.hg", "**/.hg/**", "**/.hgignore", "**/.hgtags",
                        "**/.bzr", "**/.bzr/**", "**/.bzrignore", "**/CVS", "**/CVS/**", "**/.cvsignore",
                        "**/SCCS", "**/SCCS/**", "**/vssver.scc", "**/.DS_Store", "**/*~", "**/#*#", "**/.#*",
                        "**/%*%", "**/._*")


def _artifact_paths(inh: Inherit, includes: str, excludes: str = "", default_excludes: bool = True) -> list[str]:
    """Jenkins comma-separated Ant patterns (relative to the current dir) -> upload-artifact `path` lines."""
    inc = [_in_dir(inh, p.strip()) for p in includes.split(",") if p.strip()]
    exc = [p.strip() for p in excludes.split(",") if p.strip()]
    if default_excludes:
        exc += [p for p in ANT_DEFAULT_EXCLUDES if p not in exc]
    return inc + ["!" + _in_dir(inh, p) for p in exc]


def _flag(step: Step, name: str, default: bool = True) -> bool:
    v = step.named.get(name)
    if v is None:
        return default
    return str(v).strip().lower() not in ("false", "0", "no")


def _glob_root(patterns: list[str]) -> str:
    """The directory upload-artifact stores files relative to: the common ancestor of the patterns' literal
    prefixes (`dist/**` -> `dist`, so the files are uploaded without the `dist/` prefix)."""
    roots = []
    for p in patterns:
        p = p + "**" if p.endswith("/") else p  # Ant: a trailing slash means everything below
        parts = [x for x in p.split("/") if x not in ("", ".")]
        lit = []
        for part in parts:
            if any(ch in part for ch in "*?["):
                break
            lit.append(part)
        else:
            lit = lit[:-1]  # a plain file path: its directory
        roots.append(lit)
    common: list[str] = []
    for level in zip(*roots, strict=False):  # shortest root bounds the common prefix
        if len(set(level)) != 1:
            break
        common.append(level[0])
    return "/".join(common)


def _report_dir(target: Any) -> str:
    if isinstance(target, dict):
        return str(target.get("reportDir", "."))
    m = re.search(r"reportDir:\s*([^,\]]+)", str(target or ""))
    return m.group(1).strip().strip("'\"") if m else "."


def _inline_method(s: Step, ctx: Ctx, inh: Inherit) -> list[dict[str, Any]]:
    """Inline a helper method defined in the Jenkinsfile, substituting literal arguments into its body."""
    if inh.inline_depth >= 3:
        ctx.add(f"{s.name}()", s.line, inh.stage, "manual", "-", "recursive helper method not inlined")
        return []
    mdef = ctx.ir.method_defs[s.name]
    subst = {}
    bare: dict[str, tuple[Any, bool]] = {}  # parameter -> (caller's argument, is it a caller variable?)
    for i, (pname, val) in enumerate(zip(mdef["params"], s.args, strict=False)):
        if i in s.variable_args:
            subst[pname] = "${" + str(val) + "}"  # helper(myVar): the parameter refers to the caller's variable
            bare[pname] = (val, True)
        elif isinstance(val, (str, int, float, bool)):
            subst[pname] = str(val)
            bare[pname] = (val, False)
    body = copy.deepcopy(mdef["body"])
    if subst:
        _substitute(body, subst, bare)
    if s.body and len(mdef["params"]) == len(s.args) + 1:
        # helper(x) { ... } passes the block as the last parameter: calling it runs the caller's steps
        body = _splice_block(body, mdef["params"][-1], s.body)
    ctx.add(f"{s.name}() (local helper method)", s.line, inh.stage, "approximated", "inlined",
            "body of the Jenkinsfile helper method inlined" + (f" with {', '.join(subst)} substituted" if subst else ""))
    return _steps(body, ctx, inh.child(inline_depth=inh.inline_depth + 1))


def _splice_block(steps: list[Step], param: str, block: list[Step]) -> list[Step]:
    out: list[Step] = []
    for st in steps:
        if (st.name == param and not st.receiver) or (st.name == "call" and st.receiver == param):
            out += copy.deepcopy(block)
            continue
        st.body = _splice_block(st.body, param, block)
        for key in ("_else", "_catch", "_finally"):
            if isinstance(st.named.get(key), list):
                st.named[key] = _splice_block(st.named[key], param, block)
        out.append(st)
    return out


def _substitute(steps: list[Step], subst: dict[str, str], bare: dict[str, tuple[Any, bool]] | None = None) -> None:
    """Replace helper parameters in the inlined body: `$p` / `${p}` inside strings, and (``bare``) a positional
    argument that is the parameter itself (`sh target`), which takes the caller's argument as written."""
    def rep(v: Any) -> Any:
        if isinstance(v, str):
            for k, val in subst.items():
                v = re.sub(r"\$\{" + re.escape(k) + r"\}|\$" + re.escape(k) + r"\b", val.replace("\\", "\\\\"), v)
            return v
        if isinstance(v, list):
            return [rep(x) for x in v]
        if isinstance(v, dict):
            return {k: rep(x) for k, x in v.items()}
        return v
    for st in steps:
        for i in list(st.variable_args):
            if bare and i < len(st.args) and st.args[i] in bare:
                st.args[i], is_var = bare[st.args[i]]
                if not is_var:
                    st.variable_args.remove(i)
        st.args = rep(st.args)
        st.named = {k: (rep(v) if k not in ("_else", "_catch", "_finally") else v) for k, v in st.named.items()}
        for key in ("_else", "_catch", "_finally"):
            if isinstance(st.named.get(key), list):
                _substitute(st.named[key], subst, bare)
        _substitute(st.body, subst, bare)


# --------------------------------------------------------------------------------------------- script blocks
def _script(s: Step, ctx: Ctx, inh: Inherit) -> list[dict[str, Any]]:
    ctx.add("script {}", s.line, inh.stage, "approximated", "inner steps translated individually",
            "imperative Groovy is not executed; review control flow")
    return _steps(s.body, ctx, inh)


def _reads_runtime_env(expr: str, inh: Inherit) -> bool:
    """A step's `if:` reads the workflow/job env and the step's own `env:` (verified on GitHub), but not what the step's
    script exports at run time: a condition on a shell-computed stage/wrapper value cannot be evaluated there."""
    runtime = {k for k, _ in inh.exports}
    return any(name in runtime for name in re.findall(r"\benv\.([A-Za-z_]\w*)", re.sub(r"'(?:[^']|'')*'", "''", expr)))


def _count_steps(steps: list[Step]) -> int:
    """Leaf steps (wrappers such as stage/dir/withEnv count through their bodies)."""
    return sum(_count_steps(st.body) if st.body else 1 for st in steps)


def _script_stmt(s: Step, ctx: Ctx, inh: Inherit) -> list[dict[str, Any]]:
    kind = s.name.strip("<>")
    if kind == "if" and (chain := _literal_chain(s)) and (script := _chain_script(*chain, inh.stage)):
        return _chain_step(s, ctx, inh, chain, script)
    if kind == "if":
        expr = translate_groovy(s.source or "")
        if expr and _reads_runtime_env(expr, inh):
            expr = None  # a value only the shell computes: manual gate, never a guess
        if expr:
            ctx.add(f"if ({(s.source or '')[:50]})", s.line, inh.stage, "approximated", f"if: {expr}")
            other = s.named.get("_else") or []
            if _count_steps(s.body) + _count_steps(other) > 1:
                # Groovy decides once; a step of the branch may change what the condition reads (`TARGET=dev`), so
                # later steps and the else branch must test the decision, not the condition again
                # Two steps with the branch steps' own environment (a step's `if:` reads its own `env:`): the first
                # records `taken=true` when the condition holds, the second `taken=false` when the first was skipped
                label = f"{inh.stage}: if (line {s.line})" if inh.stage else f"if (line {s.line})"
                yes = _mk(label, ctx, inh, "if-decision", s.line, run='echo "taken=true" >> "$GITHUB_OUTPUT"',
                          trace=False, cond=expr)
                no = _mk(label, ctx, inh, "if-decision", s.line, run='echo "taken=false" >> "$GITHUB_OUTPUT"',
                         trace=False, cond=f"steps.{yes['id']}.outcome == 'skipped'")
                for d in (yes, no):
                    d["_j2gha"]["trace_run"] = d["run"]
                out = [yes, no] + _steps(s.body, ctx, inh.child(cond=_and(inh.cond, f"steps.{yes['id']}.outputs.taken == 'true'")))
                if other:
                    out += _steps(other, ctx, inh.child(cond=_and(inh.cond, f"steps.{no['id']}.outputs.taken == 'false'")))
                return out
            out = _steps(s.body, ctx, inh.child(cond=_and(inh.cond, expr)))
            if other:
                out += _steps(other, ctx, inh.child(cond=_and(inh.cond, f"!({expr})")))
            return out
        ctx.add(f"if ({(s.source or '')[:50]})", s.line, inh.stage, "manual", "placeholder",
                "condition depends on Groovy runtime state")
        return [_mk(f"{inh.stage}: Groovy if (manual)", ctx, inh, "script-manual", s.line,
                    run=f"echo \"::warning::manual migration: Groovy condition at line {s.line}: "
                        f"{_sh_escape((s.source or '')[:100])}\"", trace=False)]
    if kind == "try":
        ctx.add(f"try/catch/finally (line {s.line})", s.line, inh.stage, "approximated",
                "steps; catch -> if: a try step failed; finally -> if: always() once entered",
                "exception types are not distinguished")
        if not s.body:
            # handlers of a try around preceding stages (analysis.declarative places them after those stages)
            out = []
            if s.named.get("_catch"):
                out += _steps(s.named["_catch"], ctx, inh.child(cond=_and("failure()", inh.cond)))
            if s.named.get("_finally"):
                out += _steps(s.named["_finally"], ctx, inh.child(cond=_and("always()", inh.cond)))
            return out
        # anchor: catch/finally run only if the try was entered (an earlier failure skips it, as in Jenkins), and
        # catch only for a failure inside the try body
        entry = _mk(f"{inh.stage}: try (line {s.line})" if inh.stage else f"try (line {s.line})", ctx,
                    Inherit(cond=inh.cond, stage=inh.stage), "try-entry", s.line,
                    run='echo "run=true" >> "$GITHUB_OUTPUT"', trace=False)
        entry["_j2gha"]["trace_run"] = entry["run"]
        body = _steps(s.body, ctx, inh)
        out = [entry] + body
        entered = f"steps.{entry['id']}.outcome == 'success'"
        failed = " || ".join(f"steps.{x['id']}.outcome == 'failure'" for x in body if "id" in x) or "false"
        if s.named.get("_catch"):
            out += _steps(s.named["_catch"], ctx, inh.child(cond=_and("always()", entered, f"({failed})")))
        if s.named.get("_finally"):
            out += _steps(s.named["_finally"], ctx, inh.child(cond=_and("always()", entered)))
        return out
    if kind in ("decl", "assign"):
        carried = _carry_assignment(s, ctx, inh, kind)
        if carried is not None:
            return carried
        inner = s.body[0] if s.body else None
        if inner and inner.name in ("sh", "bat", "powershell") and (inner.named.get("returnStdout") or inner.named.get("returnStatus")):
            ctx.add(f"{kind} {(s.source or '')[:50]}", s.line, inh.stage, "approximated",
                    "run step (captured output not propagated)", "write values to $GITHUB_OUTPUT/$GITHUB_ENV")
            return _step(inner, ctx, inh)
        if inner:
            ctx.add(f"{kind} {(s.source or '')[:50]}", s.line, inh.stage, "manual", "-",
                    "Groovy variable assignment from a step")
            return _step(inner, ctx, inh)
        ctx.add(f"{kind} {(s.source or '')[:50]}", s.line, inh.stage, "manual", "-", "Groovy variable assignment")
        return []
    ctx.add(f"{kind} ({(s.source or '')[:50]})", s.line, inh.stage, "manual", "placeholder",
            "Groovy control flow requires manual migration")
    return [_mk(f"{inh.stage}: Groovy {kind} (manual)", ctx, inh, "script-manual", s.line,
                run=f"echo \"::warning::manual migration: Groovy {kind} at line {s.line}\"", trace=False)]


# ------------------------------------------------------------------------------------- assignments -> env
# names a pipeline variable must not overwrite through $GITHUB_ENV: the runner's own and the shell's
_RESERVED_ENV = re.compile(r"(?:GITHUB|RUNNER|ACTIONS|BASH|LD)_\w*|CI|HOME|PATH|PWD|OLDPWD|SHELL|USER|IFS|NODE_OPTIONS")
_TRIM = ('{v}="${{{v}#"${{{v}%%[![:space:]]*}}"}}"\n'
         '{v}="${{{v}%"${{{v}##*[![:space:]]}}"}}"\n')


def _publish_var(name: str) -> str:
    """Write a shell variable to $GITHUB_ENV (later steps) and $GITHUB_OUTPUT (later jobs, `_wire_script_vars`)."""
    return "\n".join(f"{{ echo '{name}<<J2GHA_EOF'; printf '%s\\n' \"${name}\"; echo J2GHA_EOF; }} >> \"${f}\""
                     for f in ("GITHUB_ENV", "GITHUB_OUTPUT"))


def _carry_assignment(s: Step, ctx: Ctx, inh: Inherit, kind: str) -> list[dict[str, Any]] | None:
    """`x = sh(script: ..., returnStdout: true)[.trim()]`, `x = pwd()` and string expressions (literals, env/params,
    earlier variables, `+`, `.take(n)`): the value goes to $GITHUB_ENV, so later steps of the job see `$x`/env.x as
    Jenkins' later steps see the variable. None: not a value this can carry (the caller reports it as before)."""
    target = s.named.get("_target") or ""
    value = s.named.get("_value") or {}
    if not re.fullmatch(r"[A-Za-z_]\w*", target) or _RESERVED_ENV.fullmatch(target) or inh.shell not in (None, "bash"):
        return None
    # a Groovy variable is not in the environment of Jenkins' `sh` steps: one named like an environment variable must
    # not change what `$NAME` reads there
    if target in JENKINS_ENV or target in ctx.ir.environment or any(p.name == target for p in ctx.ir.parameters):
        return None
    src = (s.source or "")[:50]
    inner = s.body[0] if s.body else None
    if inner is not None and inner.name == "sh" and inner.named.get("returnStdout") and not inner.named.get("returnStatus"):
        n_items = len(ctx.items)
        steps = _step(inner, ctx, inh)
        if len(steps) != 1 or not isinstance(steps[0].get("run"), str):
            del ctx.items[n_items:]
            return None
        trim = value.get("t") == "call" and (value.get("call") or {}).get("name") == "trim"
        st = steps[0]
        st["run"] = f'{target}="$(\n{st["run"]}\n)"\n' + (_TRIM.format(v=target) if trim else "") + _publish_var(target)
        ctx.add(f"{kind} {src}", s.line, inh.stage, "mapped" if trim else "approximated",
                "run step; its output goes to $GITHUB_ENV",
                "later steps of the job read the variable" + ("" if trim else "; trailing newlines are dropped"))
        ctx.var_producers.setdefault(target, []).append((ctx.job, st["id"]))
        ctx.assigned.add(target)
        return steps
    rendered = _bash_value(value, ctx)
    if rendered is None:
        return None
    if rendered == f'"${{{target}}}"':  # `def VERSION = params.VERSION`: already the environment variable's value
        ctx.add(f"{kind} {src}", s.line, inh.stage, "mapped", "-", "the environment variable already has this value")
        return []
    step = _mk(f"{inh.stage}: set {target}", ctx, inh, "script-assign", s.line,
               run=f"{target}={rendered}\n{_publish_var(target)}", trace=False, shell="bash")
    ctx.add(f"{kind} {src}", s.line, inh.stage, "mapped", "run: $GITHUB_ENV", "later steps of the job read the variable")
    ctx.var_producers.setdefault(target, []).append((ctx.job, step["id"]))
    ctx.assigned.add(target)
    return [step]


def _dq(text: str) -> str:
    """Literal text inside a bash double-quoted string."""
    return re.sub(r'([\\$`"])', r"\\\1", text)


def _bash_ref(name: str, ctx: Ctx) -> str | None:
    """A Groovy name in an expression -> its bash expansion (None: a local whose value is unknown here)."""
    if name in ctx.ir.constants and name not in ctx.assigned:
        return _dq(ctx.ir.constants[name])
    known = (name in ctx.assigned or name in SCRIPT_VARS.get() or name in ctx.ir.environment or name in JENKINS_ENV
             or any(p.name == name for p in ctx.ir.parameters))
    if known or name[0].isupper():  # an undeclared upper-case name is an environment variable in Jenkins
        return f"${{{name}}}"
    return None


def _bash_value(v: dict[str, Any], ctx: Ctx) -> str | None:
    """A Groovy value (AST) -> a bash double-quoted string, or None when it is not a plain string expression."""
    def part(n: dict[str, Any]) -> str | None:
        t = n.get("t")
        if t == "str":
            return _dq(str(n.get("v")))
        if t == "num" and isinstance(n.get("v"), int):
            return str(n["v"])
        if t == "concat":
            parts = [part(p) for p in n.get("parts") or []]
            return None if any(p is None for p in parts) else "".join(parts)  # type: ignore[arg-type]
        if t == "var":
            return _bash_ref(str(n.get("name")), ctx)
        if t == "prop":
            m = re.fullmatch(r"(?:env|params)\.([A-Za-z_]\w*)", str(n.get("text", "")).strip())
            return f"${{{m.group(1)}}}" if m and not n.get("calls") else None
        if t == "gstr":
            return _gstring(str(n.get("v", "")), ctx)
        if t == "call":
            c = n.get("call") or {}
            name, recv, args = c.get("name"), (c.get("receiver") or "").strip(), c.get("args") or []
            if name == "pwd" and not recv and not args and not c.get("named"):
                return "${PWD}"
            if name == "take" and len(args) == 1 and args[0].get("t") == "num" and isinstance(args[0].get("v"), int):
                m = re.fullmatch(r"(?:(?:env|params)\.)?([A-Za-z_]\w*)", recv)
                ref = _bash_ref(m.group(1), ctx) if m else None
                if ref and ref.startswith("${"):
                    return f"${{{ref[2:-1]}:0:{args[0]['v']}}}"
        return None

    body = part(v)
    return None if body is None else f'"{body}"'


def _gstring(src: str, ctx: Ctx) -> str | None:
    """A GString's source (with its quotes) whose interpolations are plain names -> bash double-quoted body."""
    m = re.fullmatch(r'"(.*)"', src, re.S)
    if not m:
        return None
    out, pos, text = [], 0, m.group(1)
    for ref in re.finditer(r"\$\{\s*(?:(?:env|params)\.)?([A-Za-z_]\w*)\s*\}|\$(?:(?:env|params)\.)?([A-Za-z_]\w*)", text):
        lit = text[pos:ref.start()]
        if "$" in lit or "\\" in lit:
            return None  # an interpolation this does not understand, or an escape
        out.append(_dq(lit))
        r = _bash_ref(ref.group(1) or ref.group(2), ctx)
        if r is None:
            return None
        out.append(r)
        pos = ref.end()
    lit = text[pos:]
    if "$" in lit or "\\" in lit:
        return None
    out.append(_dq(lit))
    return "".join(out)


# ------------------------------------------------------------------------------------- if/else chains -> env
def _literal_chain(s: Step) -> tuple[list[tuple[str, list[Step]]], list[Step]] | None:
    """if/else-if/else whose branches only assign string literals to variables or call error()
    (`if (env.GIT_BRANCH ==~ /release-.+/) { target = 'pre' } else ...`): (branches, final else) or None."""
    branches: list[tuple[str, list[Step]]] = []
    cur = s
    while True:
        branches.append((cur.source or "", cur.body))
        other = cur.named.get("_else") or []
        if len(other) == 1 and other[0].name == "<if>":
            cur = other[0]
            continue
        final = other
        break
    assigned = False
    for _, body in [*branches, ("", final)]:
        for st in body:
            if st.name in ("<assign>", "<decl>") and isinstance(st.named.get("_literal"), str) \
                    and re.fullmatch(r"[A-Za-z_]\w*", st.named.get("_target") or ""):
                assigned = True
            elif not (st.name == "error" and len(st.args) == 1 and isinstance(st.args[0], str) and not st.body):
                return None
    return (branches, final) if assigned else None


def _chain_targets(branches: list[tuple[str, list[Step]]], final: list[Step]) -> list[str]:
    return list(dict.fromkeys(st.named["_target"] for _, b in [*branches, ("", final)] for st in b
                              if st.name != "error"))


def _chain_script(branches: list[tuple[str, list[Step]]], final: list[Step], stage: str) -> tuple[str, str] | None:
    """(script, trace-mode script): a bash if/elif chain exporting the variables to $GITHUB_ENV and step outputs."""
    regexes: list[str] = []
    conds = [bash_condition(c, regexes) for c, _ in branches]
    if any(c is None for c in conds):
        return None

    def body(steps: list[Step], trace: bool) -> list[str]:
        lines = []
        for st in steps:
            if st.name == "error":
                msg = re.sub(r"\$\{(?:env\.|params\.)?([A-Za-z_]\w*)\}", r"${\1}", st.args[0])
                msg = msg if not re.search(r"\$\{(?![A-Za-z_]\w*\})", msg) else re.sub(r"\$\{[^}]*\}", "?", msg)
                lines += [marker_cmd(stage, "error") if trace else f'echo "::error::{_sh_escape_keep_vars(msg)}"',
                          "exit 1"]
            else:
                lines.append(f"{st.named['_target']}={shlex.quote(st.named['_literal'])}")
        return lines or [":"]

    def script(trace: bool) -> str:
        out = [f"j2gha_re{i}={shlex.quote(r)}" for i, r in enumerate(regexes, 1)]
        for i, (cond, (_, steps)) in enumerate(zip(conds, branches, strict=True)):
            out.append(f"{'if' if i == 0 else 'elif'} [[ {cond} ]]; then")
            out += [f"  {x}" for x in body(steps, trace)]
        if final:
            out.append("else")
            out += [f"  {x}" for x in body(final, trace)]
        out.append("fi")
        for t in _chain_targets(branches, final):
            out += [f'echo "{t}=${{{t}:-}}" >> "$GITHUB_ENV"', f'echo "{t}=${{{t}:-}}" >> "$GITHUB_OUTPUT"']
        return "\n".join(out)

    return script(False), script(True)


def _chain_step(s: Step, ctx: Ctx, inh: Inherit, chain: tuple, script: tuple[str, str]) -> list[dict[str, Any]]:
    targets = _chain_targets(*chain)
    ctx.add(f"if ({(s.source or '')[:50]}) assigning {', '.join(targets)}", s.line, inh.stage, "approximated",
            "run: bash if/elif -> $GITHUB_ENV + job outputs",
            "Java regexes run as POSIX ERE; later `when`/`if` read env." + ", env.".join(targets))
    step = _mk(f"{inh.stage}: set {', '.join(targets)}", ctx, inh, "script-vars", s.line, run=script[0], trace=False,
               shell="bash")
    step["_j2gha"]["trace_run"] = script[1]  # control flow: kept (with error markers) in trace variants
    for t in targets:
        ctx.var_producers.setdefault(t, []).append((ctx.job, step["id"]))
    return [step]


def _dispatch_vars(ir: Pipeline) -> frozenset[str]:
    """Script variables that literal if/else chains will export, in pipeline order (a chain may test an earlier one)."""
    found: set[str] = set()

    def walk(steps: list[Step]) -> None:
        for st in steps:
            if st.name == "<if>" and (chain := _literal_chain(st)):
                token = SCRIPT_VARS.set(frozenset(found))
                try:
                    if _chain_script(*chain, ""):
                        found.update(_chain_targets(*chain))
                        continue
                finally:
                    SCRIPT_VARS.reset(token)
            walk(st.body)
            for key in ("_else", "_catch", "_finally"):
                if isinstance(st.named.get(key), list):
                    walk(st.named[key])

    for stage, _ in ir.iter_stages():
        walk(stage.steps)
        for steps in stage.post.values():
            walk(steps)
    for steps in ir.post.values():
        walk(steps)
    return frozenset(found)


# --------------------------------------------------------------------------------------------- post
def _stage_post(post: dict[str, list[Step]], ctx: Ctx, inh: Inherit, body: list[dict[str, Any]], stage: str,
                entry: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Stage post conditions from the stage entry step (did the stage run?) and the outcomes of its steps. As in
    Jenkins, every condition is still evaluated after a post step fails, and that failure counts for the later ones."""
    if not post:
        return []
    ran = f"steps.{entry['id']}.outcome == 'success'" if entry else None
    failed_ids = [s["id"] for s in body if "id" in s]
    out = []
    base = inh.child(cond=None, stage=stage)
    for c in POST_ORDER:
        if c not in post:
            continue
        failed = " || ".join(f"steps.{i}.outcome == 'failure'" for i in failed_ids) or "false"
        conds = {
            "always": _and("always()", ran),
            "failure": _and("always()", ran, f"({failed})"),
            "success": _and("!cancelled()", ran, f"!({failed})"),
            "aborted": _and("cancelled()", ran),
            "unsuccessful": _and("always()", ran, f"(({failed}) || cancelled())"),
            "cleanup": _and("always()", ran),
        }
        if c not in conds:
            ctx.add(f"stage '{stage}' post {c}", None, stage, "dropped", "-",
                    "needs previous-run status or UNSTABLE result - no GHA equivalent")
            continue
        ctx.add(f"stage '{stage}' post {c}", None, stage, "mapped", f"if: {conds[c]}")
        steps = _steps(post[c], ctx, base.child(cond=conds[c]))
        failed_ids += [s["id"] for s in steps if "id" in s]
        out += steps
    return out


def _pipeline_post_single(ir: Pipeline, ctx: Ctx, inh: Inherit) -> list[dict[str, Any]]:
    conds = {"always": "always()", "failure": "failure()", "success": "success()", "aborted": "cancelled()",
             "unsuccessful": "failure() || cancelled()", "cleanup": "always()"}
    out = []
    base = inh.child(stage=_post_stage(ir), cond=None)
    for c in POST_ORDER:
        if c not in ir.post:
            continue
        if c not in conds:
            ctx.add(f"post {c}", None, None, "dropped", "-", "no GHA equivalent")
            continue
        ctx.add(f"post {c}", None, None, "mapped", f"if: {conds[c]}")
        out += _steps(ir.post[c], ctx, base.child(cond=conds[c]))
    return out


def _post_stage(ir: Pipeline) -> str:
    """Jenkins runs Declarative post in the 'Declarative: Post Actions' stage; a scripted pipeline's try/catch/finally
    around its stages (see analysis.declarative.interpret_scripted) runs outside any stage."""
    return PIPELINE_POST_STAGE if ir.dialect == "declarative" else ""


def _fanin_post_job(post: dict[str, list[Step]], ctx: Ctx, needs: list[str], stage: str, when: str | None,
                    agent: Agent | None, label: str, restores: bool = False) -> dict[str, Any]:
    """Pipeline post (multi-job workflows) and a parallel/matrix stage's post: a final job after the jobs it needs.
    `success()` is false when a needed job was skipped (a stage whose `when` was false), so success is spelled
    `!failure() && !cancelled()`. Every condition has an explicit status function: the job-level `always()` does not reach its steps, and a
    failing post step must not skip the later conditions (failure() then also counts it, as Jenkins does)."""
    failed = "contains(needs.*.result, 'failure') || failure()"
    cancelled = "contains(needs.*.result, 'cancelled')"
    conds = {"always": "always()", "failure": f"always() && ({failed})",
             "success": f"!failure() && !cancelled() && !contains(needs.*.result, 'failure') && !{cancelled}",
             "aborted": f"always() && {cancelled}",
             "unsuccessful": f"always() && ({failed} || {cancelled})",
             "cleanup": "always()"}
    steps: list[dict[str, Any]] = []
    env_step = _pipeline_env_step(ctx)
    if env_step:
        steps.append(env_step)
    base = Inherit(stage=stage)
    for c in POST_ORDER:
        if c not in post:
            continue
        if c not in conds:
            ctx.add(f"{label} {c}", None, None if label == "post" else stage, "dropped", "-", "no GHA equivalent")
            continue
        cond = _and(conds[c], when)
        ctx.add(f"{label} {c}", None, None if label == "post" else stage, "mapped", f"final job if: {cond}")
        steps += _steps(post[c], ctx, base.child(cond=cond))
    ws_steps = [s.name for c in post.values() for s in c if s.name in (
        "archiveArtifacts", "archive", "junit", "publishHTML", "recordIssues", "jacoco", "cleanWs", "deleteDir")]
    if ws_steps and restores:
        ctx.add(f"{label} (workspace-dependent steps)", None, None, "mapped", "final job",
                f"{', '.join(sorted(set(ws_steps)))} run in the restored pipeline workspace (j2gha-ws-* artifacts)")
    elif ws_steps:
        ctx.add(f"{label} (workspace-dependent steps)", None, None, "approximated", "final job",
                f"{', '.join(sorted(set(ws_steps)))} run in a fresh workspace - upload files from the producing jobs")
    runs_on, container, _, _ = _agent(agent, ctx, label)
    job = {"name": "post" if label == "post" else f"{stage} (post)", "needs": needs, "if": "always()",
           "runs-on": runs_on}
    if container:
        job["container"] = container
    job["steps"] = steps or [{"name": "no-op", "run": "true", "_j2gha": {"kind": "noop", "trace": False}}]
    return job


# --------------------------------------------------------------------------------------------- matrix
def _matrix_strategy(st: Stage, ctx: Ctx) -> dict[str, Any]:
    m = st.matrix
    matrix: dict[str, Any] = {k: [str(v) for v in vals] for k, vals in m.axes.items()}
    excludes = []
    for rule in m.excludes:
        combos = [{}]
        for axis, spec in rule.items():
            vals = [str(v) for v in m.axes.get(axis, [])]
            chosen = [str(v) for v in spec.get("values", [])] if "values" in spec else \
                [v for v in vals if v not in [str(x) for x in spec.get("notValues", [])]]
            combos = [dict(c, **{axis: v}) for c in combos for v in chosen]
        excludes += combos
    if excludes:
        matrix["exclude"] = excludes
    ctx.add(f"stage '{st.name}' matrix ({' x '.join(f'{k}[{len(v)}]' for k, v in m.axes.items())})", m.line, st.name,
            "mapped", "strategy.matrix", "notValues excludes expanded" if any("notValues" in str(r) for r in m.excludes) else "")
    return {"strategy": {"fail-fast": False, "matrix": matrix}}


def _matrix_steps(st: Stage, ctx: Ctx, inh: Inherit) -> list[dict[str, Any]]:
    """Matrix cell-level directives (when, input, environment, options, stages, post) - the stage's own directives
    are applied by the caller. Axis env is set at job level (see _jobs)."""
    m = st.matrix
    mcond, mstatus = when_expr(m.when)
    if m.when:
        ctx.add(f"matrix '{st.name}' when", None, st.name, mstatus, f"if: {mcond}", _when_note(mstatus))
    base = inh.child(stage=st.name)
    out: list[dict[str, Any]] = []
    if m.input:
        out.append(_mk(f"{st.name}: input approval", ctx, base, "input", m.input.get("line"),
                       run=f"echo \"Approved via environment protection: {_sh_escape(str(m.input.get('message', '')))}\"",
                       trace=True))
    entry = None
    if mcond or m.post:
        entry = _entry_step(st.name, ctx, base, mcond, m.line)
        out.append(entry)
        base = base.child(cond=_gate(entry))
    base, env_steps = _apply_scope(m.environment, m.options, ctx, st.name, m.line, base)
    out += env_steps
    body: list[dict[str, Any]] = []
    for child in m.stages:
        body += _stage_steps(child, ctx, base, [st.name, child.name])
    out += body
    out += _stage_post(m.post, ctx, base, body, st.name, entry)
    return out


def _options_items(ir: Pipeline, ctx: Ctx) -> None:
    for k, v in ir.options.items():
        if k == "timeout":
            ctx.add("options: timeout", None, None, "approximated", f"timeout-minutes: {v.get('minutes')} (per job)",
                    "Jenkins timeout covers the whole pipeline")
        elif k in ("timestamps", "ansiColor"):
            ctx.add(f"options: {k}", None, None, "dropped", "-", "native in GitHub Actions")
        elif k == "buildDiscarder":
            ctx.add("options: buildDiscarder", None, None, "dropped", "-", "use artifact retention-days / repo settings")
        elif k == "skipDefaultCheckout":
            ctx.add("options: skipDefaultCheckout", None, None, "mapped", "no checkout step")
        elif k == "disableConcurrentBuilds":
            continue
        elif k == "checkoutToSubdirectory":
            ctx.add("options: checkoutToSubdirectory", None, None, "mapped", "actions/checkout path")
        elif k == "parallelsAlwaysFailFast":
            ctx.add("options: parallelsAlwaysFailFast", None, None, "approximated", "-", "only matrices support fail-fast")
        else:
            ctx.add(f"options: {k}", None, None, "manual", "-", "no GHA equivalent")


# --------------------------------------------------------------------------------------------- report
# automation_pct: an estimate of conversion effort (the share of report items the generator handled), not of correctness
AUTOMATION_WEIGHTS = {"mapped": 1.0, "dropped": 0.8, "approximated": 0.6, "manual": 0.0}
# Report items that describe what the converter adds around a Jenkins element (status "info") are listed but not
# scored: the automation share counts Jenkins elements, so its denominator does not move when such a row is added.


def _report(ctx: Ctx, wf: dict[str, Any]) -> dict[str, Any]:
    seen: set[tuple] = set()
    items = []
    for it in ctx.items:
        key = (it.jenkins, it.line, it.status, it.gha, it.note)
        if it.line is None or key not in seen:
            items.append(it)
        seen.add(key)
    ctx.items = items
    counts: dict[str, int] = {}
    for it in ctx.items:
        counts[it.status] = counts.get(it.status, 0) + 1
    scored = {k: v for k, v in counts.items() if k in AUTOMATION_WEIGHTS}
    total = sum(scored.values()) or 1
    automated = round(100 * sum(AUTOMATION_WEIGHTS[k] * v for k, v in scored.items()) / total, 1)
    jobs = wf["jobs"]
    return {
        "counts": counts,
        "automation_pct": automated,
        "items": [it.__dict__ for it in sorted(ctx.items, key=lambda i: (STATUS_RANK.get(i.status, 9) if i.status in STATUS_RANK else (9 if i.status == "info" else 1), i.line or 0))],
        "secrets": ctx.secrets,
        "jobs": {k: {"name": v.get("name"), "runs-on": v.get("runs-on"), "steps": len(v.get("steps", [])),
                     "matrix": bool(v.get("strategy"))} for k, v in jobs.items()},
        "notes": ctx.notes,
        "handoff": ctx.handoff,
    }


# --------------------------------------------------------------------------------------------- YAML output
class _Dumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper: yaml.SafeDumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_presenter)


def strip_meta(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: strip_meta(v) for k, v in obj.items() if not str(k).startswith("_j2gha")}
    if isinstance(obj, list):
        return [strip_meta(v) for v in obj]
    return obj


def pin_actions(wf: dict[str, Any], resolver) -> dict[str, str]:
    """Rewrite `uses: owner/repo@tag` to commit SHAs. Returns {sha_ref: tag} for YAML comments."""
    pins: dict[str, str] = {}

    def rec(o):
        if isinstance(o, dict):
            u = o.get("uses")
            if isinstance(u, str) and "@" in u and not u.startswith(("./", "docker://")):
                repo, ref = u.split("@", 1)
                if not re.fullmatch(r"[0-9a-f]{40}", ref):
                    sha = resolver(repo, ref)
                    if sha:
                        o["uses"] = f"{repo}@{sha}"
                        pins[o["uses"]] = ref
            for v in o.values():
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec(wf)
    return pins


def github_resolver():
    from ..github import GitHub, GitHubError

    gh = GitHub(cache_ttl=7 * 24 * 3600)
    if not gh.token:
        return lambda repo, ref: None
    cache: dict[str, str | None] = {}

    def resolve(repo: str, ref: str) -> str | None:
        key = f"{repo}@{ref}"
        if key not in cache:
            owner_repo = "/".join(repo.split("/")[:2])
            try:
                cache[key] = gh.get(f"/repos/{owner_repo}/commits/{ref}")["sha"]
            except (GitHubError, KeyError):
                cache[key] = None
        return cache[key]
    return resolve


def to_yaml(wf: dict[str, Any], header: str = "", pins: dict[str, str] | None = None) -> str:
    clean = strip_meta(wf)
    text = yaml.dump(clean, Dumper=_Dumper, sort_keys=False, width=120, allow_unicode=True)
    for ref, tag in (pins or {}).items():
        text = text.replace(f"uses: {ref}\n", f"uses: {ref} # {tag}\n")
    # `on:` must not be quoted/booleanised; PyYAML emits null triggers as `pull_request: null`
    text = text.replace(": null\n", ":\n").replace("\n'on':", "\non:")
    return header + text
