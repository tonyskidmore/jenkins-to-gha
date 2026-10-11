"""Evaluation helpers for improving the conversion rules (docs/self-improvement.md).

    gaps        which Jenkins steps the corpus uses that the converter does not map, ranked by cost
    scoreboard  one row per example from the harness artifacts; compared with the committed baseline
    guard       fail when a change touches the files that decide how results are judged

Everything is read from artifacts the other stages already write. Nothing here runs Jenkins, Docker or a model.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import config
from .analysis.catalog import load_catalog

EVALS = "evals"
UNMAPPED = ("policy", "redesign", "dynamic", "unknown")


def _load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text()) if p.exists() else {}


def _root() -> Path:
    return config.ROOT


def holdout_ids() -> set[str]:
    p = _root() / EVALS / "holdout.txt"
    if not p.exists():
        return set()
    return {ln.split("#")[0].strip() for ln in p.read_text().splitlines() if ln.split("#")[0].strip()}


# ----------------------------------------------------------------------------------------------------------- gaps


_STEP_NAME = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*")


def gaps(ids: list[str] | None = None, examples_dir: Path | None = None, include_holdout: bool = False,
         unmapped_only: bool = False) -> list[dict]:
    """Steps that analysis categorised as policy/redesign/dynamic/unknown, ranked by occurrences x weight.

    Holdout examples are left out unless asked for, so a change is not tuned to the examples that validate it.
    `unmapped_only` keeps steps that are not in the catalog or that a migration report lists as `manual`, which drops
    policy steps the generator already approximates. Names that are not identifiers (parse debris) are always dropped.
    """
    root = examples_dir or config.EXAMPLES_DIR
    ids = ids if ids is not None else config.list_example_ids()
    skip = set() if include_holdout else holdout_ids()
    catalog = load_catalog()["steps"]
    acc: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "examples": set(), "category": "unknown"})
    manual: set[str] = set()
    for i in ids:
        if i in skip:
            continue
        manual |= {it["jenkins"] for it in _load(root / i / "gha" / "conversion.json").get("items", [])
                   if it.get("status") == "manual"}
        a = _load(root / i / "analysis" / "analysis.json")
        for name, s in (a.get("steps") or {}).items():
            if s.get("category") in UNMAPPED:
                row = acc[name]
                row["count"] += s.get("count", 0)
                row["examples"].add(i)
                row["category"] = s["category"]
        for s in a.get("unknown_steps") or []:
            if s["name"] in (a.get("steps") or {}):
                continue  # `steps` already lists every unknown step: counting both would use it twice
            row = acc[s["name"]]
            row["count"] += s.get("count", 1)
            row["examples"].add(i)
    out = []
    for name, row in acc.items():
        if not _STEP_NAME.fullmatch(name) or (unmapped_only and name in catalog and name not in manual):
            continue
        weight = (catalog.get(name) or {}).get("weight", 1)
        out.append({"step": name, "category": row["category"], "count": row["count"], "weight": weight,
                    "cost": round(row["count"] * weight, 1), "examples": sorted(row["examples"]),
                    "in_catalog": name in catalog})
    return sorted(out, key=lambda r: (-r["cost"], r["step"]))


def format_gaps(rows: list[dict], limit: int = 20) -> str:
    if not rows:
        return "no matching steps in the (non-holdout) corpus"
    lines = [f"{'step':<28}{'category':<10}{'uses':>5}{'weight':>8}{'cost':>7}  examples"]
    for r in rows[:limit]:
        ex = ",".join(r["examples"][:6]) + (",..." if len(r["examples"]) > 6 else "")
        lines.append(f"{r['step']:<28}{r['category']:<10}{r['count']:>5}{r['weight']:>8}{r['cost']:>7}  {ex}")
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} more (use --limit)")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------------ scoreboard


def _verdict(d: Path, tier: str, jenkins: dict) -> str:
    from .runners.execute import stale_reason

    r = _load(d / "runs" / f"{tier}-trace" / "result.json")
    if not r.get("comparison"):
        return "none"
    if stale_reason(d, r, tier) or stale_reason(d, jenkins, "jenkins"):
        return "stale"
    c = r["comparison"]
    return "equivalent" if c.get("equivalent") else ("inconclusive" if c.get("verdict") == "inconclusive" else "differs")


def scoreboard(ids: list[str] | None = None, examples_dir: Path | None = None) -> dict[str, Any]:
    root = examples_dir or config.EXAMPLES_DIR
    ids = ids if ids is not None else config.list_example_ids()
    hold = holdout_ids()
    rows = {}
    for i in ids:
        d = root / i
        a, conv, val = _load(d / "analysis" / "analysis.json"), _load(d / "gha" / "conversion.json"), \
            _load(d / "gha" / "validation.json")
        jen = _load(d / "runs" / "jenkins-trace" / "result.json")
        rows[i] = {
            "holdout": i in hold,
            "difficulty": (a.get("complexity") or {}).get("score"),
            "weighted_mapped_pct": (a.get("coverage") or {}).get("weighted_mapped_pct"),
            "unknown_steps": len(a.get("unknown_steps") or []),
            "automation_pct": conv.get("automation_pct"),
            "manual_items": (conv.get("counts") or {}).get("manual"),
            "static_ok": val.get("ok"),
            "security_ok": val.get("security_ok"),
            "verdicts": {t: _verdict(d, t, jen) for t in ("act", "selfhosted", "hosted")},
        }
    return {"version": 1, "examples": rows}


def compare(base: dict[str, Any], now: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """(regressions, improvements, unmeasured) of `now` against `base`, per example present in both.

    A verdict that is now `stale` or `none` was not re-measured (the tier was not run again): it is reported as
    unmeasured, never as a pass and, unlike a changed verdict, not as a regression. `--strict` fails on it.
    """
    reg, imp, unmeasured = [], [], []

    def num(i: str, key: str, b: Any, n: Any, higher_is_better: bool) -> None:
        if b is None or n is None or b == n:
            return
        better = (n > b) == higher_is_better
        (imp if better else reg).append(f"{i}: {key} {b} -> {n}")

    for i, b in base.get("examples", {}).items():
        n = now.get("examples", {}).get(i)
        if n is None:
            reg.append(f"{i}: missing from the current scoreboard")
            continue
        num(i, "weighted_mapped_pct", b.get("weighted_mapped_pct"), n.get("weighted_mapped_pct"), True)
        num(i, "automation_pct", b.get("automation_pct"), n.get("automation_pct"), True)
        num(i, "unknown_steps", b.get("unknown_steps"), n.get("unknown_steps"), False)
        num(i, "manual_items", b.get("manual_items"), n.get("manual_items"), False)
        for key in ("static_ok", "security_ok"):
            if b.get(key) is True and n.get(key) is not True:
                reg.append(f"{i}: {key} true -> {n.get(key)}")
            elif b.get(key) is not True and n.get(key) is True:
                imp.append(f"{i}: {key} -> true")
        for tier, bv in (b.get("verdicts") or {}).items():
            nv = (n.get("verdicts") or {}).get(tier, "none")
            if bv == nv:
                continue
            # an equivalent run that is now anything else is a regression; stale/none means "not measured", so
            # it is not an improvement but is reported so a missing re-run is not mistaken for a pass
            if nv in ("stale", "none"):
                if bv == "equivalent":
                    unmeasured.append(f"{i}: {tier} verdict equivalent -> {nv} (re-run the {tier} tier to measure)")
            elif bv == "equivalent":
                reg.append(f"{i}: {tier} verdict equivalent -> {nv}")
            elif nv == "equivalent":
                imp.append(f"{i}: {tier} verdict {bv} -> equivalent")
            elif bv == "inconclusive" and nv == "differs":
                reg.append(f"{i}: {tier} verdict inconclusive -> differs")
    return reg, imp, unmeasured


def format_scoreboard(sb: dict[str, Any]) -> str:
    lines = [f"{'id':<5}{'hold':<6}{'diff':>5}{'wmap%':>7}{'auto%':>7}{'unk':>5}{'man':>5}  {'static':<7}verdicts"]
    for i, r in sb["examples"].items():
        static = {True: "ok", False: "FAIL", None: "-"}[r["static_ok"]]
        v = " ".join(f"{t}={x}" for t, x in r["verdicts"].items() if x != "none") or "-"
        lines.append(f"{i:<5}{'yes' if r['holdout'] else '':<6}{r['difficulty'] if r['difficulty'] is not None else '-':>5}"
                     f"{r['weighted_mapped_pct'] if r['weighted_mapped_pct'] is not None else '-':>7}"
                     f"{r['automation_pct'] if r['automation_pct'] is not None else '-':>7}{r['unknown_steps']:>5}"
                     f"{r['manual_items'] if r['manual_items'] is not None else '-':>5}  {static:<7}{v}")
    return "\n".join(lines)


def baseline_path() -> Path:
    return _root() / EVALS / "baseline.json"


# ---------------------------------------------------------------------------------------------------------- guard


def _patterns() -> tuple[list[str], list[str], dict[str, set[str]]]:
    """([protected], [review], {path: names}) from evals/protected.txt; `[lists]` lines read `path: NAME, NAME`."""
    section, out, lists = "", {"protected": [], "review": []}, {}
    p = _root() / EVALS / "protected.txt"
    for ln in (p.read_text().splitlines() if p.exists() else []):
        ln = ln.split("#")[0].strip()
        if ln.startswith("[") and ln.endswith("]"):
            section = ln[1:-1]
        elif ln and section == "lists" and ":" in ln:
            path, names = ln.split(":", 1)
            lists[path.strip()] = {n.strip() for n in names.split(",") if n.strip()}
        elif ln and section in out:
            out[section].append(ln)
    return out["protected"], out["review"], lists


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=_root(), capture_output=True, text=True, check=True).stdout


def changed_files(base: str) -> list[str]:
    """Files changed against `base` (merge-base diff, committed or not), plus untracked files."""
    names = set(_git("diff", "--name-only", base).split())
    names |= set(_git("ls-files", "--others", "--exclude-standard").split())
    return sorted(names)


def removed_test_lines(base: str) -> list[str]:
    """Tests may be added to but not weakened: any deleted or altered line under tests/ is reported."""
    out = []
    for ln in _git("diff", "--numstat", base, "--", "tests").splitlines():
        added, deleted, path = ln.split("\t", 2)
        if deleted not in ("0", "-") and not path.startswith("tests/fixtures/"):
            out.append(f"{path} ({deleted} line(s) removed or changed)")
    return out


CATALOG = "j2gha/rules/steps.yaml"
CATALOG_KEYS = ("category", "weight")


def catalog_changes(base: str) -> list[str]:
    """Existing catalog entries may gain entries but not be recategorised, re-weighted or removed.

    The catalog is editable on purpose (a new rule is a new entry), so the cheapest way to raise coverage would be
    to move a step to `noop`/`direct` or lower its weight. Those are human decisions.
    """
    import yaml

    def steps(text: str) -> dict | None:
        doc = yaml.safe_load(text)
        return doc.get("steps") if isinstance(doc, dict) and isinstance(doc.get("steps"), dict) else None

    try:
        old = steps(_git("show", f"{base}:{CATALOG}"))
    except subprocess.CalledProcessError:
        return []  # no catalog at base
    if old is None:
        return []
    new = steps((_root() / CATALOG).read_text())
    if new is None:
        return ["catalog is no longer a mapping with a `steps:` section"]
    out = []
    for name, entry in old.items():
        if name not in new:
            out.append(f"catalog entry '{name}' removed")
            continue
        for key in CATALOG_KEYS:
            if entry.get(key) != new[name].get(key):
                out.append(f"catalog entry '{name}': {key} {entry.get(key)} -> {new[name].get(key)}")
    return out


def _without_assignments(source: str, names: set[str]) -> str:
    """The module's AST with the top-level assignments to `names` removed (formatting and comments do not matter)."""
    import ast

    tree = ast.parse(source)
    tree.body = [n for n in tree.body if not (isinstance(n, (ast.Assign, ast.AnnAssign)) and any(
        isinstance(t, ast.Name) and t.id in names for t in (n.targets if isinstance(n, ast.Assign) else [n.target])))]
    return ast.dump(tree)


def list_edit_violations(base: str, path: str, names: set[str]) -> list[str]:
    """Files that mix the lists a new step must join with the logic that judges results: only the named
    assignments (e.g. TRACED_STEPS) may change; any other change to the module is a violation."""
    try:
        old = _git("show", f"{base}:{path}")
    except subprocess.CalledProcessError:
        return []
    try:
        same = _without_assignments(old, names) == _without_assignments((_root() / path).read_text(), names)
    except SyntaxError:
        return [f"{path} no longer parses"]
    return [] if same else [f"{path} changed outside {', '.join(sorted(names))}"]


def guard(base: str = "HEAD") -> tuple[list[str], list[str]]:
    """(violations, review notes) for the changes against `base`."""
    protected, review, lists = _patterns()
    files = changed_files(base)
    bad = [f"{f} matches protected pattern '{pat}'" for f in files for pat in protected if fnmatch.fnmatch(f, pat)]
    bad += [f"tests weakened: {t}" for t in removed_test_lines(base)]
    for path, names in lists.items():
        if path in files:
            bad += list_edit_violations(base, path, names)
    if CATALOG in files:
        bad += [f"existing {c}" for c in catalog_changes(base)]
    notes = [f"{f}: review the diff by hand (matches '{pat}')" for f in files for pat in review
             if fnmatch.fnmatch(f, pat)]
    return sorted(set(bad)), sorted(set(notes))
