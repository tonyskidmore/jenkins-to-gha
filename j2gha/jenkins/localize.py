"""Make an original Jenkinsfile executable on the disposable local controller.

Two modes:
  trace - side-effecting steps are replaced by `J2GHA-TRACE` markers (control-flow fingerprint, no tooling needed)
  full  - real commands run; only unavailable infrastructure is stubbed (unknown plugin/library steps, downstream
          builds, notifications, cloud identity wrappers)

Rewrites are applied by AST source ranges (from the Groovy dump), never by regex over the whole file:
  * `agent {...}` -> `agent any` (labels, kubernetes, docker without --docker)
  * `triggers {}`, `@Library`, `libraries {}` removed; `tools {}` kept in full mode (installations provisioned)
  * options/parameters/tools that Jenkins rejects (plugins not installed) are removed by the auto-repair loop
A preamble defines `@Field scm` (for `checkout scm`) and script-level methods that shadow steps (CpsScript
resolves script methods before steps).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..analysis import catalog
from ..analysis.ast import CallCtx, all_calls, value_text, walk_statements
from ..trace import SILENT_STUBS, STUBBED_WRAPPERS, TRACED_STEPS

# Steps always stubbed in full mode because the local controller cannot provide the infrastructure.
# Bump when a localisation change alters what a Jenkins run records: run records carry it as provenance.
LOCALIZER_VERSION = 5

# Core parameter-definition symbols (Jenkins core / workflow-job): never stubbed as unknown DSL symbols, so a scripted
# `properties([parameters([choice(...)])])` defines real parameters (a J2ghaAny cannot be a parameter definition).
PARAMETER_SYMBOLS = frozenset({"parameters", "booleanParam", "choice", "string", "text", "password"})

# Values of the fake credentials provisioned on the controller; the GHA variants use the same values for secrets.
FAKE_USER = "j2gha-user"
FAKE_PASSWORD = "j2gha-fake-password"
FAKE_SECRET = "j2gha-fake-secret"

FULL_MODE_STUBS = ["build", "mail", "emailext", "slackSend", "office365ConnectorSend", "githubNotify",
                   "setGitHubPullRequestStatus", "publishChecks", "s3Upload", "s3Download", "copyArtifacts",
                   "waitForQualityGate", "recordIssues", "publishCoverage", "recordCoverage", "jacoco", "cobertura"]
FULL_MODE_WRAPPER_STUBS = ["withSonarQubeEnv", "withAWS", "withKubeConfig", "withVault", "azureCLI", "container",
                           "sshagent", "withDockerRegistry", "configFileProvider", "withMaven", "withGradle",
                           "withPythonEnv",
                           # no Kubernetes cloud, no wrapper plugins (build-user-vars, xvnc...), no Docker socket
                           # unless --docker: the body runs on the built-in node, as in trace mode
                           "podTemplate", "wrap", "withDockerContainer"]

SAFE_IMPORT_PREFIXES = ("java.", "javax.", "groovy.", "org.codehaus.groovy.", "org.jenkinsci.", "hudson.", "jenkins.",
                        "com.cloudbees.", "org.apache.commons.", "net.sf.json.", "static ")

READ_STUBS = {"readFile": "''", "fileExists": "false", "findFiles": "[]", "readJSON": "new J2ghaConfig()",
              "readYaml": "new J2ghaConfig()", "readProperties": "new J2ghaConfig()", "readMavenPom": "new J2ghaAny()",
              "readCSV": "[]", "tool": "'/usr'", "load": "new J2ghaAny()", "evaluate": "new J2ghaAny()",
              "library": "new J2ghaAny()"}

RETURNS = {
    "sh": "if (a && a[0] instanceof Map && a[0].returnStdout) { return '' }; "
          "if (a && a[0] instanceof Map && a[0].returnStatus) { return 0 }; return null",
    "bat": "if (a && a[0] instanceof Map && a[0].returnStdout) { return '' }; "
           "if (a && a[0] instanceof Map && a[0].returnStatus) { return 0 }; return null",
    "powershell": "if (a && a[0] instanceof Map && (a[0].returnStdout)) { return '' }; return null",
    "pwsh": "return null",
    "build": "return [result: 'SUCCESS', number: 1, currentResult: 'SUCCESS', absoluteUrl: '', "
             "getResult: { -> 'SUCCESS' }, buildVariables: [:]]",
    "input": "return null",
    "readFile": "return ''",
    "httpRequest": "return [status: 200, content: '{}']",
}


@dataclass
class Edit:
    start: int
    end: int
    text: str
    reason: str


@dataclass
class Localized:
    script: str
    changes: list[str] = field(default_factory=list)
    stubs: list[str] = field(default_factory=list)
    credentials: list[dict[str, Any]] = field(default_factory=list)
    tools: dict[str, str] = field(default_factory=dict)


class SourceEditor:
    def __init__(self, text: str):
        self.text = text
        self.line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self.line_starts.append(i + 1)
        self.edits: list[Edit] = []

    def offset(self, line: int, col: int) -> int:
        return self.line_starts[line - 1] + col - 1

    def replace_node(self, node: dict, text: str, reason: str) -> bool:
        if not node.get("line") or not node.get("endLine"):
            return False
        start = self.offset(node["line"], node["col"])
        end = self.offset(node["endLine"], node["endCol"])
        for e in self.edits:  # skip overlapping edits (outer edit wins)
            if not (end <= e.start or start >= e.end):
                return False
        self.edits.append(Edit(start, end, text, reason))
        return True

    def insert_before_end(self, node: dict, text: str, reason: str) -> bool:
        """Insert text just before the closing brace of a call with a closure body."""
        if not node.get("endLine"):
            return False
        end = self.offset(node["endLine"], node["endCol"])
        pos = self.text.rfind("}", 0, end)
        if pos < 0:
            return False
        self.edits.append(Edit(pos, pos, text, reason))
        return True

    def apply(self) -> str:
        """Every edit keeps the line count of the span it replaces, so Jenkins error lines (and the `quote-env`
        repair keyed on them) match the original Jenkinsfile."""
        out = self.text
        for e in sorted(self.edits, key=lambda e: -e.start):
            lost = self.text.count("\n", e.start, e.end) - e.text.count("\n")
            if lost < 0:
                raise ValueError(f"localisation edit '{e.reason}' adds {-lost} line(s): {e.text!r}")
            out = out[:e.start] + e.text + "\n" * lost + out[e.end:]
        return out


def _calls(ast: dict) -> list[CallCtx]:
    return list(all_calls(ast))


def _stub_class(imp: dict) -> str | None:
    """Simple name an unresolvable (shared-library / plugin) import is stubbed under, if any."""
    name = str(imp.get("name") or "")
    if not name or name.startswith(SAFE_IMPORT_PREFIXES) or not imp.get("line"):
        return None
    simple = imp.get("alias") or name.split(".")[-1]
    return simple if re.fullmatch(r"[A-Z]\w*", simple or "") else None


def _stub_refs(node: dict, classes: set[str]) -> list[str]:
    """Stubbed classes referenced from a call's arguments (they evaluate to J2ghaAny at run time)."""
    text = " ".join(value_text(v) for v in [*(node.get("args") or []), *(node.get("named") or {}).values()])
    return sorted(n for n in classes if re.search(rf"\b{re.escape(n)}\b", text))


def _arg_calls(node: dict):
    """Every call nested in a call's arguments (`choice(choices: getBillingProjectChoices())`, lists, maps), including
    the receivers of argument calls (`getChoices().reverse()`: a stub's methods return stubs too). Calls inside a
    GString are not: their value is interpolated into a String, which every parameter/option accepts."""
    todo = [*(node.get("args") or []), *(node.get("named") or {}).values()]
    while todo:
        v = todo.pop()
        if not isinstance(v, dict):
            continue
        if v.get("t") == "call" and v.get("call"):
            yield v["call"]
            todo += [*(v["call"].get("args") or []), *(v["call"].get("named") or {}).values(),
                     *({"t": "call", "call": rc} for rc in v["call"].get("receiverCalls") or [])]
        elif v.get("t") == "list":
            todo += v.get("v") or []
        elif v.get("t") == "map":
            todo += list((v.get("v") or {}).values())


def _stub_calls(node: dict, stubbed: set[str], defined: set[str]) -> list[str]:
    """Calls in a directive's arguments that return a stub at run time: shared-library globals (a bare call the
    step catalog does not know; the analysis lists them as neither steps nor symbols when they sit inside another
    call's arguments) and steps the repair loop already stubbed. Jenkins cannot coerce a J2ghaAny into a
    parameter/option value (021: `choice(choices: getBillingProjectChoices())` failed before any stage)."""
    if node.get("name") in ("string", "text", "password"):
        return []  # a String default: the stringify-args repair keeps the parameter with a 'j2gha-stub' default
    out = []
    for call in _arg_calls(node):
        name = str(call.get("name") or "")
        if call.get("receiver") or not re.fullmatch(r"[a-z_]\w*", name) or name in defined:
            continue
        if name in stubbed or (catalog.categorise(name) == "unknown" and name not in catalog.GROOVY_METHODS):
            out.append(f"{name}()")
    return sorted(set(out))


def localize(text: str, ast: dict, analysis: dict, mode: str, source: dict | None = None,
             docker: bool = False, extra_stubs: list[str] | None = None,
             remove: list[tuple[str, str]] | None = None) -> Localized:
    """``remove`` = [(directive, name)] from the auto-repair loop, e.g. ("options", "gitLabConnection") or
    ("fill-stage", "<stage name>") for stages that have no steps."""
    ed = SourceEditor(text)
    loc = Localized(script=text)
    calls = _calls(ast)
    in_pipeline = analysis.get("dialect") in ("declarative", "library-template")
    remove = remove or []
    stubbed = {s for s in map(_stub_class, ast.get("imports", [])) if s}
    defined = set(analysis.get("methods", []))
    # unknown steps and runtime-discovered ones are stubbed below as methods returning J2ghaAny
    stub_steps = {u["name"] for u in analysis.get("unknown_steps", []) if "." not in u["name"]} | set(extra_stubs or [])
    for c in calls:
        n, parent = c.name, (c.path[-1] if c.path else None)
        if in_pipeline and n == "agent" and parent in ("pipeline", "stage", "matrix") and "steps" not in c.path:
            body_names = [b.get("name") for b in (c.node.get("body") or []) if b.get("k") == "call"]
            args = c.node.get("args") or []
            is_none = (args and value_text(args[0]) == "none") or "none" in body_names
            if is_none:
                continue
            keep_docker = mode == "full" and docker and any(b in ("docker", "dockerfile") for b in body_names)
            if not keep_docker and not (args and value_text(args[0]) == "any"):
                if ed.replace_node(c.node, "agent any", "agent -> any"):
                    loc.changes.append(f"L{c.line}: agent -> any (was {', '.join(body_names) or value_text(args[0]) if args else '?'})")
        elif in_pipeline and n in ("buildDiscarder", "lock") and parent == "options":
            # lock needs a lockable resource the disposable controller does not define (GHA: concurrency);
            # buildDiscarder has no effect on a run but crashes the job when its argument is a stub or was
            # stringified by a repair (examples 003 and 005 in full mode). Neither changes what a run records.
            if ed.replace_node(c.node, f"/* j2gha: {n} removed */", n):
                loc.changes.append(f"L{c.line}: options {n} removed")
        elif in_pipeline and n in ("triggers", "libraries") and parent == "pipeline":
            if ed.replace_node(c.node, f"/* j2gha: {n} removed */", f"{n} removed"):
                loc.changes.append(f"L{c.line}: {n} {{}} removed")
        elif in_pipeline and n == "tools" and parent in ("pipeline", "stage") and mode == "trace":
            if ed.replace_node(c.node, "/* j2gha: tools removed (trace) */", "tools removed"):
                loc.changes.append(f"L{c.line}: tools {{}} removed (trace mode)")
        elif in_pipeline and n == "environment" and any(r[0] == "quote-env" for r in remove):
            for st in c.node.get("body") or []:
                v = st.get("value") or {}
                if st.get("k") == "assign" and ("quote-env", st.get("line")) in remove and v.get("line"):
                    src = ed.text[ed.offset(v["line"], v["col"]):ed.offset(v["endLine"], v["endCol"])]
                    if ed.replace_node(v, '"${' + src + '}"', "quote env"):
                        loc.changes.append(f"L{st['line']}: environment value `{src}` wrapped in a GString")
        elif in_pipeline and parent in ("pipeline", "stage") and ("remove-directive", n) in remove:
            if ed.replace_node(c.node, f"/* j2gha: empty {n} removed */", "empty directive"):
                loc.changes.append(f"L{c.line}: {n} {{}} removed (empty after repairs)")
        elif in_pipeline and parent in ("options", "parameters") and \
                (refs := _stub_refs(c.node, stubbed) + _stub_calls(c.node, stub_steps, defined)):
            # a plugin describable cannot coerce J2ghaAny (e.g. gitLabConnection(LibDefaults.CONNECTION),
            # choice(choices: getBillingProjectChoices()))
            if ed.replace_node(c.node, f"/* j2gha: {parent} {n} removed */", "stub-valued directive"):
                loc.changes.append(f"L{c.line}: {parent} '{n}' removed (value from stubbed {', '.join(refs)})")
        elif in_pipeline and parent in ("options", "parameters", "tools", "triggers") and (parent, n) in remove:
            if ed.replace_node(c.node, f"/* j2gha: {parent} {n} removed */", "unsupported directive"):
                loc.changes.append(f"L{c.line}: {parent} '{n}' removed (plugin not available locally)")
        elif in_pipeline and n == "stage" and ("fill-stage", value_text((c.node.get("args") or [None])[0])) in remove:
            if ed.insert_before_end(c.node, " steps { script { true } } /* j2gha: stage had no steps */ ",
                                    "empty stage"):
                loc.changes.append(f"L{c.line}: stage had no steps - no-op steps block added")
        elif n == "node" and c.node.get("args") and c.node.get("body") is not None and "agent" not in c.path:
            # node('label') { } (scripted, or inside script{}) -> node('built-in'): the label does not exist locally
            a0 = c.node["args"][0]
            if a0.get("line"):
                if ed.replace_node(a0, "'built-in'", "node label"):
                    loc.changes.append(f"L{c.line}: node({value_text(a0)}) -> node('built-in')")
    # @Library('x') _  -> removed
    for s in ast.get("statements", []):
        if s.get("k") == "decl" and any(a.get("name") == "Library" for a in s.get("annotations", [])):
            ann = s["annotations"][0]
            node = {"line": ann["line"], "col": ann["col"], "endLine": s["endLine"], "endCol": s["endCol"]}
            if ed.replace_node(node, "/* j2gha: @Library removed */", "library removed"):
                loc.changes.append(f"L{ann['line']}: @Library removed - library steps are stubbed")
    for imp in ast.get("imports", []):
        if not str(imp.get("name") or "").startswith(SAFE_IMPORT_PREFIXES):
            continue  # removed together with its annotation below
        for ann in imp.get("annotations", []):
            if ann.get("name") == "Library":
                node = {"line": ann["line"], "col": ann["col"], "endLine": ann["endLine"], "endCol": ann["endCol"]}
                if ed.replace_node(node, "/* j2gha: @Library removed */", "library removed"):
                    loc.changes.append(f"L{ann['line']}: @Library removed - library steps are stubbed")
    for c in calls:
        if c.name == "library" and not c.path:
            if ed.replace_node(c.node, "/* j2gha: library() removed */", "library removed"):
                loc.changes.append(f"L{c.line}: library() removed - library steps are stubbed")
    # unresolvable imports (shared-library / plugin classes) -> removed and replaced by permissive stub classes
    stub_classes: list[str] = []
    for imp in ast.get("imports", []):
        name = str(imp.get("name") or "")
        if not name or name.startswith(SAFE_IMPORT_PREFIXES) or not imp.get("line"):
            continue
        rng = dict(imp)
        anns = [a for a in imp.get("annotations", []) if a.get("line")]
        if anns:
            first = min(anns, key=lambda a: (a["line"], a["col"]))
            if (first["line"], first["col"]) < (imp["line"], imp["col"]):
                rng.update(line=first["line"], col=first["col"])
        if ed.replace_node(rng, f"/* j2gha: import {name} removed */", "import removed"):
            if simple := _stub_class(imp):
                stub_classes.append(simple)
            loc.changes.append(f"L{imp['line']}: import {name} removed (class stubbed)")
    # A script-level `def x` is a local of run(), out of scope for an earlier `pipeline {}` and for script methods:
    # they resolve `x` through the binding, typically set by helper code we stubbed. Promote it in place (same line).
    missing_props = [r[1] for r in remove if r[0] == "stub-property"] + _env_global_refs(ast, remove)
    if mode == "full" and not docker and any(re.match(r"docker\b", c.node.get("receiver") or "") for c in calls):
        # docker.image(x).inside {}, docker.withRegistry {}, docker.build(): the docker-workflow global runs real
        # `docker inspect`/`docker pull` sh steps before its (stubbed) wrappers, so without --docker it is replaced
        # by a stub whose blocks still run (108: a client and no daemon failed the first stage)
        missing_props.append("docker")
    top_decls = {st.get("name") for st in ast.get("statements", []) if st.get("k") == "decl"}
    tuples = {st["line"]: names for st in ast.get("statements", [])
              if st.get("k") == "decl" and st.get("name") == "(" and (names := _tuple_decl_names(ed, st))}
    top_decls.update(n for names in tuples.values() for n in names)  # never re-declared in the appended block
    missing_props += _sibling_params(ast, missing_props, analysis)
    for st in ast.get("statements", []):
        if st.get("k") != "decl" or st.get("annotations"):
            continue
        if st.get("name") in missing_props and (st.get("value") or {}).get("kind") == "EmptyExpression":
            if ed.replace_node(st, f"@groovy.transform.Field def {st['name']} = new J2ghaAny()", "promote decl"):
                loc.changes.append(f"L{st['line']}: script variable '{st['name']}' unset when read - "
                                   "declaration promoted to a permissive @Field stub")
        elif st.get("name") == "(" and (names := tuples.get(st["line"])) and any(n in missing_props for n in names):
            # def (a, b, c) = [0, 0, 0] (021): Groovy rejects a second declaration of any of the names and each
            # unread one would cost a build, so the whole tuple is promoted, keeping literal initialisers
            v = st.get("value") or {}
            items = v.get("v") if v.get("t") == "list" and isinstance(v.get("v"), list) else []
            decls = [f"@groovy.transform.Field def {n} = {_literal(items[i]) if i < len(items) else 'new J2ghaAny()'}"
                     for i, n in enumerate(names)]
            if ed.replace_node(st, "; ".join(decls), "promote tuple decl"):
                loc.changes.append(f"L{st['line']}: script variables {', '.join(names)} unset when read - "
                                   "multiple declaration promoted to @Field declarations")
    _stub_value_repairs(ed, ast, calls, remove, loc)
    stub_bodies = _stub_receiver_bodies(ed, ast, calls, set(stub_classes) | set(missing_props), loc)
    retry_with_conditions = any(c.name == "retry" and "conditions" in c.node.get("named", {}) for c in calls)
    body = ed.apply()
    if analysis.get("dialect") == "library-template":
        call_m = next((m for m in ast.get("methods", []) if m.get("name") == "call"), None)
        params = (call_m or {}).get("params", [])
        if params and (params[0].get("type") == "Closure" or params[0].get("name") in ("body", "closure", "cl")):
            invocation = "call { }"
        elif params:
            invocation = "call(new J2ghaConfig())"
        else:
            invocation = "call()"
        body += f"\n// j2gha: shared-library template invoked with an empty configuration\n{invocation}\n"
        loc.changes.append(f"appended `{invocation}` to execute the shared-library pipeline template")

    unknown = [u["name"] for u in analysis.get("unknown_steps", []) if "." not in u["name"]]
    stubs: list[str] = []
    if mode == "trace":
        traced = [s for s in TRACED_STEPS if s not in defined]
        wrappers = [s for s in STUBBED_WRAPPERS if s not in defined]
    else:
        traced = [s for s in FULL_MODE_STUBS if s not in defined]
        wrappers = [s for s in FULL_MODE_WRAPPER_STUBS if s not in defined]
    unknown_stubs = [u for u in dict.fromkeys(unknown + (extra_stubs or [])) if u not in defined and u not in traced
                     and u not in wrappers and u not in SILENT_STUBS and re.fullmatch(r"[A-Za-z_]\w*", u)]
    pre = [f"// ---- j2gha localisation block ({mode} mode) - generated, not part of the original pipeline ----",
           f"@groovy.transform.Field def scm = {_scm_literal(source, mode)}",
           # permissive stand-in for objects that would come from unavailable plugins/libraries
           "class J2ghaAny implements Serializable { @NonCPS def propertyMissing(String n) { new J2ghaAny() }; "
           "@NonCPS def methodMissing(String n, Object a) { new J2ghaAny() }; @NonCPS String toString() { 'j2gha-stub' }; "
           # a stub stands for a present value: truthy and therefore not empty (`if (!x || x.isEmpty()) error`)
           "@NonCPS boolean asBoolean() { true }; @NonCPS boolean isEmpty() { false }; "
           "@NonCPS def getAt(Object k) { new J2ghaAny() }; "
           "@NonCPS Iterator iterator() { [].iterator() } }",
           # permissive empty configuration: missing keys and hooks (config.customStep()) are stubs
           "class J2ghaConfig extends LinkedHashMap { @NonCPS Object get(Object k) { super.containsKey(k) ? super.get(k) : new J2ghaAny() }; "
           "@NonCPS def methodMissing(String n, Object a) { new J2ghaAny() } }",
           "def j2ghaTrace(String kind) {",
           "  steps.echo('J2GHA-TRACE ' + groovy.json.JsonOutput.toJson([stage: (env.STAGE_NAME ?: ''), step: kind]))",
           "}"]
    for s in traced:
        ret = RETURNS.get(s, "return null")
        if s == "echo":
            pre.append("def echo(Object... a) { j2ghaTrace('echo'); steps.echo(String.valueOf(a ? a[0] : '')) }")
        elif s == "error":
            pre.append("def error(Object... a) { j2ghaTrace('error'); steps.error(String.valueOf(a ? a[0] : 'error')) }")
        elif s == "checkout" and mode == "trace":
            # Declarative copies the returned map into env, so keep the scenario's GIT_BRANCH
            pre.append("def checkout(Object... a) { j2ghaTrace('checkout'); "
                       "return [GIT_COMMIT: '0000000000000000000000000000000000000000', "
                       "GIT_BRANCH: (env.GIT_BRANCH ?: env.BRANCH_NAME)] }")
        else:
            pre.append(f"def {s}(Object... a) {{ j2ghaTrace('{s}'); {ret} }}")
        stubs.append(s)
    # Build properties (buildDiscarder, triggers, milestone...) have no effect on what a run does and crash the job when
    # an argument is a stub (002: a stubbed logRotator). Parameter definitions do matter (params.X reads them), so in
    # full mode `properties()` applies its `parameters(...)` entries for real, without stub-valued definitions, and
    # drops the rest.
    full_properties = mode == "full" and "properties" not in defined and "parameters" not in defined and \
        any(c.name == "properties" and not c.node.get("receiver") for c in calls)
    for s in SILENT_STUBS:
        if s in defined:
            continue
        if s == "properties" and full_properties:
            pre.append("def parameters(Object... a) { return [j2ghaParameters: (a && a[0] instanceof List) ? a[0] : []] }")
            pre.append("@NonCPS def j2ghaParameterDefs(Object props) { (props instanceof List ? props : []).findAll { "
                       "it instanceof Map && it.containsKey('j2ghaParameters') }.collectMany { it.j2ghaParameters }"
                       ".findAll { it != null && !(it instanceof J2ghaAny) } }")
            pre.append("def properties(Object... a) { def defs = j2ghaParameterDefs(a ? a[0] : null); "
                       "if (defs) { steps.properties([steps.parameters(defs)]) }; return null }")
            stubs.append("properties(parameters kept)")
        else:
            pre.append(f"def {s}(Object... a) {{ return null }}")
            stubs.append(s)
    if mode == "trace":
        for s, ret in READ_STUBS.items():
            if s not in defined:
                pre.append(f"def {s}(Object... a) {{ return {ret} }}")
                stubs.append(s)
    if mode == "full" and "checkout" not in defined:
        pre.append("def checkout(Object... a) { def r = a.length == 1 ? steps.checkout(a[0]) : steps.checkout(a); "
                   "if (r instanceof Map && env.GIT_BRANCH) { r.GIT_BRANCH = env.GIT_BRANCH }; return r }")
        stubs.append("checkout(GIT_BRANCH kept)")
    for w in wrappers:
        pre.append(f"def {w}(Object... a) {{ def body = (a && a[-1] instanceof Closure) ? a[-1] : null; "
                   f"return body != null ? body() : null }}")
        stubs.append(w)
    for u in unknown_stubs:
        pre.append(f"def {u}(Object... a) {{ j2ghaTrace('{u}'); def body = (a && a[-1] instanceof Closure) ? a[-1] : null; "
                   f"return body != null ? body() : new J2ghaAny() }}")
        stubs.append(u)
    if retry_with_conditions and "retry" not in wrappers and "retry" not in defined:
        pre.append("def retry(Object... a) { def body = (a && a[-1] instanceof Closure) ? a[-1] : null; "
                   "return body != null ? body() : null }")
        stubs.append("retry")
        loc.changes.append("retry(conditions: ...) stubbed - agent/error conditions come from unavailable plugins")
    for sym in analysis.get("dsl_symbols", []):
        if sym not in defined and sym not in traced and sym not in wrappers and sym not in unknown_stubs \
                and sym not in PARAMETER_SYMBOLS and re.fullmatch(r"[A-Za-z_]\w*", sym):
            pre.append(f"def {sym}(Object... a) {{ return new J2ghaAny() }}")
            stubs.append(sym)
    for prop in dict.fromkeys(missing_props):
        if prop in defined or prop in top_decls:
            continue
        pre.append(f"@groovy.transform.Field def {prop} = new J2ghaAny()")
        loc.changes.append(STUBBED_PROPERTY_CHANGE.format(prop))
    if stub_bodies:
        pre.append("def j2ghaBody(Object... a) { def body = (a && a[-1] instanceof Closure) ? a[-1] : null; "
                   "return body != null ? body() : new J2ghaAny() }")
        stubs.append("j2ghaBody")
    for cls in dict.fromkeys(stub_classes):
        pre.append(f"class {cls} extends J2ghaAny {{ @NonCPS static $static_propertyMissing(String n) {{ new J2ghaAny() }}; "
                   f"@NonCPS static $static_methodMissing(String n, Object a) {{ new J2ghaAny() }} }}")
    if not in_pipeline:
        pre.append("def node(Object... a) { def body = a[-1]; return steps.node('built-in') { body() } }")
        stubs.append("node")
    pre.append("// ---- end of j2gha localisation block ----")
    # The preamble is *appended*: script methods/classes are hoisted and @Field initialisers run at construction,
    # so line numbers in Jenkins errors still match the original Jenkinsfile (auto-repairs rely on that).
    loc.script = body.rstrip("\n") + "\n\n" + "\n".join(pre) + "\n"
    loc.stubs = stubs
    loc.credentials = analysis.get("credentials", [])
    return loc


def _tuple_decl_names(ed: SourceEditor, st: dict) -> list[str]:
    """The names of a script-level multiple declaration `def (a, int b) = ...` (the dumper names the node `(`)."""
    if not st.get("line") or not st.get("endLine"):
        return []
    src = ed.text[ed.offset(st["line"], st["col"]):ed.offset(st["endLine"], st["endCol"])]
    m = re.match(r"(?:def|final)\s*\(([^)]*)\)\s*=", src)
    names = [item.split()[-1] for item in m.group(1).split(",") if item.strip()] if m else []
    return names if names and all(re.fullmatch(r"[A-Za-z_]\w*", n) for n in names) else []


def _literal(v: Any) -> str:
    """A dumper value as Groovy source when it is a plain literal, else a permissive stub."""
    if isinstance(v, dict):
        if v.get("t") == "num":
            return str(v.get("v"))
        if v.get("t") == "bool":
            return "true" if v.get("v") else "false"
        if v.get("t") == "null":
            return "null"
        if v.get("t") == "str":
            return groovy_string(str(v.get("v")))
    return "new J2ghaAny()"


GROOVY_ESCAPES = {"\\": "\\\\", "'": "\\'", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}


def groovy_string(s: str) -> str:
    """A single-quoted Groovy literal on one line (a localisation edit must not add lines) with the same value:
    line breaks and other control characters are escaped, `$` needs no escape in single quotes."""
    return "'" + "".join(GROOVY_ESCAPES.get(ch) or (f"\\u{ord(ch):04x}" if ord(ch) < 0x20 or ord(ch) == 0x7f else ch)
                         for ch in s) + "'"


def _value_root(v: dict) -> str | None:
    """`lib` for lib.config(), lib.CONFIG or lib.a.b()."""
    text = (v.get("call") or {}).get("receiver") if v.get("t") == "call" else v.get("text") if v.get("t") == "prop" else None
    root = re.match(r"[A-Za-z_]\w*", text or "")
    return root.group(0) if root else None


def _stub_value_repairs(ed: SourceEditor, ast: dict, calls: list[CallCtx], remove: list, loc: Localized) -> None:
    """Runtime repairs for stub values (J2ghaAny, stubbed library classes) that Groovy or a step cannot coerce."""
    untype = {r[1] for r in remove if r[0] == "untype-decl"}
    if untype:
        decls = [st for st in walk_statements([*ast.get("statements", []),
                                               *(b for m in ast.get("methods", []) for b in m.get("body", []))])
                 if st.get("k") == "decl" and (st.get("value") or {}).get("line")]
        # Map<..> cfg = lib.config(): the failing declaration, and its siblings typed from the same object
        roots = {_value_root(st["value"]) for st in decls if st["line"] in untype} - {None}
        for st in decls:
            if st["line"] not in untype and _value_root(st["value"]) not in roots:
                continue
            start, vstart = ed.offset(st["line"], st["col"]), ed.offset(st["value"]["line"], st["value"]["col"])
            head = ed.text[start:vstart]
            m = re.search(rf"\b{re.escape(st['name'])}\s*=\s*$", head)
            if not m or m.start() == 0 or re.match(r"(def|final|static|@)\b", head) or "\n" in head[:m.start()]:
                continue
            if ed.replace_node({"line": st["line"], "col": st["col"], "endLine": st["line"],
                                "endCol": st["col"] + m.start()}, "def ", "untype decl"):
                loc.changes.append(f"L{st['line']}: `{head[:m.start()].strip()} {st['name']}` declared with def - "
                                   "its value is a stub that cannot be cast to the declared type")
    stringify = {r[1] for r in remove if r[0] == "stringify-args"}
    if not stringify:
        return

    def exprs(c: CallCtx) -> list[tuple[dict, str]]:
        vals = [*(c.node.get("args") or []), *(c.node.get("named") or {}).values()]
        return [(v, ed.text[ed.offset(v["line"], v["col"]):ed.offset(v["endLine"], v["endCol"])])
                for v in vals if v.get("t") in ("var", "prop", "call", "expr") and v.get("line")]

    # the failing call, and every call of the same step with the same argument (dir(Lib.PATH) used repeatedly)
    failing = {(c.name, src) for c in calls if c.line in stringify for _, src in exprs(c)}
    # Declarative instantiates parameters/options/triggers when pipeline {} runs and reports that line instead
    in_root = any(c.name == "pipeline" and c.node.get("body") is not None for c in calls if c.line in stringify)

    def directive(c: CallCtx) -> bool:
        return in_root and "pipeline" in c.path and c.path[-1] in ("parameters", "options", "triggers")

    for c in calls:
        for v, src in exprs(c):
            if ((c.name, src) in failing or directive(c)) and "\n" not in src \
                    and ed.replace_node(v, '"${' + src + '}"', "stringify arg"):
                loc.changes.append(f"L{c.line}: {c.name} argument `{src}` wrapped in a GString - "
                                   "a stub cannot bind to a String step parameter")


def _stub_receiver_bodies(ed: SourceEditor, ast: dict, calls: list[CallCtx], stubbed: set[str],
                          loc: Localized) -> bool:
    """`lib.withStage(name) { ... }` on a stubbed object would return a J2ghaAny without running the block (its
    methodMissing is @NonCPS, so it cannot run steps): call the CPS script method j2ghaBody(name) { ... } instead,
    as for unknown steps with a body. Stubbed: library classes/globals and script variables initialised from them."""
    roots = set(stubbed)
    for st in ast.get("statements", []):
        if st.get("k") == "decl" and st.get("name"):
            v = st.get("value") or {}
            ctor = ((v.get("call") or {}).get("name") or "") if v.get("t") == "call" else ""
            if _value_root(v) in roots or ctor.removeprefix("new ") in stubbed:
                roots.add(st["name"])
    changed = False
    for c in calls:
        receiver = c.node.get("receiver") or ""
        root = re.match(r"[A-Za-z_]\w*", receiver)
        if c.node.get("body") is None or not root or root.group(0) not in roots or not c.node.get("line"):
            continue
        start = ed.offset(c.node["line"], c.node["col"])
        m = re.compile(re.escape(receiver) + r"\s*\.\s*" + re.escape(c.name) + r"\b").match(ed.text, start)
        if m and "\n" not in m.group(0) and ed.replace_node(
                {"line": c.node["line"], "col": c.node["col"], "endLine": c.node["line"],
                 "endCol": c.node["col"] + len(m.group(0))}, "j2ghaBody", "stub receiver body"):
            loc.changes.append(f"L{c.line}: {receiver}.{c.name}(...) {{}} on a stub runs its block (j2ghaBody)")
            changed = True
    return changed


def _scm_literal(source: dict | None, mode: str) -> str:
    if mode == "full" and source and source.get("url"):
        ref = source.get("sha") or source.get("branch") or "main"
        return ("[$class: 'GitSCM', branches: [[name: " + json.dumps(ref) + "]], "
                "extensions: [[$class: 'CloneOption', shallow: false, noTags: true]], "
                "userRemoteConfigs: [[url: " + json.dumps(source["url"]) + "]]]")
    return "[$class: 'GitSCM', branches: [[name: 'main']], userRemoteConfigs: [[url: 'https://example.invalid/j2gha.git']]]"


# ---------------------------------------------------------------------------------- auto-repair from Jenkins errors
EMPTY_STAGE = re.compile(r'Expected one of "steps", "stages", or "parallel" for stage "([^"]+)"')
EMPTY_DIRECTIVE = re.compile(r"\b(parameters|options|triggers|tools|environment) can not be empty")
MISSING_PROPERTY = re.compile(r"No such property: (\w+) for class: WorkflowScript")
BARE_ENV = re.compile(r"Environment variable values must either be single quoted, double quoted, or function calls\. @ line (\d+)")
# a stub value cast to a declared type, or bound to a step's String parameter (stub classes have simple names)
STUB_CAST = re.compile(r"Cannot cast object 'j2gha-stub' with class '[\w$]+' to class [^\n]*\n"
                       r"(?:[^\n]*\n)*?[^\n]*\bat WorkflowScript\.[\w$]+\(WorkflowScript:(\d+)\)")
STUB_STEP_ARG = re.compile(r"expects class java\.lang\.String but received class [\w$]+(?![\w.$])[^\n]*\n"
                           r"(?:[^\n]*\n)*?[^\n]*\bat WorkflowScript\.[\w$]+\(WorkflowScript:(\d+)\)")
ENV_VALUE_ISSUE = re.compile(r"One or more variables have some issues with their values: ([\w, ]+)")
NON_GLOBAL_ROOTS = {"env", "params", "currentBuild", "scm", "this", "it", "true", "false", "null"}


# Jenkins' own environment variables resolve as bare names; never stub them
JENKINS_ENV_RE = re.compile(r"(BUILD|JOB|GIT|CHANGE|TAG|NODE|JENKINS|HUDSON|EXECUTOR|BRANCH|WORKSPACE|STAGE)(_\w*)?"
                            r"|PATH|HOME|RUN_\w+")


def _sibling_params(ast: dict, missing: list[str], analysis: dict) -> list[str]:
    """Bare UPPER_CASE names next to a missing one in a script-level map/list literal - job parameters configured
    outside the Jenkinsfile (`[branch: APP_BRANCH, env: ENVIRONMENT]`) - so they are stubbed together rather than
    one build per name."""
    if not missing:
        return []
    defined = {re.sub(r"^env\.", "", str(st.get("name") if st.get("k") == "decl" else st.get("target")).strip())
               for st in walk_statements(ast.get("statements", [])) if st.get("k") in ("decl", "assign")}
    defined |= set(analysis.get("methods", []))
    defined |= {value_text(c.node["named"]["name"]) for c in all_calls(ast)
                if "parameters" in c.path and "name" in (c.node.get("named") or {})}
    out: list[str] = []
    for st in ast.get("statements", []):
        v = st.get("value") or {}
        if st.get("k") not in ("decl", "assign") or v.get("t") not in ("map", "list"):
            continue
        items = list(v["v"].values()) if v["t"] == "map" else v["v"]
        names = [x.get("name") for x in items if isinstance(x, dict) and x.get("t") == "var"]
        if any(n in missing for n in names):
            out += [n for n in names if n and n not in missing and n not in defined
                    and re.fullmatch(r"[A-Z][A-Z0-9_]*", n) and not JENKINS_ENV_RE.fullmatch(n)]
    return list(dict.fromkeys(out))


# The change recorded for each undefined property replaced by a J2ghaAny (whose toString() is STUB_VALUE); execution
# variants give the converted run the same value for the environment-like ones (runners.variants.stubbed_properties).
STUBBED_PROPERTY_CHANGE = "undefined property '{}' (plugin/library global) replaced by a permissive stub"
STUB_VALUE = "j2gha-stub"


def _env_global_refs(ast: dict, remove: list) -> list[str]:
    """Root identifiers referenced from environment values Jenkins could not evaluate (plugin/library globals)."""
    wanted = {r[1] for r in remove if r[0] == "env-globals"}
    if not wanted:
        return []
    roots: list[str] = []
    for c in all_calls(ast):
        if c.name != "environment":
            continue
        for st in c.node.get("body") or []:
            if st.get("k") == "assign" and st.get("target") in wanted:
                text = value_text(st.get("value"))
                for expr in re.findall(r"\$\{([^}]+)\}", text):
                    root = re.match(r"\s*([A-Za-z_]\w*)", expr)
                    if root and root.group(1) not in NON_GLOBAL_ROOTS and not root.group(1).isupper():
                        roots.append(root.group(1))
    return roots
REPAIR_PATTERNS = [
    (re.compile(r'Invalid option type "(\w+)"'), "options"),
    (re.compile(r'Invalid parameter type "(\w+)"'), "parameters"),
    (re.compile(r'Invalid tool type "(\w+)"'), "tools"),
    (re.compile(r'Invalid trigger type "(\w+)"'), "triggers"),
]
NO_SUCH_STEP = re.compile(r"No such DSL method '(\w+)' found")


def repairs_from_errors(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    removes: list[tuple[str, str]] = []
    for rx, directive in REPAIR_PATTERNS:
        for m in rx.finditer(text):
            removes.append((directive, m.group(1)))
    for m in EMPTY_STAGE.finditer(text):
        removes.append(("fill-stage", m.group(1)))
    for m in EMPTY_DIRECTIVE.finditer(text):
        removes.append(("remove-directive", m.group(1)))
    for m in MISSING_PROPERTY.finditer(text):
        removes.append(("stub-property", m.group(1)))
    for m in BARE_ENV.finditer(text):
        removes.append(("quote-env", int(m.group(1))))
    for m in STUB_CAST.finditer(text):
        removes.append(("untype-decl", int(m.group(1))))
    for m in STUB_STEP_ARG.finditer(text):
        removes.append(("stringify-args", int(m.group(1))))
    for m in ENV_VALUE_ISSUE.finditer(text):
        for name in m.group(1).split(","):
            removes.append(("env-globals", name.strip()))
    stubs = sorted(set(NO_SUCH_STEP.findall(text)))
    return sorted(set(removes)), stubs


# ---------------------------------------------------------------------------------- controller provisioning
def tool_installs(ir) -> list[tuple[str, str]]:
    """Every (tool type, installation name) in pipeline- and stage-level `tools {}`; Declarative validation
    rejects names with no matching installation, so each one needs provisioning."""
    if not ir:
        return []
    pairs = list(ir.tools.items())
    for st, _ in ir.iter_stages():
        pairs += st.tools.items()
    return list(dict.fromkeys(pairs))


def provisioning_script(credentials: list[dict[str, Any]], tools: list[tuple[str, str]], text: str) -> str:
    """Groovy (script console) creating *fake* credentials and tool installations referenced by the pipeline."""
    lines = [
        "import com.cloudbees.plugins.credentials.*",
        "import com.cloudbees.plugins.credentials.domains.Domain",
        "import com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl",
        "import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl",
        "import org.jenkinsci.plugins.plaincredentials.impl.FileCredentialsImpl",
        "import com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey",
        "import hudson.util.Secret",
        "def store = jenkins.model.Jenkins.get().getExtensionList('com.cloudbees.plugins.credentials.SystemCredentialsProvider')[0].getStore()",
        "def existing = CredentialsProvider.lookupCredentials(com.cloudbees.plugins.credentials.common.IdCredentials, jenkins.model.Jenkins.get(), null, null).collect { it.id } as Set",
        "def created = []",
    ]
    for c in credentials:
        cid = str(c.get("id") or "")
        if not cid or "$" in cid or cid == "?":
            continue
        t = c.get("type") or "string"
        if t == "credentials()":
            t = "usernamePassword" if re.search(re.escape(cid) + r"|_USR|_PSW", text) and re.search(r"_(USR|PSW)\b", text) else "string"
        q = json.dumps(cid)
        desc = "'j2gha fake credential (local testing only)'"
        if t in ("usernamePassword", "usernameColonPassword"):
            make = (f"new UsernamePasswordCredentialsImpl(CredentialsScope.GLOBAL, {q}, {desc}, '{FAKE_USER}', "
                    f"'{FAKE_PASSWORD}')")
        elif t == "file":
            make = (f"new FileCredentialsImpl(CredentialsScope.GLOBAL, {q}, {desc}, 'j2gha.txt', "
                    "com.cloudbees.plugins.credentials.SecretBytes.fromBytes('j2gha-fake'.bytes))")
        elif t == "sshUserPrivateKey":
            make = (f"new BasicSSHUserPrivateKey(CredentialsScope.GLOBAL, {q}, 'j2gha', "
                    "new BasicSSHUserPrivateKey.DirectEntryPrivateKeySource('j2gha-fake-key'), '', " + desc + ")")
        elif t == "aws":  # [$class: 'AmazonWebServicesCredentialsBinding'] (aws-credentials plugin)
            make = (f"new com.cloudbees.jenkins.plugins.awscredentials.AWSCredentialsImpl(CredentialsScope.GLOBAL, {q}, "
                    f"'{FAKE_USER}', '{FAKE_PASSWORD}', {desc})")
        else:
            make = f"new StringCredentialsImpl(CredentialsScope.GLOBAL, {q}, {desc}, Secret.fromString('{FAKE_SECRET}'))"
        lines.append(f"if (!existing.contains({q})) {{ store.addCredentials(Domain.global(), {make}); created << {q} }}")
    tool_map = {
        "maven": ("hudson.tasks.Maven$MavenInstallation", "hudson.tasks.Maven$DescriptorImpl", "/usr/share/maven"),
        "jdk": ("hudson.model.JDK", "hudson.model.JDK$DescriptorImpl", "/opt/java/openjdk"),
        "nodejs": ("jenkins.plugins.nodejs.tools.NodeJSInstallation",
                   "jenkins.plugins.nodejs.tools.NodeJSInstallation$DescriptorImpl", "/usr"),
    }
    for kind, name in tools:
        if kind not in tool_map or not name:
            continue
        cls, desc_cls, home = tool_map[kind]
        qn = json.dumps(name)
        if kind == "nodejs":
            ctor = f"new {cls.replace('$', '.')}({qn}, '{home}', [])"
        elif kind == "maven":
            ctor = f"new hudson.tasks.Maven.MavenInstallation({qn}, '{home}', [])"
        else:
            ctor = f"new hudson.model.JDK({qn}, '{home}')"
        lines.append(
            f"try {{ def d = jenkins.model.Jenkins.get().getDescriptorByType({desc_cls.replace('$', '.')}); "
            f"def inst = (d.installations as List).findAll {{ it.name != {qn} }}; inst << {ctor}; "
            f"d.setInstallations(inst as {cls.replace('$', '.')}[]); created << 'tool:' + {qn} }} "
            f"catch (Throwable t) {{ println 'tool ' + {qn} + ' failed: ' + t }}")
    lines.append("println 'provisioned: ' + created")
    return "\n".join(lines)
