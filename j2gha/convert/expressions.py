"""Translate Jenkins `when` conditions and simple Groovy boolean expressions into GHA `if:` expressions.

All conditions are expressed against the `env` context (Jenkins semantics are env-based too). The workflow defines
Jenkins-compatible variables (BRANCH_NAME, TAG_NAME, CHANGE_ID, ...) at workflow level, and parameters are
exported as env vars, so `params.X` / `env.X` / bare `X` all map to `env.X`.

Returns ``(expression, status)`` where status is ``mapped``, ``approximated`` or ``manual``. ``None`` expression
means "no condition".
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any

from ..ir import Condition, When

# Groovy script variables the generator exports to the env context (`target = 'pro'` in an if/else chain), so a
# later `expression { target == 'pro' }` translates to env.target. Set for the duration of one conversion.
SCRIPT_VARS: ContextVar[frozenset[str]] = ContextVar("SCRIPT_VARS", default=frozenset())

# Declared pipeline parameters (name -> kind: booleanParam, string, choice, ...) for one conversion. A bare `params.X`
# is Groovy truth: 'true'/'false' for a boolean parameter, non-empty for anything else (a string "false" is truthy).
# None (outside a conversion): every parameter is read as a boolean.
PARAM_TYPES: ContextVar[dict[str, str] | None] = ContextVar("PARAM_TYPES", default=None)

STATUS_RANK = {"mapped": 0, "approximated": 1, "manual": 2}


def _worst(*statuses: str) -> str:
    return max(statuses, key=lambda s: STATUS_RANK[s]) if statuses else "mapped"


def q(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def glob_condition(var: str, pattern: str | None, comparator: str | None = None,
                   line: int | None = None, negated: bool = False) -> tuple[str, str]:
    if pattern is None:
        return f"{var} != ''", "mapped"
    comparator = (comparator or "GLOB").upper()
    if comparator == "REGEXP":
        return regexp_condition(var, pattern, line, negated)
    if comparator == "EQUALS" or not any(ch in pattern for ch in "*?"):
        return f"{var} == {q(pattern)}", "mapped"
    exact = _ant_condition(var, pattern)
    if exact:
        return exact
    return manual_gate(line, negated), "manual"


def _ant_condition(var: str, pattern: str) -> tuple[str, str] | None:
    """A GHA expression for the Ant-style patterns that have one, else None. In Ant `*` stays inside one path
    segment (no `/`), `?` is a single character and `**` spans segments. GHA expressions have no regex, substring or
    length: `contains`/`startsWith`/`endsWith` express the shapes below exactly, except `prefix/*`, where "no further
    `/` after the prefix" cannot be said - that one is `approximated` (it also matches `prefix/a/b`)."""
    if "?" in pattern:
        return None
    stars = pattern.count("*")
    if pattern == "**":
        return f"{var} != ''", "mapped"
    if pattern == "*":
        return f"({var} != '' && !contains({var}, '/'))", "mapped"
    if pattern.endswith("/**") and stars == 2:
        base = pattern[:-3]
        return f"({var} == {q(base)} || startsWith({var}, {q(base + '/')}))", "mapped"  # `**` also matches zero segments
    if stars == 1 and pattern.endswith("*"):
        prefix = pattern[:-1]
        if "/" in prefix:
            return f"startsWith({var}, {q(prefix)})", "approximated"
        return f"(startsWith({var}, {q(prefix)}) && !contains({var}, '/'))", "mapped"
    if stars == 1 and pattern.startswith("*") and "/" not in pattern:
        return f"(endsWith({var}, {q(pattern[1:])}) && !contains({var}, '/'))", "mapped"
    return None


REGEX_META = re.compile(r"[.^$*+?()\[\]{}|\\]")


def regexp_condition(var: str, pattern: str, line: int | None = None, negated: bool = False) -> tuple[str, str]:
    """Jenkins REGEXP comparators use Java `matches()` (whole value). Literal patterns, `prefix.*`, `.*suffix`,
    `.*part.*` and literal alternations translate exactly; anything else needs a manual gate."""
    body = pattern[1:] if pattern.startswith("^") else pattern
    body = body[:-1] if body.endswith("$") and not body.endswith("\\$") else body

    def lit(t: str) -> bool:
        return bool(t) and not REGEX_META.search(t)

    if lit(body):
        return f"{var} == {q(body)}", "mapped"
    if body.endswith(".*") and lit(body[:-2]) and not body.startswith(".*"):
        return f"startsWith({var}, {q(body[:-2])})", "mapped"
    if body.startswith(".*") and body.endswith(".*") and lit(body[2:-2]):
        return f"contains({var}, {q(body[2:-2])})", "mapped"
    if body.startswith(".*") and lit(body[2:]):
        return f"endsWith({var}, {q(body[2:])})", "mapped"
    alts = (body[1:-1] if body.startswith("(") and body.endswith(")") else body).split("|")
    if len(alts) > 1 and all(lit(a) for a in alts):
        return "(" + " || ".join(f"{var} == {q(a)}" for a in alts) + ")", "mapped"
    return manual_gate(line, negated), "manual"


def manual_gate(line: int | None, negated: bool = False) -> str:
    """An untranslatable condition becomes a repository variable: 'true'/'false' state its value. Unset, it takes
    the value that keeps the stage *off*, so the stage runs only where it would run whatever the condition's value:
    false where the condition is used positively, true under an odd number of `not`s."""
    var = f"vars.J2GHA_WHEN_L{line or 0}"
    return f"{var} != 'false'" if negated else f"{var} == 'true'"


# changeRequest(<field>: pattern) filters -> Jenkins-compatible env defined at workflow level (generator.JENKINS_ENV)
CHANGE_FIELDS = {"id": "env.CHANGE_ID", "target": "env.CHANGE_TARGET", "branch": "env.CHANGE_BRANCH",
                 "author": "env.CHANGE_AUTHOR", "title": "env.CHANGE_TITLE", "url": "env.CHANGE_URL"}


def condition_expr(c: Condition, negated: bool = False) -> tuple[str, str]:
    """``negated``: the condition sits under an odd number of `not`s (decides how manual gates default)."""
    k = c.kind
    if k in ("branch", "tag") and c.value and "${" in str(c.value):
        # GString pattern, e.g. branch "${env.BRANCH_NAME}" or branch "${env.RELEASE_BRANCH}"
        m = re.fullmatch(r"\$\{(?:env\.|params\.)?([A-Za-z_]\w*)\}", str(c.value))
        var = "env.BRANCH_NAME" if k == "branch" else "env.TAG_NAME"
        if m:
            return f"{var} == env.{m.group(1)}", "approximated"
        return manual_gate(c.line, negated), "manual"
    if k == "branch":
        return glob_condition("env.BRANCH_NAME", c.value, c.comparator, c.line, negated)
    if k == "tag":
        return glob_condition("env.TAG_NAME", c.value, c.comparator, c.line, negated)
    if k == "buildingTag":
        return "env.TAG_NAME != ''", "mapped"
    if k == "changeRequest":
        filters = dict(c.value) if isinstance(c.value, dict) else {}
        comparator = filters.pop("comparator", None)
        parts, statuses = ["env.CHANGE_ID != ''"], ["mapped"]
        for key, pattern in filters.items():
            e, s = (glob_condition(CHANGE_FIELDS[key], str(pattern), comparator, c.line, negated)
                    if key in CHANGE_FIELDS else (manual_gate(c.line, negated), "manual"))
            parts.append(f"({e})")
            statuses.append(s)
        return (parts[0] if len(parts) == 1 else "(" + " && ".join(parts) + ")"), _worst(*statuses)
    if k == "environment":
        return f"env.{c.name} == {q(c.value)}", "mapped"
    if k == "equals":
        exp = _equals_operand((c.value or {}).get("expected", ""))
        act = _equals_operand((c.value or {}).get("actual", ""))
        if exp and act:
            return f"({act}) == ({exp})", "approximated"
        return manual_gate(c.line, negated), "manual"
    if k == "expression":
        expr = translate_groovy(c.text or "")
        return (expr, "approximated") if expr else (manual_gate(c.line, negated), "manual")
    if k in ("allOf", "anyOf"):
        parts = [condition_expr(x, negated) for x in c.children]
        joiner = " && " if k == "allOf" else " || "
        return "(" + joiner.join(p[0] for p in parts) + ")", _worst(*(p[1] for p in parts))
    if k == "not":
        if not c.children:
            return manual_gate(c.line, negated), "manual"
        e, s = condition_expr(c.children[0] if len(c.children) == 1 else Condition(kind="allOf", children=c.children),
                              not negated)
        return f"!({e})", s
    if k in ("changeset", "changelog"):
        # needs the build's changed files / commit messages: never assume they match
        return manual_gate(c.line, negated), "manual"
    if k == "triggeredBy":
        cause = str((c.value or {}).get("_", "") or (c.value or {}).get("cause", ""))
        mapping = {"TimerTrigger": "schedule", "SCMTrigger": "push", "UserIdCause": "workflow_dispatch",
                   "BranchIndexingCause": "push", "UpstreamCause": "workflow_run"}
        for key, ev in mapping.items():
            if key in cause:
                return f"github.event_name == {q(ev)}", "approximated"
        return manual_gate(c.line, negated), "manual"
    if k == "isRestartedRun":
        return "github.run_attempt > 1", "approximated"
    return manual_gate(c.line, negated), "manual"


def _equals_operand(src: str) -> str | None:
    """`"${params.X}"` (a GString of one interpolation) compares as the expression itself."""
    m = re.fullmatch(r"\$\{([^{}]+)\}", (src or "").strip())
    return translate_value(m.group(1) if m else src)


def when_expr(when: When | None) -> tuple[str | None, str]:
    if when is None or not when.conditions:
        return None, "mapped"
    parts = [condition_expr(c) for c in when.conditions]
    expr = " && ".join(f"({p[0]})" if len(parts) > 1 else p[0] for p in parts)
    return expr, _worst(*(p[1] for p in parts))


# ---------------------------------------------------------------------------------------------------------------
# A tiny Groovy boolean-expression translator (recursive descent). Supports literals, params./env./bare variables,
# == != && || ! parentheses, .equals/.startsWith/.endsWith/.contains/.toBoolean() and `return` prefixes.
TOKEN_RE = re.compile(r"""
    \s*(?:
      (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\$]|\\.)*")
     |(?P<num>\d+(?:\.\d+)?)
     |(?P<op>==|!=|&&|\|\||!|\(|\)|,|\?\.|\.)
     |(?P<id>[A-Za-z_][A-Za-z0-9_]*)
    )""", re.X)


class _Fail(Exception):
    pass


def _tokens(src: str) -> list[tuple[str, str]]:
    toks = []
    pos = 0
    src = src.strip()
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m or m.end() == pos:
            raise _Fail(src[pos:pos + 20])
        kind = m.lastgroup
        toks.append((kind, m.group(kind)))
        pos = m.end()
        while pos < len(src) and src[pos].isspace():
            pos += 1
    return toks


def translate_groovy(src: str) -> str | None:
    s = (src or "").strip().rstrip(";").strip()
    s = re.sub(r"^return\s+", "", s)
    if not s or "\n" in s or ";" in s:
        return None
    try:
        toks = _tokens(s)
        p = _Parser(toks)
        out = p.expr()
        if p.i != len(toks):
            return None
        return out
    except (_Fail, IndexError):
        return None


def translate_value(src: str) -> str | None:
    """Translate a single Groovy value (literal / env / params / currentBuild.result) without boolean coercion."""
    s = (src or "").strip()
    if not s:
        return None
    try:
        toks = _tokens(s)
        p = _Parser(toks)
        out, _ = p.unary()
        return out if p.i == len(toks) else None
    except (_Fail, IndexError):
        return None


class _Parser:
    def __init__(self, toks: list[tuple[str, str]]):
        self.t = toks
        self.i = 0

    def peek(self) -> tuple[str, str] | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, value: str | None = None) -> tuple[str, str]:
        tok = self.t[self.i]
        if value is not None and tok[1] != value:
            raise _Fail(value)
        self.i += 1
        return tok

    def expr(self) -> str:
        left = self.and_()
        while self.peek() and self.peek()[1] == "||":
            self.take()
            left = f"{left} || {self.and_()}"
        return left

    def and_(self) -> str:
        left = self.cmp()
        while self.peek() and self.peek()[1] == "&&":
            self.take()
            left = f"{left} && {self.cmp()}"
        return left

    def cmp(self) -> str:
        left, ltype = self.unary()
        tok = self.peek()
        if tok and tok[1] in ("==", "!="):
            op = self.take()[1]
            right, rtype = self.unary()
            # booleans compare as strings because env values are strings
            if rtype == "bool":
                right = q(right)
            if ltype == "bool":
                left = q(left)
            return f"{left} {op} {right}"
        if ltype == "var":
            return self._param_truth(left, negate=False)
        if ltype == "envvar":
            return f"{left} != ''"  # Groovy truth of a string: non-empty
        return left

    def unary(self) -> tuple[str, str]:
        tok = self.peek()
        if tok and tok[1] == "!":
            self.take()
            inner, typ = self.unary()
            if typ == "var":
                return self._param_truth(inner, negate=True), "bool-expr"
            if typ == "envvar":
                return f"{inner} == ''", "bool-expr"
            return f"!({inner})", "bool-expr"
        return self.primary()

    def primary(self) -> tuple[str, str]:
        kind, val = self.take()
        if val == "(":
            e = self.expr()
            self.take(")")
            return f"({e})", "bool-expr"
        if kind == "str":
            return q(val[1:-1]), "str"
        if kind == "num":
            return val, "num"
        if kind == "id":
            if val in ("true", "false"):
                return val, "bool"
            if val == "null":
                return "''", "str"
            name = self._qualified(val)
            # method suffixes
            while self.peek() and self.peek()[1] in (".", "?."):
                self.take()
                _, meth = self.take()
                if meth in ("toBoolean",):
                    self._call_args(0)
                    return f"{name} == 'true'", "bool-expr"
                if meth in ("toString", "toLowerCase", "toUpperCase"):  # GHA comparisons ignore case anyway
                    self._call_args(0)
                    continue
                if meth in ("equals", "equalsIgnoreCase"):
                    arg = self._call_args(1)[0]
                    return f"{name} == {arg}", "bool-expr"
                if meth in ("startsWith", "endsWith", "contains"):
                    arg = self._call_args(1)[0]
                    return f"{meth}({name}, {arg})", "bool-expr"
                raise _Fail(meth)
            return name, ("var" if self._last_kind == "param" else "envvar")
        raise _Fail(val)

    _last_kind = "envvar"

    @staticmethod
    def _param_truth(ref: str, negate: bool) -> str:
        types = PARAM_TYPES.get()
        kind = "booleanParam" if types is None else types.get(ref.removeprefix("env."))
        if kind is None:
            raise _Fail(ref)  # not a declared parameter: its type, so its truth, is unknown
        if kind == "booleanParam":
            return f"{ref} != 'true'" if negate else f"{ref} == 'true'"
        return f"{ref} == ''" if negate else f"{ref} != ''"

    def _qualified(self, first: str) -> str:
        if first in ("params", "env"):
            self.take(".")
            _, name = self.take()
            self._last_kind = "param" if first == "params" else "envvar"
            return f"env.{name}"
        self._last_kind = "envvar"
        if first == "currentBuild":
            self.take(".")
            _, prop = self.take()
            if prop in ("result", "currentResult"):
                return "job.status"
            raise _Fail(prop)
        if first[0].isupper() or first.startswith("BRANCH") or first.startswith("GIT_") or first in SCRIPT_VARS.get():
            return f"env.{first}"
        raise _Fail(first)  # Groovy local variable - unknown at compile time

    def _call_args(self, n: int) -> list[str]:
        self.take("(")
        args = []
        while self.peek() and self.peek()[1] != ")":
            kind, val = self.take()
            if kind != "str":
                raise _Fail(val)
            args.append(q(val[1:-1]))
            if self.peek() and self.peek()[1] == ",":
                self.take()
        self.take(")")
        if len(args) != n:
            raise _Fail("arity")
        return args


# ---------------------------------------------------------------------------------------------------------------
# Groovy conditions -> a bash [[ ]] test, for if/else chains run as one shell step. Operands are env/params/known
# variables and string literals; == != ==~ (full match) =~ (find) && || ! and parentheses.
BASH_TOKEN_RE = re.compile(r"""
    \s*(?:
      (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\$]|\\.)*")
     |(?P<re>/(?:[^/\\]|\\.)+/)
     |(?P<op>==~|=~|==|!=|&&|\|\||!|\(|\))
     |(?P<id>[A-Za-z_][\w.]*)
    )""", re.X)


def bash_condition(src: str, regexes: list[str]) -> str | None:
    """Translate a Groovy condition into the body of a bash `[[ ]]` test. Regexes are appended to ``regexes`` and
    referenced as ``$j2gha_re<N>`` (bash only treats an unquoted variable as a regex)."""
    toks, pos, text = [], 0, (src or "").strip()
    while pos < len(text):
        m = BASH_TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            return None
        toks.append((m.lastgroup, m.group(m.lastgroup)))
        pos = m.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
    i = 0

    def peek() -> str | None:
        return toks[i][1] if i < len(toks) else None

    def take() -> tuple[str, str]:
        nonlocal i
        i += 1
        return toks[i - 1]

    def operand() -> str:
        kind, val = take()
        if kind == "str":
            return "'" + val[1:-1].replace("\\'", "'").replace("'", "'\\''") + "'" if val[0] == "'" else \
                "'" + val[1:-1].replace('\\"', '"').replace("'", "'\\''") + "'"
        if kind == "id":
            name = re.sub(r"^(env|params)\.", "", val)
            if "." in name or not (name[0].isupper() or name in SCRIPT_VARS.get() or val != name):
                raise _Fail(val)
            return f'"${{{name}}}"'
        raise _Fail(val)

    def cmp() -> str:
        if peek() == "!":
            take()
            return f"! {cmp()}"
        if peek() == "(":
            take()
            e = expr()
            if take()[1] != ")":
                raise _Fail(")")
            return f"( {e} )"
        left = operand()
        op = peek()
        if op in ("==", "!="):
            take()
            return f"{left} {op} {operand()}"
        if op in ("==~", "=~"):
            take()
            kind, val = take()
            if kind != "re":
                raise _Fail(val)
            pattern = _ere(val[1:-1])
            regexes.append(f"^({pattern})$" if op == "==~" else pattern)
            return f"{left} =~ $j2gha_re{len(regexes)}"
        return f"-n {left}"  # Groovy truth of a string

    def expr() -> str:
        parts = [and_()]
        while peek() == "||":
            take()
            parts.append(and_())
        return " || ".join(parts)

    def and_() -> str:
        parts = [cmp()]
        while peek() == "&&":
            take()
            parts.append(cmp())
        return " && ".join(parts)

    try:
        out = expr()
        return out if i == len(toks) else None
    except (_Fail, IndexError):
        return None


def _ere(java: str) -> str:
    """Java regex -> POSIX ERE for bash; constructs ERE lacks (non-capturing/look-around groups) are refused."""
    if "(?" in java or "\\b" in java or "\\Q" in java:
        raise _Fail(java)
    return java.replace("\\d", "[0-9]").replace("\\D", "[^0-9]").replace("\\/", "/")
