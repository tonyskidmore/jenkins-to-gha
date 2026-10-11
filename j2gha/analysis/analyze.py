"""Static analysis of a Jenkinsfile: dialect, styles, inventory, findings, coverage and complexity.

Inputs are the Groovy AST (``ast.dump_sources``) and the IR (``declarative.build_ir``); optionally the
authoritative Jenkins Declarative model (``/pipeline-model-converter/toJson``) is folded in.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from ..ir import CREDENTIAL_REF, Pipeline, literal_scope, resolve_credential_id
from . import catalog
from .ast import CallCtx, all_calls, child_calls, first_arg, value_text, walk_statements
from .declarative import binding_type, build_ir, parse_environment

ANALYSIS_VERSION = 1

# Styles used by both the analyser and the GitHub crawler (crawl.styles).
STYLE_TITLES = {
    "declarative": "Declarative pipeline",
    "scripted": "Scripted pipeline (node {})",
    "when-post": "Conditional stages (when) and post conditions",
    "parallel": "Parallel stages / branches",
    "matrix": "Declarative matrix",
    "docker-agent": "Docker / Dockerfile agents and docker.* steps",
    "kubernetes-agent": "Kubernetes agents / podTemplate",
    "shared-library": "Shared library consumer (@Library / library step)",
    "library-template": "Shared library pipeline template (vars/*.groovy)",
    "input-gate": "Manual input / approval gates",
    "credentials": "Credentials bindings",
    "parameters-triggers": "Parameters and triggers",
    "artifacts-tests": "Artifacts, stash/unstash and test reports",
    "downstream-build": "Downstream job orchestration (build job:)",
    "dynamic-groovy": "Dynamic Groovy (load, dynamic parallel/stages, heavy script{})",
    "windows": "Windows agents (bat / powershell)",
    "tools": "Tool installations (tools {} / tool step)",
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
CREDIT = {"direct": 1.0, "noop": 1.0, "local": 1.0, "groovy": 0.7, "policy": 0.6, "redesign": 0.2,
          "dynamic": 0.15, "unknown": 0.0}
STRUCTURAL = catalog.DIRECTIVES | {"script"}


def analyse(text: str, ast: dict, jenkins_model: dict | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"analysis_version": ANALYSIS_VERSION}
    result["parser"] = {
        "engine": "groovy-ast (Jenkins-bundled Groovy 2.4, CONVERSION phase)",
        "ok": bool(ast.get("ok")),
        "errors": ast.get("errors", []),
    }
    ir = build_ir(ast) if ast.get("ok") else None
    result["dialect"] = detect_dialect(ast, ir)
    inv = inventory(text, ast, ir)
    result["metrics"] = inv["metrics"]
    result["steps"] = inv["steps"]
    result["unknown_steps"] = inv["unknown_steps"]
    result["agents"] = inv["agents"]
    result["credentials"] = inv["credentials"]
    result["dsl_symbols"] = inv["symbols"]
    result["libraries"] = ir.libraries if ir else []
    result["methods"] = [m.get("name") for m in ast.get("methods", [])]
    findings = find_issues(text, ast, ir, inv, result["dialect"])
    if jenkins_model is not None:
        result["jenkins_model"] = summarise_jenkins_model(jenkins_model, ir)
        if result["jenkins_model"]["result"] == "failure" and result["dialect"] in ("declarative", "library-template"):
            findings.append(_finding("JenkinsValidationFailed", "high", None,
                                     "; ".join(result["jenkins_model"]["errors"][:3]),
                                     "Jenkins rejects this Declarative pipeline - fix syntax/plugins before migrating"))
        for d in result["jenkins_model"].get("discrepancies", []):
            findings.append(_finding("ModelDiscrepancy", "low", None, d,
                                     "j2gha interpretation differs from Jenkins' model - review"))
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f.get("line") or 0))
    result["findings"] = findings
    result["hard_gates"] = [f for f in findings if f.get("gate")]
    result["styles"] = detect_styles(result["dialect"], inv, ir)
    result["coverage"] = coverage(inv)
    result["complexity"] = complexity(result, inv)
    result["convertibility"] = convertibility(result)
    result["ir_notes"] = ir.notes if ir else []
    return result


# --------------------------------------------------------------------------- dialect
def detect_dialect(ast: dict, ir: Pipeline | None) -> str:
    if not ast.get("ok"):
        return "unparseable"
    if ir is None:
        return "unknown"
    if ir.dialect == "declarative":
        return "library-template" if any("shared-library method" in n for n in ir.notes) else "declarative"
    names = [c.name for c in all_calls(ast)]
    if "node" in names or "stage" in names:
        return "scripted"
    top = [s for s in ast.get("statements", []) if s.get("k") == "call"]
    if top and len(top) <= 3 and not any(n in catalog.load_catalog()["steps"] for n in (t.get("name") for t in top)):
        return "library-call"  # e.g. buildPlugin(...) / standardPipeline { ... }
    if ast.get("methods") and any(m.get("name") == "call" for m in ast.get("methods", [])):
        return "library-step"  # vars/*.groovy that is not a whole pipeline
    return "scripted" if top else "unknown"


# --------------------------------------------------------------------------- inventory
def _is_step_ctx(ctx: CallCtx) -> bool:
    """Is this call a pipeline step (vs. a declarative directive)?"""
    if ctx.name in STRUCTURAL and not ctx.in_script and ctx.name not in ("input", "parallel", "stage", "timeout", "retry"):
        return False
    path = ctx.path
    if not path:
        return True  # top-level calls in scripted pipelines / library calls
    if "pipeline" not in path:
        return True
    if ctx.in_script:
        return True
    parent = path[-1]
    if parent in ("steps", *catalog.DIRECTIVES - {"agent", "when", "options", "parameters", "triggers", "tools",
                                                    "environment", "matrix", "axes", "axis", "excludes", "exclude",
                                                    "pipeline", "stages", "stage", "parallel", "libraries", "post",
                                                    "input"}):
        return True
    if parent in ("agent", "when", "options", "parameters", "triggers", "tools", "environment", "matrix", "axes",
                  "axis", "excludes", "exclude", "pipeline", "stages", "stage", "parallel", "libraries", "post",
                  "input", "docker", "dockerfile", "kubernetes", "node", "label", "allOf", "anyOf", "not",
                  "expression"):
        return False
    # nested inside a step with a body (withCredentials { sh }, dir { }, timeout { } ...)
    return any(p == "steps" for p in path) or any(p in catalog.DIRECTIVES and p in ("always", "success", "failure",
                                                                                     "cleanup", "unstable", "changed",
                                                                                     "fixed", "regression", "aborted",
                                                                                     "unsuccessful", "notBuilt")
                                                   for p in path)


def _scope_chain(ctx: CallCtx, pipeline_scope: dict[str, str | None]) -> list[dict[str, str | None]]:
    """The environment scopes a call sees, innermost first: its enclosing literal withEnv lists and stage/matrix
    environment {} blocks, read from the enclosing nodes themselves (actual nesting, no line-based identity: same-line
    siblings, nested wrappers and same-line matrices resolve as Jenkins does, review R9-1/R10-1), then the pipeline's."""
    chain: list[dict[str, str | None]] = []
    for n in reversed(ctx.ancestors):
        name = n.get("name")
        if name in ("stage", "matrix"):
            chain += [literal_scope(parse_environment(e)) for e in child_calls(n.get("body"), "environment")]
        elif name == "withEnv" and (first_arg(n) or {}).get("t") == "list":
            scope: dict[str, str | None] = {}
            for item in first_arg(n)["v"]:
                key_, sep, value = value_text(item).partition("=")
                if sep and re.fullmatch(r"[A-Za-z_]\w*", key_):
                    scope[key_] = value if item.get("t") == "str" and value else None
            chain.append(scope)
    return chain + [pipeline_scope]


def _resolve_credential_refs(creds: dict[str, dict[str, Any]],
                             uses: dict[str, list[tuple[int | None, list[dict[str, str | None]]]]]) -> None:
    """credentialsId: "${ocir_creds}" (007): the id the controller must provision is the literal the reference selects
    where it is used - through the scope chain of that use (_scope_chain; ir.resolve_credential_id, shared with the
    generator). A reference resolving to an id already listed is merged into that entry; one that does not resolve
    stays listed under its expression. The expression is kept for the report."""
    for cid in [c for c in creds if CREDENTIAL_REF.fullmatch(c)]:
        entry = creds.pop(cid)
        by_id: dict[str, list[Any]] = {}
        for line, chain in uses.get(cid) or [(None, [])]:
            by_id.setdefault(resolve_credential_id(cid, chain), []).append(line)
        for rid, lines in by_id.items():
            lines = [x for x in lines if x is not None]
            if rid == cid:
                creds.setdefault(cid, {**entry, "lines": []})["lines"].extend(lines)
            elif rid in creds:
                creds[rid]["lines"].extend(lines)
                creds[rid].setdefault("expr", cid)
            else:
                creds[rid] = {**entry, "id": rid, "expr": cid, "lines": lines}


def inventory(text: str, ast: dict, ir: Pipeline | None) -> dict[str, Any]:
    steps: dict[str, dict[str, Any]] = {}
    local_methods = {m.get("name") for m in ast.get("methods", [])}
    unknown: dict[str, list[int]] = defaultdict(list)
    agents: list[dict[str, Any]] = []
    creds: dict[str, dict[str, Any]] = {}
    cred_uses: dict[str, list[tuple[int | None, list[dict[str, str | None]]]]] = defaultdict(list)
    pipeline_scope = literal_scope(ir.environment) if ir else {}

    def add_cred(cid: str, kind: str | None, line: int | None, ctx: CallCtx) -> None:
        creds.setdefault(cid, {"id": cid, "type": kind, "lines": []})["lines"].append(line)
        if CREDENTIAL_REF.fullmatch(cid):
            cred_uses[cid].append((line, _scope_chain(ctx, pipeline_scope)))

    symbols: set[str] = set()
    m = Counter()
    calls = list(all_calls(ast)) if ast.get("ok") else []

    for ctx in calls:
        name = ctx.name
        node = ctx.node
        if name == "script" and not ctx.in_script and "pipeline" in ctx.path:
            m["script_blocks"] += 1
            m["script_statements"] += sum(1 for _ in walk_statements(node.get("body") or []))
            continue
        if not _is_step_ctx(ctx):
            continue
        if ctx.in_args and not node.get("body"):
            if not node.get("receiver") and name not in local_methods and catalog.categorise(name) == "unknown" \
                    and name not in catalog.GROOVY_METHODS and not name[:1].isupper():
                symbols.add(name)
            continue
        qualified = name
        receiver = node.get("receiver")
        if receiver and receiver.split(".")[0].split("(")[0] == "docker":
            qualified = f"docker.{name}" if receiver == "docker" else f"docker.{receiver.split('.')[-1].split('(')[0]}.{name}"
        cat = catalog.categorise(qualified)
        if cat == "unknown" and receiver:
            cat = "groovy"  # method on an object (string ops, maps, custom classes)
        if cat == "unknown" and name in catalog.GROOVY_METHODS:
            cat = "groovy"
        if cat == "unknown" and name in local_methods:
            cat = "local"
        if cat == "unknown" and (name[:1].isupper() or name.startswith("new ")):
            cat = "groovy"
        entry = steps.setdefault(qualified, {"count": 0, "category": cat, "lines": [], "gha": catalog.target(qualified)})
        entry["count"] += 1
        if len(entry["lines"]) < 12 and ctx.line:
            entry["lines"].append(ctx.line)
        if cat == "unknown":
            unknown[qualified].append(ctx.line or 0)
        if name in ("sh", "bat", "powershell", "pwsh"):
            m["shell_steps"] += 1
        if name == "input":
            m["input_gates"] += 1
        if name == "build" and ("job" in node.get("named", {}) or node.get("args")):
            m["downstream_builds"] += 1
        if name in ("stash", "unstash", "archiveArtifacts", "archive", "junit", "publishHTML", "recordIssues",
                    "jacoco", "recordCoverage", "publishCoverage", "cobertura"):
            m["artifact_steps"] += 1
        if name == "load" or name == "evaluate":
            m["loads"] += 1
        if name in ("withCredentials",):
            for a in node.get("args", []):
                for item in a.get("v", []) if a.get("t") == "list" else []:
                    if item.get("t") == "call":
                        bc = item["call"]
                        cid = value_text(bc.get("named", {}).get("credentialsId")) or "?"
                        add_cred(cid, bc.get("name"), bc.get("line"), ctx)
                    elif item.get("t") == "map" and "$class" in (item.get("v") or {}):
                        kv = item["v"]
                        cid = value_text(kv.get("credentialsId")) or "?"
                        add_cred(cid, binding_type(value_text(kv["$class"])), item.get("line"), ctx)
        if name in ("sshagent",):
            for a in node.get("args", []):
                for item in a.get("v", []) if a.get("t") == "list" else []:
                    cid = value_text(item)
                    add_cred(cid, "sshUserPrivateKey", ctx.line, ctx)
        if name in ("docker.withRegistry",) or (receiver == "docker" and name == "withRegistry"):
            if len(node.get("args", [])) > 1:
                add_cred(value_text(node["args"][1]), "usernamePassword", ctx.line, ctx)
        if name in ("git", "checkout") and node.get("named", {}).get("credentialsId"):
            add_cred(value_text(node["named"]["credentialsId"]), "usernamePassword", ctx.line, ctx)
        if name == "node" and "pipeline" not in ctx.path:
            agents.append({"kind": "label", "label": value_text(first_arg(node, "label")) or None, "line": ctx.line,
                           "scope": "scripted"})
        if name == "podTemplate":
            agents.append({"kind": "kubernetes", "line": ctx.line, "scope": "scripted"})
        if name == "inside" and receiver and "docker" in receiver:
            agents.append({"kind": "docker", "image": receiver, "line": ctx.line, "scope": "step"})

    # credentials() in environment blocks + agents from IR
    if ir:
        def add_env(env, scope):
            for v in env.values():
                if v.kind == "credentials":
                    creds.setdefault(v.credential_id, {"id": v.credential_id, "type": "credentials()", "lines": []})["lines"].append(v.line)
                    if CREDENTIAL_REF.fullmatch(v.credential_id):
                        cred_uses[v.credential_id].append((v.line, [pipeline_scope]))
        add_env(ir.environment, "pipeline")
        _resolve_credential_refs(creds, cred_uses)
        if ir.agent and ir.dialect == "declarative":
            agents.append({"kind": ir.agent.kind, "label": ir.agent.label, "image": ir.agent.image, "line": ir.agent.line,
                           "scope": "pipeline"})
        for st, depth in ir.iter_stages():
            add_env(st.environment, st.name)
            m["stages"] += 1
            m["max_stage_depth"] = max(m["max_stage_depth"], depth + 1)
            if st.agent and ir.dialect == "declarative":
                agents.append({"kind": st.agent.kind, "label": st.agent.label, "image": st.agent.image,
                               "line": st.agent.line, "scope": f"stage:{st.name}"})
            if st.parallel:
                m["parallel_blocks"] += 1
                m["parallel_branches"] += len(st.parallel)
            if st.matrix:
                m["matrix_blocks"] += 1
                cells = 1
                for vals in st.matrix.axes.values():
                    cells *= max(1, len(vals))
                m["matrix_cells"] += cells
                m["matrix_axes"] += len(st.matrix.axes)
                if st.matrix.agent:
                    agents.append({"kind": st.matrix.agent.kind, "label": st.matrix.agent.label,
                                   "image": st.matrix.agent.image, "line": st.matrix.agent.line,
                                   "scope": f"matrix:{st.name}"})
            if st.when:
                m["when_conditions"] += len(st.when.conditions)
            if st.input:
                m["input_gates"] += 1
            m["post_conditions"] += len(st.post)
            m["env_vars"] += len(st.environment)
            m["tools"] += len(st.tools)
        m["top_level_stages"] = len([s for s in ir.stages if s.name or ir.dialect == "declarative"])
        m["post_conditions"] += len(ir.post)
        m["env_vars"] += len(ir.environment)
        m["parameters"] = len(ir.parameters)
        m["triggers"] = len(ir.triggers)
        m["options"] = len(ir.options)
        m["tools"] += len(ir.tools)
        m["libraries"] = len(ir.libraries)

    for stmt in _all_statements(ast):
        k = stmt.get("k")
        if k in ("for", "while"):
            m["loops"] += 1
        elif k in ("if", "switch"):
            m["conditionals"] += 1
        elif k == "try":
            m["try_catch"] += 1
        elif k == "call" and stmt.get("name") in ("each", "eachWithIndex", "collect", "collectEntries", "findAll"):
            m["loops"] += 1
    m["methods"] = len(ast.get("methods", []))
    m["classes"] = len(ast.get("classes", []))
    m["loc"] = sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("//"))
    m["steps"] = sum(e["count"] for e in steps.values())
    m["distinct_steps"] = len(steps)
    m["unknown_steps"] = len(unknown)
    m["credentials"] = len(creds)
    return {
        "metrics": dict(sorted(m.items())),
        "steps": dict(sorted(steps.items(), key=lambda kv: -kv[1]["count"])),
        "unknown_steps": [{"name": k, "lines": v[:10], "count": len(v)} for k, v in sorted(unknown.items())],
        "agents": agents,
        "credentials": list(creds.values()),
        "symbols": sorted(symbols),
        "calls": calls,
    }


def _all_statements(ast: dict):
    yield from walk_statements(ast.get("statements", []))
    for mth in ast.get("methods", []):
        yield from walk_statements(mth.get("body", []))
    for cls in ast.get("classes", []):
        for mth in cls.get("methods", []):
            yield from walk_statements(mth.get("body", []))


# --------------------------------------------------------------------------- findings
def _finding(fid: str, severity: str, line: int | None, evidence: str, recommendation: str,
             gate: bool = False) -> dict[str, Any]:
    f = {"id": fid, "severity": severity, "line": line, "evidence": evidence, "recommendation": recommendation}
    if gate:
        f["gate"] = True
    return f


def find_issues(text: str, ast: dict, ir: Pipeline | None, inv: dict, dialect: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if dialect == "unparseable":
        errs = ast.get("errors", [])
        e0 = errs[0] if errs else {}
        out.append(_finding("ParseError", "high", e0.get("line"), str(e0.get("message", ""))[:300],
                            "Groovy parser (Jenkins' Groovy 2.4) rejects the file; fix before migration", gate=True))
        return out
    if dialect == "scripted":
        out.append(_finding("ScriptedPipeline", "high", None, "node {}/stage() scripted pipeline",
                            "Re-model as Declarative or design GHA jobs around intent; automated conversion is best-effort",
                            gate=False))
    if dialect in ("library-call", "library-step"):
        out.append(_finding("OpaqueLibraryEntrypoint", "high", None,
                            "pipeline behaviour lives in a shared library / custom DSL call",
                            "Analyse the library implementation; target a reusable workflow", gate=True))
    if dialect == "library-template":
        out.append(_finding("LibraryTemplate", "medium", None, "Declarative pipeline defined in a shared-library var",
                            "Convert to a reusable workflow (on: workflow_call) with explicit inputs"))
    if ir and ir.libraries:
        out.append(_finding("SharedLibrary", "high", None, ", ".join(ir.libraries),
                            "Library steps are opaque to static analysis; map them to composite actions/reusable workflows",
                            gate=bool(inv["unknown_steps"])))
    for pat in catalog.hard_gate_patterns():
        for i, line in enumerate(text.splitlines(), 1):
            if pat["pattern"] in line and not line.strip().startswith("//"):
                out.append(_finding("JenkinsApiCoupling", "high", i, line.strip()[:160], pat["reason"] +
                                    " - no GHA equivalent; redesign required", gate=True))
                break
    for ctx in inv["calls"]:
        n = ctx.name
        node = ctx.node
        if n in ("load", "evaluate"):
            out.append(_finding("ExternalGroovyLoad", "high", ctx.line, f"{n}({value_text(first_arg(node))})",
                                "Inline the loaded logic as scripts/composite actions", gate=True))
        elif n == "parallel" and "pipeline" not in ctx.path[-1:] and node.get("args") and not node.get("named"):
            a0 = node["args"][0]
            if a0.get("t") in ("var", "expr", "call", "prop"):
                out.append(_finding("DynamicParallel", "high", ctx.line, f"parallel({value_text(a0)})",
                                    "Emit a bounded matrix from a planning job (fromJSON) instead of runtime fan-out",
                                    gate=True))
        elif n == "stage" and ctx.in_loop:
            out.append(_finding("DynamicStageGeneration", "high", ctx.line, "stage() created inside a loop",
                                "Enumerate the stages statically or use strategy.matrix", gate=True))
        elif n == "node" and node.get("args") and node["args"][0].get("t") in ("var", "gstr", "expr", "prop"):
            out.append(_finding("DynamicAgentLabel", "medium", ctx.line, f"node({value_text(node['args'][0])})",
                                "Choose runs-on via matrix/inputs"))
        elif n == "input":
            out.append(_finding("InputGate", "medium", ctx.line, "input step",
                                "Split the workflow at the gate and use a protected GitHub Environment"))
        elif n == "build" and ("job" in node.get("named", {})):
            out.append(_finding("DownstreamBuild", "medium", ctx.line, f"build job: {value_text(node['named']['job'])}",
                                "Use workflow_call (reusable workflow) or workflow_dispatch/repository_dispatch"))
        elif n == "podTemplate":
            out.append(_finding("KubernetesPodTemplate", "medium", ctx.line, "podTemplate",
                                "Use job container + services, or ARC runner scale sets"))
        elif n == "copyArtifacts":
            out.append(_finding("CrossJobArtifacts", "medium", ctx.line, "copyArtifacts",
                                "download-artifact with run-id / workflow_run"))
    if ir:
        for st, _ in ir.iter_stages():
            if st.input:
                out.append(_finding("InputGate", "medium", st.input.get("line"), f"stage '{st.name}' input directive",
                                    "Use a protected GitHub Environment on a separate job"))
            for cond in _flatten_conditions(st.when.conditions if st.when else []):
                if cond.kind == "expression":
                    out.append(_finding("GroovyWhenExpression", "medium", cond.line, (cond.text or "")[:160],
                                        "Re-express as a GHA if: expression or a step output"))
                elif cond.kind in ("changeset", "changelog"):
                    out.append(_finding("ChangesetCondition", "low", cond.line, str(cond.value),
                                        "Use on.push.paths or a changed-files step"))
                elif cond.kind == "unknown":
                    out.append(_finding("UnknownWhenCondition", "medium", cond.line, str(cond.text),
                                        "Manual mapping needed"))
            if st.agent and st.agent.kind == "kubernetes":
                out.append(_finding("KubernetesAgent", "medium", st.agent.line, "agent { kubernetes }",
                                    "Use job container + services, or ARC runner scale sets"))
        if ir.agent and ir.agent.kind == "kubernetes":
            out.append(_finding("KubernetesAgent", "medium", ir.agent.line, "agent { kubernetes }",
                                "Use job container + services, or ARC runner scale sets"))
        posts = list(ir.post.keys()) + [c for st, _ in ir.iter_stages() for c in st.post.keys()]
        for cond in sorted(set(posts) & {"changed", "fixed", "regression", "unstable", "notBuilt"}):
            out.append(_finding("PostConditionGap", "low", None, f"post {{ {cond} }}",
                                "No GHA equivalent (needs previous-run status / UNSTABLE); approximated or dropped"))
        for t in ir.triggers:
            if t.kind == "upstream":
                out.append(_finding("UpstreamTrigger", "medium", t.line, str(t.value), "Use on.workflow_run"))
            elif t.kind == "pollSCM":
                out.append(_finding("PollSCM", "low", t.line, str(t.value), "Replace polling with on.push"))
            elif t.kind == "cron" and isinstance(t.value, str) and "H" in t.value:
                out.append(_finding("HashedCron", "low", t.line, t.value, "GHA cron has no H; pick fixed minutes"))
        for p in ir.parameters:
            if p.kind in ("password", "file", "run", "credentials"):
                out.append(_finding("UnsupportedParameterType", "medium", p.line, f"{p.kind} {p.name}",
                                    "workflow_dispatch inputs support string/boolean/choice/number/environment only"))
        if ir.tools:
            out.append(_finding("ToolsDirective", "low", None, ", ".join(f"{k} '{v}'" for k, v in ir.tools.items()),
                                "Map Jenkins global tool names to actions/setup-* versions"))
    for u in inv["unknown_steps"]:
        out.append(_finding("UnknownStep", "medium", u["lines"][0] if u["lines"] else None,
                            f"{u['name']} x{u['count']}",
                            "Plugin or shared-library step with no catalog mapping - inspect implementation"))
    if inv["metrics"].get("script_blocks"):
        out.append(_finding("ScriptBlocks", "medium" if inv["metrics"].get("script_statements", 0) > 5 else "low", None,
                            f"{inv['metrics']['script_blocks']} script{{}} block(s), "
                            f"{inv['metrics'].get('script_statements', 0)} Groovy statements",
                            "Move imperative logic into versioned shell/Python scripts or composite actions"))
    for c in inv["credentials"]:
        out.append(_finding("CredentialBinding", "low", c["lines"][0] if c.get("lines") else None,
                            f"{c['type']} '{c['id']}'", "Create GitHub secret(s) or use OIDC; never inline values"))
    if re.search(r"\b(bat|powershell)\s*[\('\"]", text) or any(
            (a.get("label") or "").lower().startswith("win") for a in inv["agents"]):
        out.append(_finding("WindowsAgent", "low", None, "bat/powershell or windows label",
                            "Target runs-on: windows-latest (2x minute multiplier on private repos)"))
    return out


def _flatten_conditions(conds):
    for c in conds or []:
        yield c
        yield from _flatten_conditions(c.children)


# --------------------------------------------------------------------------- styles
def detect_styles(dialect: str, inv: dict, ir: Pipeline | None) -> list[str]:
    s: list[str] = []
    m = inv["metrics"]
    steps = inv["steps"]
    if dialect == "declarative":
        s.append("declarative")
    if dialect == "scripted":
        s.append("scripted")
    if dialect == "library-template":
        s += ["library-template", "declarative"]
    if dialect in ("library-call", "library-step") or (ir and ir.libraries) or "library" in steps:
        s.append("shared-library")
    if m.get("when_conditions") or m.get("post_conditions"):
        s.append("when-post")
    if m.get("parallel_branches") or "parallel" in steps:
        s.append("parallel")
    if m.get("matrix_blocks"):
        s.append("matrix")
    kinds = {a.get("kind") for a in inv["agents"]}
    if kinds & {"docker", "dockerfile"} or any(k.startswith("docker.") for k in steps):
        s.append("docker-agent")
    if "kubernetes" in kinds or "podTemplate" in steps:
        s.append("kubernetes-agent")
    if m.get("input_gates"):
        s.append("input-gate")
    if inv["credentials"] or "withCredentials" in steps:
        s.append("credentials")
    if m.get("parameters") or m.get("triggers") or "properties" in steps:
        s.append("parameters-triggers")
    if m.get("artifact_steps"):
        s.append("artifacts-tests")
    if m.get("downstream_builds"):
        s.append("downstream-build")
    if m.get("loads") or m.get("script_statements", 0) >= 15 or any(
            st in steps for st in ("evaluate",)) or (dialect == "scripted" and m.get("loops")):
        s.append("dynamic-groovy")
    if any(k in steps for k in ("bat", "powershell")):
        s.append("windows")
    if m.get("tools") or "tool" in steps:
        s.append("tools")
    return list(dict.fromkeys(s))


# --------------------------------------------------------------------------- scoring
def coverage(inv: dict) -> dict[str, Any]:
    by_cat = Counter()
    num = den = 0.0
    for name, e in inv["steps"].items():
        by_cat[e["category"]] += e["count"]
        w = catalog.weight(name) if e["category"] not in ("groovy", "local") else 0.5
        w = max(w, 0.25)
        num += w * e["count"] * CREDIT.get(e["category"], 0)
        den += w * e["count"]
    pct = round(100 * num / den, 1) if den else 100.0
    return {"by_category": dict(by_cat), "weighted_mapped_pct": pct}


def complexity(result: dict, inv: dict) -> dict[str, Any]:
    m = inv["metrics"]
    dialect = result["dialect"]
    steps = inv["steps"]
    dims: dict[str, float] = {}
    base = {"declarative": 0, "library-template": 6, "scripted": 13, "library-call": 12, "library-step": 12,
            "unknown": 18, "unparseable": 20}.get(dialect, 15)
    dims["declarative_structure"] = min(20, base + min(10, 2 * m.get("script_blocks", 0) +
                                                       0.25 * m.get("script_statements", 0)))
    dims["step_mapping"] = round(25 * (1 - result["coverage"]["weighted_mapped_pct"] / 100), 1)
    policy_distinct = sum(1 for e in steps.values() if e["category"] in ("policy", "redesign"))
    dims["plugin_coupling"] = min(15, 3 * m.get("unknown_steps", 0) + 0.75 * policy_distinct)
    lib = 0.0
    if result["libraries"] or dialect in ("library-call", "library-step"):
        lib = 9 + 2 * m.get("unknown_steps", 0)
    elif m.get("unknown_steps", 0) >= 3:
        lib = 4
    dims["library_opacity"] = min(15, lib)
    env = 0.0
    kinds = [a.get("kind") for a in inv["agents"]]
    env += 2 * min(2, sum(1 for a in inv["agents"] if a.get("kind") == "label" and a.get("label") and
                         a["label"] not in ("linux", "any", "master", "built-in", "docker")))
    env += 2 if "docker" in kinds else 0
    env += 3 if "dockerfile" in kinds else 0
    env += 6 if "kubernetes" in kinds else 0
    env += 2 if any(k in steps for k in ("bat", "powershell")) else 0
    env += min(3, m.get("tools", 0))
    dims["runtime_coupling"] = min(10, env)
    sec = min(6, 2 * m.get("credentials", 0)) + (3 if m.get("input_gates") else 0)
    sec += 3 if any(k in steps for k in ("withAWS", "azureCLI", "withVault", "withKubeConfig")) else 0
    dims["security_identity"] = min(10, sec)
    cf = 0.0
    cf += 3 if any(f["id"] in ("DynamicParallel", "DynamicStageGeneration") for f in result["findings"]) else 0
    cf += 1 if m.get("loops") else 0
    cf += 1 if m.get("try_catch") else 0
    cf += 1 if m.get("matrix_blocks") else 0
    cf += 1 if m.get("max_stage_depth", 0) > 2 else 0
    cf += 1 if m.get("parallel_blocks", 0) > 1 else 0
    dims["control_flow"] = min(5, cf)
    score = round(sum(dims.values()))
    gates = [f["id"] for f in result["findings"] if f.get("gate")]
    if gates:
        score = max(score, 46)
    if score <= 20:
        cls = "straightforward"
    elif score <= 45:
        cls = "assisted"
    elif score <= 70:
        cls = "significant-redesign"
    else:
        cls = "rebuild-around-intent"
    return {"score": score, "classification": cls, "dimensions": {k: round(v, 1) for k, v in dims.items()},
            "hard_gates": sorted(set(gates)),
            "weights": {"declarative_structure": 20, "step_mapping": 25, "plugin_coupling": 15, "library_opacity": 15,
                        "runtime_coupling": 10, "security_identity": 10, "control_flow": 5}}


def convertibility(result: dict) -> str:
    d = result["dialect"]
    if d in ("unparseable", "library-call", "library-step", "unknown"):
        return "report-only"
    if result["complexity"]["hard_gates"]:
        return "partial"
    if d == "scripted":
        return "partial"
    return "automatic" if result["complexity"]["score"] <= 45 else "partial"


# --------------------------------------------------------------------------- Jenkins model cross-check
def summarise_jenkins_model(model: dict, ir: Pipeline | None) -> dict[str, Any]:
    """Fold in Jenkins' authoritative toJson result and diff stage structure with our IR."""
    res = model.get("result")
    out: dict[str, Any] = {"result": res, "errors": []}
    if res != "success":
        for e in model.get("errors", []):
            err = e.get("error")
            out["errors"].extend(err if isinstance(err, list) else [str(err)])
        return out
    pipeline = model.get("json", {}).get("pipeline", {})

    def names(stages):
        acc = []
        for s in stages or []:
            acc.append(s.get("name"))
            acc.extend(names(s.get("parallel")))
            acc.extend(names(s.get("stages")))
            if s.get("matrix"):
                acc.extend(names(s["matrix"].get("stages")))
        return acc

    jstages = names(pipeline.get("stages"))
    out["stages"] = jstages
    out["agent"] = (pipeline.get("agent") or {}).get("type")
    disc = []
    if ir is not None:
        ours = [s.name for s, _ in ir.iter_stages()]
        if ours != jstages:
            disc.append(f"stage list differs: jenkins={jstages} j2gha={ours}")
    out["discrepancies"] = disc
    return out
