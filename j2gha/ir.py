"""Canonical migration IR.

A deliberately small, typed model of *what a pipeline does*, independent of both Jenkins internals
and the GitHub Actions schema. Every element keeps source provenance (``line``) so reports can point
back at the Jenkinsfile. Built by ``analysis.declarative`` / ``analysis.scripted``; consumed by
``convert.generator``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Step:
    name: str
    line: int | None = None
    # literal values, or source text for expressions; a list holding runtime values keeps its literal items and
    # marks the others {"expr": <GString/concatenation text>} (withEnv(["A=${x}", 'B=y']))
    args: list[Any] = field(default_factory=list)
    named: dict[str, Any] = field(default_factory=dict)
    body: list["Step"] = field(default_factory=list)  # nested steps (withCredentials {..}, dir {..}, script {..})
    category: str = "unknown"  # catalog category: direct/policy/redesign/dynamic/noop/unknown/local
    receiver: str | None = None  # e.g. docker.image('x') for .inside { }
    source: str | None = None  # raw Groovy for script blocks / dynamic constructs
    dynamic: bool = False  # argument values are runtime expressions (GStrings, variables)
    variable_args: list[int] = field(default_factory=list)  # positions of args that are a bare Groovy variable

    @property
    def qualified(self) -> str:
        return f"{self.receiver}.{self.name}" if self.receiver else self.name


@dataclass
class Agent:
    kind: str  # any | none | label | docker | dockerfile | kubernetes | inherit | unknown
    label: str | None = None
    image: str | None = None
    args: str | None = None
    filename: str | None = None
    dir: str | None = None
    reuse_node: bool = False
    yaml: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    line: int | None = None


@dataclass
class Condition:
    kind: str  # branch | environment | expression | allOf | anyOf | not | tag | buildingTag | changeRequest | changeset | triggeredBy | equals | unknown
    value: Any = None
    name: str | None = None  # environment name
    comparator: str | None = None
    children: list["Condition"] = field(default_factory=list)
    text: str | None = None
    line: int | None = None


@dataclass
class When:
    conditions: list[Condition] = field(default_factory=list)  # implicit allOf
    before_agent: bool = False
    before_input: bool = False
    before_options: bool = False


@dataclass
class EnvValue:
    kind: str  # literal | credentials | expression | shell (command substitution) | call (function)
    value: Any = None
    credential_id: str | None = None
    line: int | None = None


@dataclass
class Parameter:
    kind: str  # string | booleanParam | choice | text | password | other
    name: str
    default: Any = None
    choices: list[Any] = field(default_factory=list)
    description: str | None = None
    line: int | None = None


@dataclass
class Trigger:
    kind: str  # cron | pollSCM | upstream | other
    value: Any = None
    line: int | None = None


@dataclass
class Matrix:
    axes: dict[str, list[Any]] = field(default_factory=dict)
    excludes: list[dict[str, Any]] = field(default_factory=list)
    agent: Agent | None = None
    stages: list["Stage"] = field(default_factory=list)
    when: When | None = None
    post: dict[str, list[Step]] = field(default_factory=dict)  # cell-level: runs in every cell
    # further cell-level directives (apply to every cell)
    environment: dict[str, EnvValue] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    input: dict[str, Any] | None = None
    tools: dict[str, str] = field(default_factory=dict)
    line: int | None = None


@dataclass
class Stage:
    name: str
    line: int | None = None
    agent: Agent | None = None
    environment: dict[str, EnvValue] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    when: When | None = None
    tools: dict[str, str] = field(default_factory=dict)
    input: dict[str, Any] | None = None
    steps: list[Step] = field(default_factory=list)
    parallel: list["Stage"] = field(default_factory=list)
    stages: list["Stage"] = field(default_factory=list)
    matrix: Matrix | None = None
    post: dict[str, list[Step]] = field(default_factory=dict)
    fail_fast: bool = False

    @property
    def kind(self) -> str:
        if self.parallel:
            return "parallel"
        if self.matrix:
            return "matrix"
        if self.stages:
            return "sequential"
        return "steps"


@dataclass
class Pipeline:
    dialect: str  # declarative | scripted
    line: int | None = None
    agent: Agent | None = None
    environment: dict[str, EnvValue] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    parameters: list[Parameter] = field(default_factory=list)
    triggers: list[Trigger] = field(default_factory=list)
    tools: dict[str, str] = field(default_factory=dict)
    libraries: list[str] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)
    post: dict[str, list[Step]] = field(default_factory=dict)
    methods: list[str] = field(default_factory=list)  # script-level helper methods
    method_defs: dict[str, Any] = field(default_factory=dict)  # name -> {"params": [...], "body": [Step]}
    notes: list[str] = field(default_factory=list)  # interpretation caveats

    def to_dict(self) -> dict[str, Any]:
        return _prune(asdict(self))

    def iter_stages(self):
        def rec(stages, depth=0):
            for s in stages:
                yield s, depth
                yield from rec(s.parallel, depth + 1)
                yield from rec(s.stages, depth + 1)
                if s.matrix:
                    yield from rec(s.matrix.stages, depth + 1)
        yield from rec(self.stages)

    def iter_steps(self):
        def rec(steps):
            for st in steps:
                yield st
                yield from rec(st.body)
        for stage, _ in self.iter_stages():
            yield from rec(stage.steps)
            for steps in stage.post.values():
                yield from rec(steps)
            if stage.matrix:
                for steps in stage.matrix.post.values():
                    yield from rec(steps)
        for steps in self.post.values():
            yield from rec(steps)


# credentialsId: "${X}" / "${env.X}": an environment variable naming the credential
CREDENTIAL_REF = re.compile(r"\$\{(?:env\.)?(\w+)\}")


def literal_scope(env: Mapping[str, EnvValue]) -> dict[str, str | None]:
    """An environment block as a resolution scope: name -> its literal value, or None when it is not a literal."""
    return {k: (str(v.value) if v.kind == "literal" and v.value not in (None, "") else None) for k, v in env.items()}


def resolve_credential_id(cid: str, scopes: Iterable[Mapping[str, str | None]]) -> str:
    """The credential id a `${X}` reference selects: the literal value of X in the nearest scope that defines X
    (scopes innermost first: withEnv, stage, ..., pipeline). When that nearest definition is not a literal (None) the
    reference stays unresolved; an outer literal never stands in for it (shared by the analysis inventory and the
    generator, review R8-5)."""
    m = CREDENTIAL_REF.fullmatch(cid)
    if not m:
        return cid
    for scope in scopes:
        if m.group(1) in scope:
            return scope[m.group(1)] or cid
    return cid


def _prune(value: Any) -> Any:
    """Drop empty/default values so serialised IR stays readable."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            v = _prune(v)
            if v in (None, [], {}, False, ""):
                continue
            out[k] = v
        return out
    if isinstance(value, list):
        return [_prune(v) for v in value]
    return value
