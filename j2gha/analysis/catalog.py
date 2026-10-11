"""Step catalog lookups (rules/steps.yaml)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES = Path(__file__).resolve().parent.parent / "rules" / "steps.yaml"

# Declarative directives / sub-directives that are structure, not steps.
DIRECTIVES = {
    "pipeline", "agent", "stages", "stage", "steps", "post", "when", "environment", "options", "parameters",
    "triggers", "tools", "matrix", "axes", "axis", "excludes", "exclude", "parallel", "libraries", "lib",
    "input", "failFast", *("always changed fixed regression aborted failure success unstable unsuccessful "
                            "notBuilt cleanup").split(),
}

# Plain Groovy/JDK methods commonly called in pipelines; not Jenkins steps.
GROOVY_METHODS = set("""
trim split tokenize toString toInteger toBoolean toLowerCase toUpperCase replace replaceAll contains startsWith
endsWith substring size length each eachWithIndex collect collectEntries findAll find any every join keySet values
get put add addAll remove sort unique first last isEmpty readLines matches equals format println print
getAt putAt plus minus inject sum max min count take drop reverse flatten asType toList toSet containsKey
""".split())

@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    return yaml.safe_load(RULES.read_text())


def lookup(name: str) -> dict[str, Any] | None:
    steps = load_catalog()["steps"]
    if name in steps:
        return steps[name]
    if name == "docker" or name.startswith("docker."):
        # the docker-workflow global (docker.image(x).inside, docker.build...); a bare step that merely starts with
        # "docker" (dockerLogin, dockerLoginH2OECR: shared-library globals) is not it
        for key in ("docker.build", "docker.image", "docker.withRegistry", "docker.withServer"):
            if key.split(".", 1)[1] in name:
                return steps[key]
        return steps.get("docker.script")
    return None


def categorise(name: str) -> str:
    entry = lookup(name)
    return entry["category"] if entry else "unknown"


def weight(name: str) -> float:
    entry = lookup(name)
    return float(entry.get("weight", 1)) if entry else 2.0


def target(name: str) -> str | None:
    entry = lookup(name)
    return entry.get("gha") if entry else None


def hard_gate_patterns() -> list[dict[str, str]]:
    return load_catalog().get("hard_gates", [])
