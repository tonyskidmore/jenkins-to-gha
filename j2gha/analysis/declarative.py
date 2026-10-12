"""Interpret the Groovy AST of a Jenkinsfile into the canonical IR (``j2gha.ir``).

Declarative pipelines are interpreted structurally (directive by directive). Scripted pipelines get a
best-effort interpretation: ``node``/``stage``/literal ``parallel`` blocks become stages, everything else
is retained as steps, and dynamic constructs are flagged in ``Pipeline.notes``.

Jenkins' own Declarative model (``/pipeline-model-converter/toJson``) is used as an authoritative
cross-check of this interpretation - see ``analysis.jenkins_model``.
"""

from __future__ import annotations

import copy
from typing import Any

from ..ir import Agent, Condition, EnvValue, Matrix, Parameter, Pipeline, Stage, Step, Trigger, When
from .ast import child_calls, first_arg, literal, unchain, value_text, walk_statements
from .catalog import GROOVY_METHODS, categorise

POST_CONDITIONS = ["always", "changed", "fixed", "regression", "aborted", "failure", "success", "unstable",
                   "unsuccessful", "notBuilt", "cleanup"]


# --------------------------------------------------------------------------- entry points
def find_pipeline_call(ast: dict) -> tuple[dict | None, str | None]:
    """Locate the top-level ``pipeline {}`` call (or one inside a shared-library ``call`` method)."""
    for s in ast.get("statements", []):
        if s.get("k") == "call" and s.get("name") == "pipeline" and s.get("body") is not None:
            return s, None
    for m in ast.get("methods", []):
        for s in _walk_shallow(m.get("body", [])):
            if s.get("k") == "call" and s.get("name") == "pipeline" and s.get("body") is not None:
                return s, m.get("name")
    return None, None


def _walk_shallow(stmts: list[dict], depth: int = 0):
    for s in stmts or []:
        yield s
        if depth < 4:
            for key in ("then", "else", "body"):
                if isinstance(s.get(key), list) and s.get("k") != "call":
                    yield from _walk_shallow(s[key], depth + 1)


def build_ir(ast: dict) -> Pipeline | None:
    if not ast.get("ok"):
        return None
    call, method = find_pipeline_call(ast)
    methods = [m.get("name") for m in ast.get("methods", [])]
    libraries = _libraries(ast)
    method_defs = {m.get("name"): {"params": [x.get("name") for x in m.get("params", [])],
                                   "body": parse_script_body(m.get("body"))}
                   for m in ast.get("methods", []) if m.get("name") != (method or "")}
    if call is not None:
        p = interpret_declarative(call)
        p.methods = methods
        p.method_defs = method_defs
        p.libraries = libraries
        if method:
            p.notes.append(f"pipeline {{}} is defined inside shared-library method '{method}()'")
        p.constants = script_constants(ast)
        return p
    p = interpret_scripted(ast)
    p.methods = methods
    p.method_defs = method_defs
    p.libraries = libraries
    p.constants = script_constants(ast)
    return p


def script_constants(ast: dict) -> dict[str, str]:
    """Top-level ``NAME = 'literal'`` script bindings assigned nowhere else: their value is fixed for the whole run."""
    counts: dict[str, int] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            name = node.get("target") if node.get("k") == "assign" else node.get("name") if node.get("k") == "decl" else None
            if isinstance(name, str):
                counts[name] = counts.get(name, 0) + 1
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(ast.get("statements"))
    walk(ast.get("methods"))
    walk(ast.get("classes"))
    out: dict[str, str] = {}
    for s in ast.get("statements", []):
        value = s.get("value") or {}
        if (s.get("k") == "assign" and s.get("op") == "=" and isinstance(s.get("target"), str)
                and value.get("t") == "str" and counts.get(s["target"]) == 1):
            out[s["target"]] = str(value.get("v"))
    return out


def _libraries(ast: dict) -> list[str]:
    libs = []
    for a in ast.get("annotations", []):
        if a.get("name") == "Library":
            v = literal(a.get("members", {}).get("value"))
            if isinstance(v, list):
                libs.extend(str(x) for x in v)
            elif v:
                libs.append(str(v))
    for s in ast.get("statements", []):
        if s.get("k") == "call" and s.get("name") == "library":
            v = first_arg(s, "identifier")
            libs.append(value_text(v) or "?")
    return libs


# --------------------------------------------------------------------------- declarative
def interpret_declarative(call: dict) -> Pipeline:
    p = Pipeline(dialect="declarative", line=call.get("line"))
    for d in child_calls(call.get("body")):
        name = d.get("name")
        if name == "agent":
            p.agent = parse_agent(d)
        elif name == "environment":
            p.environment = parse_environment(d)
        elif name == "options":
            p.options = parse_options(d, p.notes)
        elif name == "parameters":
            p.parameters = parse_parameters(d)
        elif name == "triggers":
            p.triggers = parse_triggers(d)
        elif name == "tools":
            p.tools = parse_tools(d)
        elif name == "stages":
            p.stages = parse_stages(d, p.notes)
        elif name == "post":
            p.post = parse_post(d)
        elif name == "libraries":
            for lib in child_calls(d.get("body"), "lib"):
                p.libraries.append(value_text(first_arg(lib)))
        else:
            p.notes.append(f"line {d.get('line')}: unrecognised pipeline directive '{name}'")
    for s in call.get("body") or []:
        if s.get("k") != "call":
            p.notes.append(f"line {s.get('line')}: non-directive statement inside pipeline {{}} ({s.get('k')})")
    return p


def parse_agent(d: dict) -> Agent:
    line = d.get("line")
    a0 = first_arg(d)
    if a0 is not None and not d.get("body"):
        v = value_text(a0)
        if a0.get("t") == "var" and v in ("any", "none"):
            return Agent(kind=v, line=line)
        if a0.get("t") == "var":
            return Agent(kind="any" if v == "any" else v, line=line)
        return Agent(kind="label", label=v, line=line)
    body = d.get("body") or []
    for c in child_calls(body):
        n = c.get("name")
        if n in ("any", "none"):
            return Agent(kind=n, line=line)
        if n == "label":
            return Agent(kind="label", label=value_text(first_arg(c)), line=line)
        if n == "node":
            props = _props(c)
            return Agent(kind="label", label=str(props.get("label") or value_text(first_arg(c, "label")) or ""),
                         raw=props, line=line)
        if n in ("docker", "dockerfile", "kubernetes", "dockerContainer"):
            props = _props(c)
            ag = Agent(kind="kubernetes" if n == "kubernetes" else ("docker" if n != "dockerfile" else "dockerfile"),
                       raw=props, line=line)
            if n in ("docker", "dockerContainer"):
                ag.image = str(props.get("image") or value_text(first_arg(c, "image")) or "") or None
            ag.args = props.get("args")
            ag.label = props.get("label")
            ag.reuse_node = bool(props.get("reuseNode"))
            if n == "dockerfile":
                ag.filename = props.get("filename") or "Dockerfile"
                ag.dir = props.get("dir")
            if n == "kubernetes":
                ag.yaml = props.get("yaml") or props.get("yamlFile")
                ag.image = None
            return ag
    # agent { label 'x' } handled above; unknown shapes:
    return Agent(kind="unknown", raw={"text": str(body)[:200]}, line=line)


def _props(c: dict) -> dict[str, Any]:
    """Collect `key value` style sub-directives and named args into a dict of literals/text."""
    props: dict[str, Any] = {}
    for k, v in c.get("named", {}).items():
        props[k] = literal(v) if literal(v) is not None else value_text(v)
    if c.get("args") and not c.get("body"):
        props.setdefault("_arg", value_text(c["args"][0]))
    for sub in child_calls(c.get("body")):
        a0 = first_arg(sub)
        val = literal(a0)
        props[sub.get("name")] = val if val is not None else (value_text(a0) if a0 else True)
    return props


def parse_environment(d: dict) -> dict[str, EnvValue]:
    env: dict[str, EnvValue] = {}
    for s in d.get("body") or []:
        if s.get("k") != "assign":
            continue
        name = s.get("target")
        v = s.get("value") or {}
        call = v["call"] if v.get("t") == "call" else None
        if call is not None and call.get("name") == "trim" and call.get("receiverCalls"):
            call = call["receiverCalls"][0] if call["receiverCalls"][0].get("k") == "call" else call
        if call is not None and call.get("name") == "credentials":
            env[name] = EnvValue(kind="credentials", credential_id=value_text(first_arg(call)), line=s.get("line"))
        elif call is not None and call.get("name") in ("sh", "bat") and (
                literal(call.get("named", {}).get("returnStdout")) or not call.get("named")):
            env[name] = EnvValue(kind="shell", value=value_text(first_arg(call, "script")), line=s.get("line"))
        elif call is not None and not call.get("receiver") and call.get("name") not in ("trim",):
            # value computed by a (library/plugin) function call: runtime-only
            env[name] = EnvValue(kind="call", value=call.get("name"), line=s.get("line"))
        elif literal(v) is not None:
            env[name] = EnvValue(kind="literal", value=literal(v), line=s.get("line"))
        else:
            env[name] = EnvValue(kind="expression", value=value_text(v), line=s.get("line"))
    return env


def parse_options(d: dict, notes: list[str]) -> dict[str, Any]:
    opts: dict[str, Any] = {}
    for c in child_calls(d.get("body")):
        n = c.get("name")
        if n == "timeout":
            t = literal(c.get("named", {}).get("time")) or literal(first_arg(c))
            unit = literal(c.get("named", {}).get("unit")) or "MINUTES"
            opts["timeout"] = {"time": t, "unit": unit, "minutes": _to_minutes(t, unit)}
        elif n == "retry":
            opts["retry"] = literal(first_arg(c, "count")) or value_text(first_arg(c))
        elif n in ("buildDiscarder",):
            opts["buildDiscarder"] = value_text(first_arg(c))
        else:
            args = [literal(a) if literal(a) is not None else value_text(a) for a in c.get("args", [])]
            named = {k: (literal(v) if literal(v) is not None else value_text(v)) for k, v in c.get("named", {}).items()}
            opts[n] = named or (args[0] if len(args) == 1 else args) or True
    return opts


def _to_minutes(t: Any, unit: str) -> int | None:
    try:
        t = float(t)
    except (TypeError, ValueError):
        return None
    unit = str(unit).upper()
    factor = {"SECONDS": 1 / 60, "MINUTES": 1, "HOURS": 60, "DAYS": 1440, "MILLISECONDS": 1 / 60000}.get(unit, 1)
    return max(1, int(round(t * factor)))


def parse_parameters(d: dict) -> list[Parameter]:
    return [_parameter(c.get("name"), c.get("named", {}), first_arg(c), c.get("line")) for c in child_calls(d.get("body"))]


# Map-form parameter definitions name their class: [$class: 'ChoiceParameterDefinition', name: ..., choices: ...]
PARAMETER_CLASSES = {"StringParameterDefinition": "string", "BooleanParameterDefinition": "booleanParam",
                     "ChoiceParameterDefinition": "choice", "TextParameterDefinition": "text",
                     "PasswordParameterDefinition": "password"}


def _parameter(kind: str | None, named: dict, a0: Any, line: int | None) -> Parameter:
    name = value_text(named.get("name")) if named.get("name") else value_text(a0)
    choices = literal(named.get("choices")) or []
    if isinstance(choices, str):
        choices = [x for x in choices.splitlines() if x]
    return Parameter(kind=kind or "other", name=name or "?", default=literal(named.get("defaultValue")),
                     choices=list(choices) if isinstance(choices, list) else [],
                     description=literal(named.get("description")), line=line)


def parse_triggers(d: dict) -> list[Trigger]:
    out = []
    for c in child_calls(d.get("body")):
        n = c.get("name")
        v = literal(first_arg(c, "spec", "upstreamProjects"))
        out.append(Trigger(kind=n if n in ("cron", "pollSCM", "upstream") else "other",
                           value=v if v is not None else {"step": n, "text": value_text(first_arg(c))},
                           line=c.get("line")))
    return out


def parse_tools(d: dict) -> dict[str, str]:
    tools = {}
    for c in child_calls(d.get("body")):
        tools[c.get("name")] = value_text(first_arg(c))
    return tools


def parse_stages(d: dict, notes: list[str]) -> list[Stage]:
    out = []
    for c in d.get("body") or []:
        if c.get("k") == "call" and c.get("name") == "stage":
            out.append(parse_stage(c, notes))
        else:
            notes.append(f"line {c.get('line')}: unexpected statement in stages {{}} ({c.get('k')} {c.get('name', '')})")
    return out


def parse_stage(c: dict, notes: list[str]) -> Stage:
    name = value_text(first_arg(c, "name")) or "?"
    st = Stage(name=name, line=c.get("line"))
    for d in child_calls(c.get("body")):
        n = d.get("name")
        if n == "steps":
            st.steps = parse_steps(d.get("body"))
        elif n == "agent":
            st.agent = parse_agent(d)
        elif n == "environment":
            st.environment = parse_environment(d)
        elif n == "options":
            st.options = parse_options(d, notes)
        elif n == "when":
            st.when = parse_when(d)
        elif n == "tools":
            st.tools = parse_tools(d)
        elif n == "input":
            st.input = _props(d)
            st.input["line"] = d.get("line")
        elif n == "parallel":
            st.parallel = [parse_stage(x, notes) for x in child_calls(d.get("body"), "stage")]
        elif n == "stages":
            st.stages = parse_stages(d, notes)
        elif n == "matrix":
            st.matrix = parse_matrix(d, notes)
        elif n == "post":
            st.post = parse_post(d)
        elif n == "failFast":
            st.fail_fast = bool(literal(first_arg(d)))
        else:
            notes.append(f"line {d.get('line')}: unrecognised stage directive '{n}' in stage '{name}'")
    return st


def parse_matrix(d: dict, notes: list[str]) -> Matrix:
    m = Matrix(line=d.get("line"))
    for c in child_calls(d.get("body")):
        n = c.get("name")
        if n == "axes":
            for ax in child_calls(c.get("body"), "axis"):
                props = {s.get("name"): s for s in child_calls(ax.get("body"))}
                axis_name = value_text(first_arg(props["name"])) if "name" in props else "?"
                values = [literal(v) if literal(v) is not None else value_text(v)
                          for v in (props["values"].get("args", []) if "values" in props else [])]
                m.axes[axis_name] = values
        elif n == "excludes":
            for ex in child_calls(c.get("body"), "exclude"):
                rule: dict[str, Any] = {}
                for ax in child_calls(ex.get("body"), "axis"):
                    props = {s.get("name"): s for s in child_calls(ax.get("body"))}
                    axis_name = value_text(first_arg(props["name"])) if "name" in props else "?"
                    if "values" in props:
                        rule[axis_name] = {"values": [literal(v) for v in props["values"].get("args", [])]}
                    if "notValues" in props:
                        rule[axis_name] = {"notValues": [literal(v) for v in props["notValues"].get("args", [])]}
                m.excludes.append(rule)
        elif n == "agent":
            m.agent = parse_agent(c)
        elif n == "stages":
            m.stages = parse_stages(c, notes)
        elif n == "when":
            m.when = parse_when(c)
        elif n == "post":
            m.post = parse_post(c)
        elif n == "environment":
            m.environment = parse_environment(c)
        elif n == "options":
            m.options = parse_options(c, notes)
        elif n == "input":
            m.input = {**_props(c), "line": c.get("line")}
        elif n == "tools":
            m.tools = parse_tools(c)
        else:
            notes.append(f"line {c.get('line')}: unrecognised matrix directive '{n}'")
    return m


def parse_when(d: dict) -> When:
    w = When()
    for c in child_calls(d.get("body")):
        n = c.get("name")
        if n == "beforeAgent":
            w.before_agent = bool(literal(first_arg(c)))
        elif n == "beforeInput":
            w.before_input = bool(literal(first_arg(c)))
        elif n == "beforeOptions":
            w.before_options = bool(literal(first_arg(c)))
        else:
            w.conditions.append(parse_condition(c))
    return w


def parse_condition(c: dict) -> Condition:
    n = c.get("name")
    line = c.get("line")
    if n in ("allOf", "anyOf", "not"):
        return Condition(kind=n, children=[parse_condition(x) for x in child_calls(c.get("body"))], line=line)
    if n in ("branch", "tag"):
        v = first_arg(c, "pattern")
        cmp = literal(c.get("named", {}).get("comparator"))
        return Condition(kind=n, value=value_text(v) if v else None, comparator=cmp, line=line)
    if n == "environment":
        return Condition(kind=n, name=value_text(c.get("named", {}).get("name")),
                         value=value_text(c.get("named", {}).get("value")), line=line)
    if n == "expression":
        src = ""
        body = c.get("body") or []
        if body:
            src = "; ".join(_stmt_text(s) for s in body)
        return Condition(kind=n, text=src, line=line)
    if n == "equals":
        def src(v):  # keep string literals quoted so the expression translator sees literals
            lit = literal(v)
            return "'" + str(lit).replace("'", "\\'") + "'" if isinstance(lit, str) else value_text(v)
        return Condition(kind=n, value={"expected": src(c.get("named", {}).get("expected")),
                                        "actual": src(c.get("named", {}).get("actual"))}, line=line)
    if n in ("buildingTag", "changeRequest", "changeset", "changelog", "triggeredBy", "isRestartedRun"):
        args = {k: value_text(v) for k, v in c.get("named", {}).items()}
        if c.get("args"):
            args["_"] = value_text(c["args"][0])
        return Condition(kind=n, value=args or None, line=line)
    return Condition(kind="unknown", text=n, line=line)


def _stmt_text(s: dict) -> str:
    if s.get("k") == "return":
        v = s.get("value") or {}
        return "return " + (_call_text(v["call"]) if v.get("t") == "call" and v.get("call") else value_text(v))
    if s.get("k") == "expr":
        return s.get("text", "")
    if s.get("k") == "call":
        return _call_text(s)
    return s.get("text", s.get("k", ""))


def _call_text(c: dict) -> str:
    """`params.V.endsWith('-SNAPSHOT')` with literal arguments kept quoted for the expression translator; calls
    with closure or named arguments stay opaque (`name(...)`)."""
    args = c.get("args") or []
    if c.get("named") or any(a.get("t") in ("closure", "call", "map", "list") for a in args):
        rendered = "..."
    else:
        rendered = ", ".join("'" + str(literal(a)).replace("'", "\\'") + "'" if isinstance(literal(a), str)
                             else value_text(a) for a in args)
    return f"{c['receiver'] + '.' if c.get('receiver') else ''}{c.get('name')}({rendered})"


def parse_post(d: dict) -> dict[str, list[Step]]:
    post: dict[str, list[Step]] = {}
    for c in child_calls(d.get("body")):
        post[c.get("name")] = parse_steps(c.get("body"))
    return post


# --------------------------------------------------------------------------- steps
def parse_steps(body: list[dict] | None) -> list[Step]:
    steps: list[Step] = []
    for s in body or []:
        if s.get("k") == "call":
            steps.extend(parse_step(c) for c in unchain(s))
        else:
            # Groovy statements directly in steps{} are not valid Declarative; keep as dynamic.
            steps.append(Step(name=f"<{s.get('k')}>", line=s.get("line"), category="dynamic",
                              source=s.get("text") or s.get("cond") or s.get("k"), dynamic=True))
    return steps


# Map-form credentials bindings name their class; the symbol form names the binding. Both reach the IR as the symbol.
BINDING_CLASSES = {"UsernamePasswordMultiBinding": "usernamePassword", "UsernamePasswordBinding": "usernameColonPassword",
                   "StringBinding": "string", "FileBinding": "file", "SSHUserPrivateKeyBinding": "sshUserPrivateKey",
                   "ZipFileBinding": "zip", "CertificateMultiBinding": "certificate",
                   "AmazonWebServicesCredentialsBinding": "aws", "DockerServerCredentialsBinding": "dockerCert"}


def binding_type(class_name: str) -> str:
    return BINDING_CLASSES.get(class_name, class_name)


def parse_step(s: dict) -> Step:
    name = s.get("name", "")
    receiver = s.get("receiver")
    args = []
    variable_args = [i for i, a in enumerate(s.get("args", [])) if a.get("t") == "var"]
    dynamic = False
    for a in s.get("args", []):
        lit = literal(a)
        if lit is None and a.get("t") == "list":
            dynamic = True
            args.append([x if (x := literal(v)) is not None else {"expr": value_text(v)} for v in a.get("v", [])])
        elif lit is None:
            dynamic = dynamic or a.get("t") not in ("closure",)
            args.append(value_text(a))
        else:
            args.append(lit)
    named = {}
    closure_bodies: list[Step] = []
    for k, v in s.get("named", {}).items():
        if v.get("t") == "closure":
            # parallel branchA: { ... }, branchB: { ... } - branch bodies run (in the enclosing stage)
            closure_bodies.extend(parse_script_body(v.get("body")))
            named[k] = "{closure}"
            continue
        lit = literal(v)
        if lit is None:
            if v.get("t") not in ("list", "map", "call"):
                dynamic = True
            named[k] = value_text(v) if v.get("t") != "list" else [value_text(x) for x in v.get("v", [])]
        else:
            named[k] = lit
    step = Step(name=name, line=s.get("line"), args=args, named=named, receiver=_short_receiver(receiver),
                dynamic=dynamic, variable_args=variable_args)
    step.category = categorise(step.qualified if receiver else name)
    if receiver and step.category == "unknown":
        # e.g. sh(script: 'x', returnStdout: true).trim() -> the pipeline step is in the receiver chain
        inner = [parse_step(rc) for rc in s.get("receiverCalls", []) if rc.get("k") == "call"]
        if inner and (name in GROOVY_METHODS or receiver.startswith(inner[0].name)):
            inner[0].named.setdefault("_chain", name)
            return inner[0]
    if step.category == "unknown" and name in GROOVY_METHODS:
        step.category = "groovy"
    if name == "script":
        step.category = "dynamic"
        step.body = parse_script_body(s.get("body"))
        step.source = None
    elif s.get("body"):
        step.body = parse_script_body(s.get("body"))  # bodies may hold Groovy control flow (scripted pipelines)
    if closure_bodies:
        step.body = closure_bodies + step.body
    # credentials bindings inside withCredentials([...]) are list items of call values
    if name == "withCredentials":
        binds = []
        for a in s.get("args", []):
            for item in (a.get("v", []) if a.get("t") == "list" else []):
                if item.get("t") == "call":
                    bc = item["call"]
                    binds.append({"type": bc.get("name"),
                                  **{k: value_text(v) for k, v in bc.get("named", {}).items()}})
                elif item.get("t") == "map" and "$class" in (item.get("v") or {}):
                    # [$class: 'AmazonWebServicesCredentialsBinding', credentialsId: ..., accessKeyVariable: ...]
                    kv = {k: value_text(v) for k, v in item["v"].items()}
                    binds.append({"type": binding_type(kv.pop("$class")), **kv})
        step.named["bindings"] = binds
    return step


def parse_script_body(body: list[dict] | None) -> list[Step]:
    """Scripted Groovy inside script {}: keep calls as steps, control flow as dynamic markers."""
    out: list[Step] = []
    for s in body or []:
        k = s.get("k")
        if k == "call":
            out.extend(parse_step(c) for c in unchain(s))
        elif k == "if":
            out.append(Step(name="<if>", line=s.get("line"), category="dynamic", dynamic=True, source=s.get("cond"),
                            body=parse_script_body(s.get("then")),
                            named={"_else": parse_script_body(s.get("else"))} if s.get("else") else {}))
        elif k == "try":
            catches = []
            for c in s.get("catches", []) or []:
                catches.extend(parse_script_body(c.get("body")))
            named = {}
            if catches:
                named["_catch"] = catches
            if s.get("finally"):
                named["_finally"] = parse_script_body(s.get("finally"))
            out.append(Step(name="<try>", line=s.get("line"), category="dynamic", dynamic=True,
                            body=parse_script_body(s.get("body")), named=named))
        elif k in ("for", "while", "switch"):
            inner = []
            for key in ("then", "else", "body", "finally", "default"):
                if isinstance(s.get(key), list):
                    inner.extend(parse_script_body(s[key]))
            for c in s.get("catches", []) or []:
                inner.extend(parse_script_body(c.get("body")))
            for c in s.get("cases", []) or []:
                inner.extend(parse_script_body(c.get("body")))
            out.append(Step(name=f"<{k}>", line=s.get("line"), category="dynamic", dynamic=True,
                            source=s.get("cond") or s.get("collection") or s.get("expr"), body=inner))
        elif k in ("decl", "assign"):
            v = s.get("value") or {}
            inner = [parse_step(v["call"])] if v.get("t") == "call" else []
            target = str(s.get("name") or s.get("target") or "").strip()
            named = {"_target": target, **({"_literal": v["v"]} if v.get("t") == "str" else {}),
                     "_value": _strip_positions(v)}  # the right-hand side, for values the converter can carry on
            out.append(Step(name=f"<{k}>", line=s.get("line"), category="dynamic", dynamic=True,
                            source=f"{target} = {value_text(v)}", body=inner, named=named))
        else:
            out.append(Step(name=f"<{k}>", line=s.get("line"), category="dynamic", dynamic=True,
                            source=s.get("text")))
    return out


def _strip_positions(node: Any) -> Any:
    """An AST value without its source positions (they are on the step already)."""
    if isinstance(node, dict):
        return {k: _strip_positions(v) for k, v in node.items() if k not in ("line", "col", "endLine", "endCol")}
    if isinstance(node, list):
        return [_strip_positions(v) for v in node]
    return node


def _short_receiver(receiver: str | None) -> str | None:
    if not receiver:
        return None
    if receiver.startswith("docker"):
        return "docker" if receiver == "docker" else receiver
    return receiver


# --------------------------------------------------------------------------- scripted
# Block steps that, around stage() blocks, are re-applied inside every stage/segment they enclose: the generator
# handles each of them inside a stage (working-directory, step env, secrets, timeout-minutes, retry loop,
# continue-on-error, docker run wrapper, ...).
_SCOPE_WRAPPERS = frozenset({
    "dir", "withEnv", "withCredentials", "timeout", "retry", "catchError", "warnError", "wrap", "sshagent",
    "withDockerRegistry", "withMaven", "withGradle", "nodejs", "withPythonEnv", "configFileProvider", "lock",
    "withSonarQubeEnv", "withAWS", "withKubeConfig", "withVault", "azureCLI", "withDockerServer",
    "withDockerContainer", "container"})
_DOCKER_WRAPPERS = frozenset({"inside", "withRegistry"})  # docker.image('x').inside {}, docker.withRegistry(..) {}
_COSMETIC_WRAPPERS = frozenset({"timestamps", "ansiColor"})  # GitHub Actions logs are timestamped/coloured natively
# Jenkins applies these to the enclosed block as a whole; re-applied per enclosed step they are approximations.
_BLOCK_SEMANTICS = {
    "timeout": "Jenkins limits the whole block, each step gets its own timeout-minutes",
    "retry": "Jenkins re-runs the whole block, only individual run steps are retried",
    "catchError": "Jenkins skips the rest of the block after an error, each step gets continue-on-error",
    "warnError": "Jenkins skips the rest of the block after an error, each step gets continue-on-error",
    "lock": "the lock is not held across the enclosed stages - use a concurrency group",
}


class _Frame:
    """A scope enclosing stage() blocks, re-applied inside every stage/segment it encloses: a wrapper step (slot
    ``body``), or the catch (``_catch``: failure only) / finally (``_finally``: always) region of a ``try``, which
    the generator renders like an in-stage ``<try>`` statement with an empty body."""

    __slots__ = ("slot", "step")

    def __init__(self, step: Step, slot: str = "body"):
        self.step, self.slot = step, slot

    def wrap(self, steps: list[Step]) -> Step:
        out = copy.deepcopy(self.step)  # the template holds no body
        if self.slot == "body":
            out.body = steps
        else:
            out.named = {self.slot: steps}
        return out


def _wrap(frames: tuple[_Frame, ...], steps: list[Step]) -> list[Step]:
    """Nest ``steps`` in the enclosing scopes (outermost first)."""
    for f in reversed(frames):
        steps = [f.wrap(steps)]
    return steps


def _own_job(st: Stage) -> bool:
    """Mirrors ``convert.generator._plan``: such a stage never shares a job with its neighbours."""
    return bool(st.parallel or st.matrix or (st.agent and st.agent.kind not in ("none", "inherit")) or st.input)


def _quoted(names: list[str]) -> str:
    return ", ".join(f"'{n}'" for n in names[:6]) + (", ..." if len(names) > 6 else "")


def _rethrows(body: list[dict] | None) -> bool:
    """The catch body always ends the build: a `throw` / `error()` statement directly in it (not in an if)."""
    return any(s.get("k") == "throw" or (s.get("k") == "call" and s.get("name") == "error") for s in body or [])


class _ScriptedWalker:
    """Walks scripted statements in source order, emitting stages and anonymous segments into ``p.stages``."""

    def __init__(self, p: Pipeline):
        self.p = p
        self.strings: dict[str, str] = {}  # variables last assigned a string literal, for stage(stageName)
        self.groups: list[tuple[tuple[_Frame, ...], list[Step]]] = []  # the open anonymous segment, by scope
        self.seg_agent: Agent | None = None
        self.loose_count = 0

    # ----------------------------------------------------------------- helpers
    def stage_agent(self, agent: Agent | None) -> Agent | None:
        return agent if agent is not self.p.agent else None

    def stage_name(self, c: dict) -> str:
        a0 = first_arg(c, "name")
        return (self.strings.get(a0.get("name")) if a0 and a0.get("t") == "var" else None) or value_text(a0) or "?"

    def stage_names(self, stmts: list[dict] | None) -> list[str]:
        return [self.stage_name(s) for s in walk_statements(stmts or [])
                if s.get("k") == "call" and s.get("name") == "stage" and s.get("body") is not None]

    @staticmethod
    def structural(stmts: list[dict] | None) -> bool:
        """Holds a stage() block, a node {} (whose label sets the job's runner) or a literal parallel (jobs)."""
        def shaping(s: dict) -> bool:
            n = s.get("name")
            return n == "node" or (n == "stage" and s.get("body") is not None) or (
                n == "parallel" and any(v.get("t") == "closure" for v in (s.get("named") or {}).values()))
        return any(s.get("k") == "call" and not s.get("receiver") and shaping(s) for s in walk_statements(stmts or []))

    @staticmethod
    def is_wrapper(c: dict) -> bool:
        n, r = c.get("name"), c.get("receiver")
        if n in _DOCKER_WRAPPERS:
            return bool(r) and str(r).startswith("docker")
        return not r and (n in _SCOPE_WRAPPERS or n in _COSMETIC_WRAPPERS)

    # ----------------------------------------------------------------- output (source order)
    def loose(self, steps: list[Step], agent: Agent | None, frames: tuple[_Frame, ...]) -> None:
        if not steps:
            return
        key = self.stage_agent(agent)
        if self.groups and key is not self.seg_agent:
            self.flush()  # statements of another node {} form their own segment
        if not self.groups:
            self.seg_agent = key
        last = self.groups[-1][0] if self.groups else None
        if last is not None and len(last) == len(frames) and all(a is b for a, b in zip(last, frames, strict=True)):
            self.groups[-1][1].extend(steps)
        else:
            self.groups.append((frames, list(steps)))
        self.loose_count += len(steps)

    def flush(self) -> None:
        if not self.groups:
            return
        steps = [x for frames, body in self.groups for x in _wrap(frames, body)]
        self.p.stages.append(Stage(name="", line=self.groups[0][1][0].line, agent=self.seg_agent, steps=steps))
        self.groups = []

    def add_stage(self, st: Stage) -> None:
        self.flush()
        self.p.stages.append(st)

    # ----------------------------------------------------------------- statements
    def visit(self, stmts: list[dict] | None, agent: Agent | None, frames: tuple[_Frame, ...]) -> None:
        for s in stmts or []:
            k = s.get("k")
            if k == "call":
                for c in unchain(s):
                    self.call(c, agent, frames)
                continue
            if k == "try":
                self.try_(s, agent, frames)
                continue
            if k in ("decl", "assign", "expr"):
                var, v = s.get("target") if k == "assign" else s.get("name"), s.get("value") or {}
                if var and v.get("t") == "str" and s.get("op", "=") == "=":
                    self.strings[var] = v["v"]
                elif var:
                    self.strings.pop(var, None)
            names = self.stage_names([s])
            if names:
                self.p.notes.append(f"line {s.get('line')}: top-level {k} controls pipeline structure (dynamic): "
                                    f"stage(s) {_quoted(names)} kept as its nested steps, in an unnamed segment")
            self.loose(parse_script_body([s]), agent, frames)

    def call(self, c: dict, agent: Agent | None, frames: tuple[_Frame, ...]) -> None:
        name, body, line = c.get("name"), c.get("body"), c.get("line")
        if name == "node" and not c.get("receiver"):
            label = value_text(first_arg(c, "label"))
            ag = Agent(kind="label" if label else "any", label=label or None, line=line)
            if self.p.agent is None:
                self.p.agent = ag
            self.visit(body, ag, frames)
        elif name == "stage" and body is not None:
            st = Stage(name=self.stage_name(c), line=line, agent=self.stage_agent(agent))
            st.steps = _wrap(frames, parse_script_body(body))
            _hoist_parallel(st, self.p.notes)
            self.add_stage(st)
        elif name == "properties":
            _scripted_properties(c, self.p)
        elif name == "parallel" and (branches := _literal_parallel(c, self.p.notes)):
            for b in branches:
                b.steps = _wrap(frames, b.steps)
            self.add_stage(Stage(name="parallel", line=line, parallel=branches))
        elif body is not None and self.is_wrapper(c) and self.structural(body):
            self.wrapper(c, agent, frames)
        else:
            if name == "stage":
                self.p.notes.append(f"line {line}: stage '{self.stage_name(c)}' without a block (legacy syntax) - "
                                    "the steps after it stay outside any stage")
            elif names := self.stage_names([c]):
                self.p.notes.append(f"line {line}: stage(s) {_quoted(names)} nested in '{name}' (plugin/library "
                                    "block) kept as its nested steps, in an unnamed segment")
            self.loose([parse_step(c)], agent, frames)

    def wrapper(self, c: dict, agent: Agent | None, frames: tuple[_Frame, ...]) -> None:
        name, line, names = c.get("name"), c.get("line"), self.stage_names(c.get("body"))
        if name in _COSMETIC_WRAPPERS:
            self.p.notes.append(f"line {line}: {name} {{}}" + (f" around stage(s) {_quoted(names)}" if names else "")
                                + " dropped (native in GitHub Actions)")
            self.visit(c.get("body"), agent, frames)
            return
        tmpl = parse_step(c)
        tmpl.body = []
        if names:  # around node {} only, the result equals the generator's own handling of the wrapper step
            how = _BLOCK_SEMANTICS.get(name)
            self.p.notes.append(f"line {line}: {tmpl.qualified} {{}} around stage(s) {_quoted(names)} re-applied "
                                "inside each enclosed stage and segment" + (f" (approximated: {how})" if how else ""))
        self.visit(c.get("body"), agent, frames + (_Frame(tmpl),))

    def try_(self, s: dict, agent: Agent | None, frames: tuple[_Frame, ...]) -> None:
        line, catches, fin = s.get("line"), s.get("catches") or [], s.get("finally") or []
        for c in catches:
            if not _rethrows(c.get("body")):
                self.p.notes.append(f"line {c.get('line') or line}: catch does not rethrow - Jenkins carries on after "
                                    "the try and the build can still succeed; in GitHub Actions the failed step fails "
                                    "the job and the steps after it are skipped")
        if not self.structural([s]):
            # a plain statement: the generator runs its catch body if: failure() and its finally body if: always()
            self.loose(parse_script_body([s]), agent, frames)
            return
        self.flush()
        start = len(self.p.stages)
        self.visit(s.get("body"), agent, frames)
        self.flush()
        names = self.stage_names(s.get("body"))
        what = f"stage(s) {_quoted(names)}" if names else "node {} block(s)"
        handlers = [x for c in catches for x in c.get("body") or []] + fin
        spawns = any(x.get("k") == "call" and x.get("name") in ("node", "parallel") for x in walk_statements(handlers))
        if not spawns and self.stage_agent(agent) is None and not any(_own_job(st) for st in self.p.stages[start:]):
            # one job: the handlers follow the enclosed stages as a <try> with an empty body, so the generator
            # conditions the catch body on failure() and the finally body on always()
            tmpl = Step(name="<try>", line=line, category="dynamic", dynamic=True)
            if catches:
                catch = _Frame(tmpl, "_catch")
                for c in catches:
                    self.visit(c.get("body"), agent, frames + (catch,))
            if fin:
                self.visit(fin, agent, frames + (_Frame(tmpl, "_finally"),))
            done = (["catch body runs only on failure (if: failure())"] if catches else []) + \
                (["finally body always runs (if: always())"] if fin else [])
            self.p.notes.append(f"line {line}: try around {what}: {', '.join(done)}, right after them (exception "
                                "types are not distinguished)")
            return
        # the enclosed stages span several jobs: a later job would be skipped once they fail, so the handlers go to
        # pipeline post (failure / cleanup keeps catch before finally)
        for c in catches:
            self.p.post.setdefault("failure", []).extend(_wrap(frames, parse_script_body(c.get("body"))))
        if fin:
            self.p.post.setdefault("cleanup" if catches else "always", []).extend(
                _wrap(frames, parse_script_body(fin)))
        moved = (["catch body to pipeline post failure"] if catches else []) + \
            ([f"finally body to post {'cleanup' if catches else 'always'}"] if fin else [])
        self.p.notes.append(f"line {line}: try around {what} spanning several jobs: {' and '.join(moved)} - they "
                            "run at the end of the workflow instead of right after the enclosed stages")


def interpret_scripted(ast: dict) -> Pipeline:
    """Best-effort structural model of a Scripted Pipeline, in source order.

    * ``stage('x') {}`` blocks become stages; each run of statements between them becomes an anonymous segment
      (``Stage(name="")``) at its original position. Jenkins traces those steps with an empty STAGE_NAME, as the
      generator labels the steps of an unnamed stage.
    * Wrappers enclosing stages (``dir``, ``withEnv``, ``withCredentials``, ``timeout``, ``retry``, ...) are
      re-applied inside every stage and segment they enclose, as a Step of the same kind with the original
      arguments, so the generator's in-stage handling applies.
    * A ``try`` enclosing stages keeps its catch body failure-only and its finally body unconditional: right after
      the enclosed stages (a ``<try>`` step with an empty body), or in pipeline ``post`` when they span jobs.

    Every approximation is recorded in ``Pipeline.notes``."""
    p = Pipeline(dialect="scripted")
    w = _ScriptedWalker(p)
    w.visit(ast.get("statements", []), None, ())
    w.flush()
    segments = [s for s in p.stages if not s.name]
    if segments:
        p.notes.append(f"{w.loose_count} statement(s) outside any stage kept in source order in {len(segments)} "
                       f"unnamed segment(s) (from line(s) {', '.join(str(s.line) for s in segments[:8])}"
                       f"{', ...' if len(segments) > 8 else ''})")
    if not any(s.name for s in p.stages):
        p.notes.append("no stage() blocks found - structure is opaque (library call or custom DSL)")
    return p


def _literal_parallel(call: dict, notes: list[str]) -> list[Stage]:
    branches = []
    named = call.get("named", {})
    if named:
        for bname, v in named.items():
            if bname == "failFast":
                continue
            if v.get("t") == "closure":
                b = Stage(name=bname, line=v.get("line"))
                b.steps = parse_script_body(v.get("body"))
                branches.append(b)
    else:
        a0 = first_arg(call)
        if a0 is not None:
            notes.append(f"line {call.get('line')}: parallel() over a runtime-built map '{value_text(a0)}' (dynamic fan-out)")
    return branches


def _hoist_parallel(stage: Stage, notes: list[str]) -> None:
    """stage('x') { parallel a: {...}, b: {...} } -> parallel stage."""
    if len(stage.steps) == 1 and stage.steps[0].name == "parallel":
        pass  # literal parallel already parsed as a step; structure is shown via its named closures


def _scripted_properties(call: dict, p: Pipeline) -> None:
    for a in call.get("args", []):
        for item in a.get("v", []) if a.get("t") == "list" else []:
            if item.get("t") != "call":
                continue
            c = item["call"]
            if c.get("name") == "parameters":
                for pa in (first_arg(c) or {}).get("v", []):
                    if pa.get("t") == "call":
                        pc = pa["call"]
                        p.parameters.append(_parameter(pc.get("name"), pc.get("named", {}), first_arg(pc), pc.get("line")))
                    elif pa.get("t") == "map" and "$class" in (pa.get("v") or {}):
                        kv = pa["v"]
                        cls = value_text(kv["$class"])
                        p.parameters.append(_parameter(PARAMETER_CLASSES.get(cls, "other"), kv, None,
                                                       pa.get("line") or call.get("line")))
            elif c.get("name") == "pipelineTriggers":
                for t in (first_arg(c) or {}).get("v", []):
                    if t.get("t") == "call":
                        tc = t["call"]
                        p.triggers.append(Trigger(kind=tc.get("name") if tc.get("name") in ("cron", "pollSCM") else "other",
                                                  value=literal(first_arg(tc)), line=tc.get("line")))
            elif c.get("name") == "disableConcurrentBuilds":
                p.options["disableConcurrentBuilds"] = True
            elif c.get("name") == "buildDiscarder":
                p.options["buildDiscarder"] = True
