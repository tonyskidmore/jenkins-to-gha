"""Groovy AST extraction (via Jenkins' bundled Groovy in Docker) and tree-walking helpers.

The dumper (docker/jenkins/groovy/ast_dump.groovy) emits a JSON projection where each method
call is a ``{"k": "call", "name": ..., "args": [...], "named": {...}, "body": [...]}`` node.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ..config import CACHE_DIR, DOCKER_DIR, JENKINS_IMAGE


class AstUnavailable(RuntimeError):
    pass


def docker_image_exists(image: str) -> bool:
    try:
        out = subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=30)
        return out.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def dump_sources(sources: dict[str, str], image: str = JENKINS_IMAGE, timeout: int = 900) -> dict[str, dict]:
    """Parse many Groovy sources in a single container run. ``sources`` maps key -> source text."""
    if not sources:
        return {}
    if not docker_image_exists(image):
        raise AstUnavailable(f"docker image {image} not found - run `j2gha docker build`")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ast-", dir=CACHE_DIR))
    try:
        names: dict[str, str] = {}
        for i, (key, text) in enumerate(sources.items()):
            fname = f"src{i:05d}.groovy"
            (work / fname).write_text(text, encoding="utf-8")
            names[fname] = key
        # Mount the current dumper script over the baked-in copy so edits take effect without rebuilds.
        dumper = DOCKER_DIR / "jenkins" / "groovy" / "ast_dump.groovy"
        cmd = ["docker", "run", "--rm", "--network", "none", "-v", f"{work}:/work", "-w", "/work"]
        if dumper.exists():
            cmd += ["-v", f"{dumper}:/opt/j2gha/ast_dump.groovy:ro"]
        cmd += ["--entrypoint", "j2gha-ast", image, *names.keys()]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise AstUnavailable(f"AST dumper failed ({proc.returncode}): {proc.stderr[-2000:]}")
        results = json.loads(proc.stdout)
        out: dict[str, dict] = {}
        for r in results:
            key = names.get(Path(r.get("file", "")).name)
            if key is not None:
                r["file"] = key
                out[key] = r
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def dump_source(text: str, name: str = "Jenkinsfile", image: str = JENKINS_IMAGE) -> dict:
    return dump_sources({name: text}, image=image)[name]


# --------------------------------------------------------------------------- walking
@dataclass
class CallCtx:
    """A call node plus where it sits in the pipeline structure."""

    node: dict
    path: list[str] = field(default_factory=list)  # enclosing call names, outermost first
    stages: list[str] = field(default_factory=list)  # enclosing stage names
    in_script: bool = False  # inside a declarative script {} block or a scripted pipeline
    in_method: str | None = None  # defined inside a script-level method
    in_loop: bool = False
    in_args: bool = False  # nested inside another call's arguments (e.g. recordIssues(tools: [java()]))
    ancestors: list[dict] = field(default_factory=list)  # enclosing call nodes, outermost first (path's nodes)

    @property
    def name(self) -> str:
        return self.node.get("name", "")

    @property
    def line(self) -> int | None:
        return self.node.get("line")


def literal(value: dict | None) -> Any:
    """Return the Python literal for a dumper value, or None if not a literal."""
    if not value:
        return None
    t = value.get("t")
    if t in ("str", "num", "bool"):
        return value.get("v")
    if t == "list":
        items = [literal(v) for v in value.get("v", [])]
        return items if all(i is not None for i in items) else None
    if t == "map":
        return {k: literal(v) for k, v in value.get("v", {}).items()}
    if t == "concat":
        parts = [literal(p) for p in _concat_parts(value)]
        return "".join(str(p) for p in parts) if all(isinstance(p, (str, int, float)) for p in parts) else None
    return None


def _concat_parts(value: dict) -> list[dict]:
    out = []
    for p in value.get("parts", []):
        out.extend(_concat_parts(p) if p and p.get("t") == "concat" else [p])
    return out


def value_text(value: dict | None) -> str:
    """Best-effort source-ish rendering of a dumper value."""
    if not value:
        return ""
    t = value.get("t")
    if t == "str":
        return str(value.get("v"))
    if t in ("num", "bool", "const"):
        return str(value.get("v"))
    if t == "null":
        return "null"
    if t == "gstr":
        v = _cut_gstring((value.get("v") or "").strip())
        for q in ('"""', "'''", '"', "'"):
            if len(v) >= 2 * len(q) and v.startswith(q) and v.endswith(q):
                return _unescape(v[len(q):-len(q)])
        return _unescape(v)
    if t == "list":
        return "[" + ", ".join(value_text(v) for v in value.get("v", [])) + "]"
    if t == "map":
        return "[" + ", ".join(f"{k}: {value_text(v)}" for k, v in value.get("v", {}).items()) + "]"
    if t == "var":
        return value.get("name", "")
    if t == "concat":
        # 'tar -f ' + packname -> GString-like text so downstream translation treats variables uniformly
        out = []
        for p in _concat_parts(value):
            lit = literal(p)
            if isinstance(lit, (str, int, float)):
                out.append(str(lit))
            elif p and p.get("t") == "gstr":
                out.append(value_text(p))
            elif p and p.get("t") == "var":
                out.append("${" + p.get("name", "") + "}")
            else:
                out.append("${" + (value_text(p) or "?") + "}")
        return "".join(out)
    if t == "call":
        c = value.get("call", {})
        return f"{c.get('receiver') + '.' if c.get('receiver') else ''}{c.get('name')}(...)"
    return value.get("text", "") or ""


def _cut_gstring(v: str) -> str:
    """Groovy 2.4 reports GString end columns past the closing quote (to end of line, comments included).
    Cut the source at the real closing delimiter, honouring escapes and ${...} nesting."""
    for q in ('"""', "'''", '"', "/"):
        if v.startswith(q):
            break
    else:
        return v
    i, depth = len(q), 0
    while i < len(v):
        ch = v[i]
        if ch == "\\":
            i += 2
            continue
        if v.startswith("${", i):
            depth += 1
            i += 2
            continue
        if ch == "}" and depth:
            depth -= 1
        elif depth == 0 and v.startswith(q, i):
            return v[: i + len(q)]
        i += 1
    return v


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "\\": "\\", "$": "$", '"': '"', "'": "'"}


def _unescape(text: str) -> str:
    """Apply Groovy string escapes to raw GString source (constants arrive already unescaped)."""
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), "\\" + m.group(1)), text)


def first_arg(node: dict, *names: str) -> dict | None:
    """First positional argument, or a named argument from ``names``."""
    for n in names:
        if n in node.get("named", {}):
            return node["named"][n]
    args = node.get("args") or []
    return args[0] if args else None


def unchain(node: dict) -> list[dict]:
    """Groovy parses ``stage('a') {..} stage('b') {..}`` on one line as a command chain
    (``stage('a', {..}).stage('b', {..})``). Unroll such chains back into sibling calls."""
    rcs = node.get("receiverCalls") or []
    if node.get("receiver") and len(rcs) == 1 and rcs[0].get("body") is not None and node.get("body") is not None:
        head = {k: v for k, v in node.items() if k not in ("receiver", "receiverCalls")}
        return unchain(rcs[0]) + [head]
    return [node]


def child_calls(body: list[dict] | None, name: str | None = None) -> list[dict]:
    out = []
    for s in body or []:
        if s.get("k") != "call":
            continue
        for c in unchain(s):
            if name is None or c.get("name") == name:
                out.append(c)
    return out


def iter_statement_children(stmt: dict) -> Iterator[tuple[list[dict], dict]]:
    """Yield (statement-list, attrs) for every nested statement list inside a statement."""
    k = stmt.get("k")
    if k == "call":
        if stmt.get("body"):
            yield stmt["body"], {}
        for v in list(stmt.get("args", [])) + list(stmt.get("named", {}).values()):
            for body, attrs in _value_children(v):
                yield body, {**attrs, "args": True}
        for rc in stmt.get("receiverCalls", []) or []:
            yield [rc], {}
    elif k == "if":
        yield [c for c in stmt.get("condCalls", []) if c.get("k") == "call"], {}
        yield stmt.get("then", []), {}
        yield stmt.get("else", []), {}
    elif k in ("for", "while"):
        yield [c for c in stmt.get("collectionCalls", []) if c.get("k") == "call"], {}
        yield stmt.get("body", []), {"loop": True}
    elif k == "try":
        yield stmt.get("body", []), {}
        for c in stmt.get("catches", []):
            yield c.get("body", []), {}
        yield stmt.get("finally", []), {}
    elif k == "switch":
        for c in stmt.get("cases", []):
            yield c.get("body", []), {}
        yield stmt.get("default", []), {}
    elif k in ("decl", "assign", "return"):
        yield from _value_children(stmt.get("value"))
    elif k in ("expr", "throw"):
        yield from _calls_as_statements(stmt.get("calls", []))
    elif k == "synchronized":
        yield stmt.get("body", []), {}


def _calls_as_statements(calls: list[dict]) -> Iterator[tuple[list[dict], dict]]:
    stmts = []
    for c in calls or []:
        if c.get("k") == "call":
            stmts.append(c)
        elif c.get("k") == "closure":
            yield c.get("body", []), {}
    if stmts:
        yield stmts, {}


def _value_children(v: dict | None) -> Iterator[tuple[list[dict], dict]]:
    if not v:
        return
    t = v.get("t")
    if t == "call":
        yield [v["call"]], {}
    elif t == "closure":
        yield v.get("body", []), {"closure": True}
    elif t == "list":
        for x in v.get("v", []):
            yield from _value_children(x)
    elif t == "map":
        for x in v.get("v", {}).values():
            yield from _value_children(x)
    elif t in ("gstr", "prop", "expr"):
        yield from _calls_as_statements(v.get("calls", []))
    elif t == "concat":
        for part in v.get("parts", []):
            yield from _value_children(part)


def walk_calls(statements: list[dict], ctx: CallCtx | None = None) -> Iterator[CallCtx]:
    """Depth-first walk over every call node, tracking pipeline context."""
    base = ctx or CallCtx(node={})
    for stmt in statements or []:
        if stmt.get("k") == "call":
            name = stmt.get("name", "")
            # pipeline {} is the Declarative root even inside a method (shared-library template `def call()`)
            in_script = base.in_script and not (name == "pipeline" and stmt.get("body") is not None)
            here = CallCtx(node=stmt, path=list(base.path), stages=list(base.stages), in_script=in_script,
                           in_method=base.in_method, in_loop=base.in_loop, in_args=base.in_args,
                           ancestors=list(base.ancestors))
            yield here
            child = CallCtx(node={}, path=base.path + [name], stages=list(base.stages), in_script=in_script,
                            in_method=base.in_method, in_loop=base.in_loop, ancestors=base.ancestors + [stmt])
            if name == "stage":
                label = value_text(first_arg(stmt, "name"))
                child.stages = base.stages + [label or "?"]
            if name == "script":
                child.in_script = True
            for body, attrs in iter_statement_children(stmt):
                # closures passed as arguments (parallel a: {..}) are executed bodies, not symbols
                is_sym = attrs.get("args", False) and not attrs.get("closure", False)
                sub = CallCtx(node={}, path=child.path, stages=child.stages, in_script=child.in_script,
                              in_method=child.in_method, in_loop=child.in_loop or attrs.get("loop", False),
                              in_args=child.in_args or is_sym, ancestors=child.ancestors)
                yield from walk_calls(body, sub)
        else:
            for body, attrs in iter_statement_children(stmt):
                sub = CallCtx(node={}, path=base.path, stages=base.stages, in_script=base.in_script,
                              in_method=base.in_method, in_loop=base.in_loop or attrs.get("loop", False),
                              ancestors=base.ancestors)
                yield from walk_calls(body, sub)


def walk_statements(statements: list[dict]) -> Iterator[dict]:
    """Every statement node (calls included), depth first."""
    for stmt in statements or []:
        yield stmt
        for body, _ in iter_statement_children(stmt):
            yield from walk_statements(body)


def all_calls(ast: dict) -> Iterator[CallCtx]:
    yield from walk_calls(ast.get("statements", []))
    for m in ast.get("methods", []):
        yield from walk_calls(m.get("body", []), CallCtx(node={}, in_method=m.get("name"), in_script=True))
    for c in ast.get("classes", []):
        for m in c.get("methods", []):
            yield from walk_calls(m.get("body", []), CallCtx(node={}, in_method=f"{c.get('name')}.{m.get('name')}",
                                                             in_script=True))
