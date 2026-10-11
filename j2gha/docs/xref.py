"""Jenkins -> GitHub Actions documentation crosswalk.

Joins three things per Jenkins construct: the step catalog's conversion decision (rules/steps.yaml), where to read on
the Jenkins side (local bundle page, else jenkins.io) and where to read on the GHA side (local bundle page, else
docs.github.com) from rules/docs-xref.yaml. Works with no bundles downloaded (everything resolves to URLs).

GHA links keep the *requested* product version (``--gha-version`` / ``J2GHA_DOCS_GHA`` / the selected default) even
when its bundle is not downloaded: they point at that version on docs.github.com, and a page missing from a downloaded
bundle that covers its section is reported as not in that version's docs, not swapped for the GitHub.com page.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import yaml

from . import store
from .gha import SITE, url_prefix, version_id
from .store import covered

RULES = Path(__file__).resolve().parent.parent / "rules"
GHA_SITE = "https://docs.github.com/en/actions/"
JENKINS_SYNTAX = "https://www.jenkins.io/doc/book/pipeline/syntax/"


@lru_cache(maxsize=1)
def table() -> dict[str, dict]:
    return yaml.safe_load((RULES / "docs-xref.yaml").read_text())["xref"]


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict]:
    return yaml.safe_load((RULES / "steps.yaml").read_text()).get("steps", {})


def _title(path: Path, fallback: str) -> str:
    try:
        with path.open(encoding="utf-8") as fh:
            first = fh.readline()
        return first.lstrip("# ").strip() or fallback
    except OSError:
        return fallback


def _plugin_page(bundle: Path, step: str) -> Path | None:
    index = bundle / "plugins" / "INDEX.md"
    if not index.is_file():
        return None
    needle = f"`{step}`"
    for line in index.read_text(encoding="utf-8").splitlines():
        if needle in line and "](" in line:
            return bundle / "plugins" / line.split("](", 1)[1].split(")", 1)[0]
    return None


def jenkins_refs(term: str, entry: dict, bundle: Path | None) -> list[tuple[str, str]]:
    """[(label, target)] where target is an absolute local path (with #anchor) or a URL."""
    refs = []
    for page in entry.get("jenkins", []):
        rel, _, anchor = page.partition("#")
        if bundle and (bundle / rel).is_file():
            refs.append((_title(bundle / rel, rel) + (f" #{anchor}" if anchor else ""),
                         str(bundle / rel) + (f"#{anchor}" if anchor else "")))
        elif rel.startswith("handbook/"):
            url = "https://www.jenkins.io/doc/book/" + rel.removeprefix("handbook/").removesuffix(".md") + "/"
            refs.append((rel + (f" #{anchor}" if anchor else ""), url + (f"#{anchor}" if anchor else "")))
    if bundle:  # an options/triggers/parameters/when/agent symbol documented by its plugin
        for page in sorted((bundle / "declarative").glob(f"*/{term}.md")):
            exact = "installed in the harness controller" in page.read_text(encoding="utf-8")[:2000]
            refs.append((f"{page.parent.name} `{term}` ({'installed version' if exact else 'latest plugin release'})",
                         str(page)))
    if entry.get("kind", "step") == "step" or not refs:
        local = bundle / "steps" / f"{term}.md" if bundle else None
        if local and local.is_file():
            refs.insert(0, (f"step `{term}` (installed plugin version)", str(local)))
        elif bundle and (p := _plugin_page(bundle, term)):
            refs.insert(0, (f"step `{term}` in {p.stem} (latest plugin release)", str(p)))
        elif term in catalog():
            refs.insert(0, (f"step `{term}`", "https://www.jenkins.io/doc/pipeline/steps/"))
    return refs


def gha_refs(entry: dict, bundle: Path | None, version: str | None = None) -> list[tuple[str, str]]:
    """[(label, target)] for ``version``'s pages: the local bundle's page, else that version on docs.github.com."""
    meta = json.loads((bundle / "manifest.json").read_text()) if bundle else {}
    vid = meta.get("components", {}).get("docs.github.com") or version_id(version or "fpt")
    fetched = store.families(meta)  # sections the bundle downloaded: a page missing there is missing in the version
    listed = None
    if bundle and (bundle / "pagelist.json").is_file():
        prefix = url_prefix(vid or "free-pro-team@latest") + "/"
        listed = {p.removeprefix(prefix) for p in json.loads((bundle / "pagelist.json").read_text())}
    refs = []
    for page in entry.get("gha", []):
        rel, _, anchor = page.partition("#")
        local = bundle / "actions" / f"{rel}.md" if bundle else None
        suffix = f"#{anchor}" if anchor else ""
        name = rel + (f" #{anchor}" if anchor else "")
        if local and local.is_file():
            refs.append((_title(local, rel) + (f" #{anchor}" if anchor else ""), str(local) + suffix))
        elif bundle and covered(f"actions/{rel}", fetched) and (listed is None or f"actions/{rel}" not in listed):
            refs.append((f"{name} - not in the {bundle.name} docs (GitHub.com page)", GHA_SITE + rel + suffix))
        elif vid:
            refs.append((name, f"{SITE}{url_prefix(vid)}/actions/{rel}{suffix}"))
        else:
            refs.append((f"{name} (GitHub.com; {version} is not a docs.github.com version)", GHA_SITE + rel + suffix))
    return refs


def _short(label: str) -> str:
    """``handbook/pipeline/syntax.md #stage`` -> ``syntax #stage``: page name and anchor, for compact links."""
    page, sep, anchor = label.partition(" #")
    return page.rsplit("/", 1)[-1].removesuffix(".md") + sep + anchor


def web_refs(term: str) -> dict | None:
    """``term``'s crosswalk entry as GitHub.com and jenkins.io links, or None when it has none.

    Never reads a local bundle, the selected version or ``J2GHA_DOCS_*``, so output built from it (the migration
    report) is the same on every machine; `j2gha docs xref <term>` resolves the same pages locally.
    """
    key, entry = _entry(term)
    if key not in table():
        return None
    return {"key": key, "note": entry.get("note", ""),
            "jenkins": [(_short(label), url) for label, url in jenkins_refs(key, entry, None)],
            "gha": [(_short(label), url) for label, url in gha_refs(entry, None, "fpt")]}


def _entry(term: str) -> tuple[str, dict]:
    t = table()
    for key in t:
        if key.lower() == term.lower():
            return key, t[key]
    for key in catalog():
        if key.lower() == term.lower():
            return key, {"kind": "step"}
    return term, {"kind": "step"}


def _block(term: str, rel_to: Path | None) -> list[str]:
    key, entry = _entry(term)
    jb, gb = store.bundle_path("jenkins"), store.bundle_path("gha")

    def fmt(label: str, target: str) -> str:
        if rel_to is not None and not target.startswith("http"):
            target = os.path.relpath(target.split("#")[0], rel_to) + ("#" + target.split("#", 1)[1]
                                                                       if "#" in target else "")
        return f"[{label}]({target})"

    out = [f"### `{key}` ({entry.get('kind', 'step')})", ""]
    if key not in table() and key not in catalog():
        found = jenkins_refs(key, entry, jb)
        out.append(f"- Not in the crosswalk or the step catalog. Search the bundles: `rg -n '{key}' "
                   f"{store.docs_dir()}`" + (" · Jenkins: " + " · ".join(fmt(*r) for r in found) if found else ""))
        return out + [""]
    cat = catalog().get(key)
    if cat:
        out.append(f"- Catalog: **{cat['category']}** -> {cat.get('gha', '')}")
    if entry.get("note"):
        out.append(f"- Note: {entry['note']}")
    out.append("- Jenkins: " + " · ".join(fmt(*r) for r in jenkins_refs(key, entry, jb)))
    g = gha_refs(entry, gb, store.requested("gha"))
    if g:
        out.append("- GitHub Actions: " + " · ".join(fmt(*r) for r in g))
    out.append("")
    return out


def lookup(terms: list[str]) -> str:
    return "\n".join(line for t in terms for line in _block(t, None))


def write_xref() -> Path:
    root = store.docs_dir()
    root.mkdir(parents=True, exist_ok=True)
    jb, gb = store.bundle_path("jenkins"), store.bundle_path("gha")
    jv, gv = store.requested("jenkins"), store.requested("gha") or "fpt"
    vid = version_id(gv)
    jdocs = jb.name if jb else f"{jv or ''} not downloaded (jenkins.io links)".lstrip()
    gdocs = gb.name if gb else f"{gv} not downloaded ({SITE + url_prefix(vid) if vid else 'GitHub.com'} links)"
    lines = ["# Jenkins -> GitHub Actions cross-reference", "",
             f"> Jenkins docs: {jdocs} · GitHub Actions docs: {gdocs}. Generated by `j2gha docs xref` from "
             "j2gha/rules/docs-xref.yaml + steps.yaml; links are relative to this file.", ""]
    groups = {"directive": "Declarative directives and options", "step": "Steps", "global": "Global variables",
              "concept": "Concepts"}
    for kind, heading in groups.items():
        lines += [f"## {heading}", ""]
        for key, entry in table().items():
            if entry.get("kind", "step") == kind:
                lines += _block(key, root)
    path = root / "xref.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    store.write_root_index()
    return path
