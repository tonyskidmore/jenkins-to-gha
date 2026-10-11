"""Where local documentation bundles live and how they are indexed.

Layout (``$J2GHA_DOCS_DIR``, default ``<repo>/.docs``, gitignored)::

    INDEX.md                          bundles present + which version each source uses by default
    selected.json                     {"jenkins": "<version>", "gha": "<version>"} (j2gha docs use)
    <source>/<version>/INDEX.md       llms.txt-style index: H1, summary, H2 sections of "- [title](path): blurb"
    <source>/<version>/manifest.json  provenance: origin URLs, licence, fetched_at, component versions, page count and
                                      the families (``parts``) present with when each was fetched
    <source>/<version>/pages.json     every page with its family, so a partial refresh can keep the other families
    <source>/<version>/**.md          one Markdown page per document, first lines = title + source URL

Sources: ``jenkins`` (step/global reference from the harness controller + the jenkins.io handbook) and ``gha``
(docs.github.com rendered Markdown for one GitHub product version).

A fetch builds into a staging directory beside the bundle (``<source>/.<version>.staging-<pid>``) and swaps it in only
once it is complete, so a failed fetch leaves the previous bundle, the selection and the root index as they were. A
partial fetch (``--parts``) seeds the staging directory with the bundle's other families. Version labels become
directory names, so every label read from the CLI, ``J2GHA_DOCS_<SOURCE>`` or selected.json is validated (``LABEL``).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import ROOT

SOURCES = ("jenkins", "gha")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")  # one path component; never "." / ".." / absolute


def docs_dir() -> Path:
    env = os.environ.get("J2GHA_DOCS_DIR")
    return Path(env).expanduser().resolve() if env else ROOT / ".docs"


def version_label(source: str, version: str, where: str = "") -> str:
    """Validate a bundle label (GHA aliases such as ``enterprise-server@3.19`` normalised to ``ghes-3.19``)."""
    if source not in SOURCES:
        raise SystemExit(f"unknown docs source {source!r} (expected one of: {', '.join(SOURCES)})")
    if source == "gha":
        from .gha import label_of

        version = label_of(version)
    if not LABEL.fullmatch(version):
        raise SystemExit(f"invalid {source} docs version {version!r}{where}: a label is 1-64 letters, digits or "
                         "'._+-', starting with a letter or digit (no path separators, no '..')")
    return version


def covered(name: str, by: Iterable[str]) -> bool:
    """``name`` (a family or page path) is one of ``by`` or nested in one: ``actions/reference`` is in ``actions``."""
    return any(name == b or name.startswith(f"{b}/") for b in by)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _remove(source: str, path: Path) -> None:
    """rmtree a bundle, staging or backup directory: refuses anything not strictly inside <docs>/<source>/."""
    base = (docs_dir() / source).resolve()
    real = path.resolve()
    if path.is_symlink() or real == base or not real.is_relative_to(base):
        raise RuntimeError(f"refusing to delete {path}: not a bundle directory inside {base}")
    shutil.rmtree(real)


@dataclass
class Page:
    path: str  # relative to the bundle, e.g. "steps/sh.md"
    title: str
    section: str
    blurb: str = ""
    index: str = "INDEX.md"  # large families get their own sub-index so the top INDEX.md stays cheap to read
    part: str = ""  # the family (fetch part / docs section) that wrote it; "" index = listed by a family index page


@dataclass
class Bundle:
    source: str
    version: str
    title: str
    summary: str
    origin: dict[str, str] = field(default_factory=dict)
    licence: str = ""
    components: dict[str, str] = field(default_factory=dict)
    pages: list[Page] = field(default_factory=list)
    parts: dict[str, str] = field(default_factory=dict)  # family -> fetched_at
    part: str = ""  # family being written, stamped on each page
    staging: Path | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.version = version_label(self.source, self.version)

    @property
    def home(self) -> Path:
        return docs_dir() / self.source / self.version

    @property
    def path(self) -> Path:
        """Where pages go: the staging directory while a build is in progress, else the bundle itself."""
        return self.staging or self.home

    def write(self, rel: str, title: str, body: str, source_url: str, section: str, blurb: str = "",
              index: str = "INDEX.md") -> None:
        """Write one page. The header line keeps provenance next to the content for citation."""
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        body = body.strip()
        if body.split("\n", 1)[0].lstrip("# ").strip() == title:  # drop a duplicated H1
            body = body.split("\n", 1)[1].strip() if "\n" in body else ""
        header = f"# {title}\n\n> Source: {source_url} ({self.source} {self.version})\n\n"
        target.write_text(header + body + "\n", encoding="utf-8")
        self.pages.append(Page(rel, title, section, blurb, index, self.part))

    def reset(self, refresh: Iterable[str] | None = None, key: Callable[[Page], str] = lambda p: p.part) -> None:
        """Start a build in an empty staging directory; the bundle itself is only replaced by finish().

        ``refresh`` names the families this build fetches. The current bundle's other families - their pages
        (``key(page)`` not within ``refresh``), provenance and fetch times - are carried over, so a partial fetch
        doesn't drop them."""
        self.discard()
        refresh = None if refresh is None else tuple(refresh)
        old = manifest(self.source, self.version) if refresh is not None else None
        kept = {n: t for n, t in families(old).items() if not covered(n, refresh)}
        listed = self.home / "pages.json"
        if kept and not listed.is_file():
            raise SystemExit(f"{self.source} {self.version} predates partial refresh (no pages.json), so fetching "
                             f"only {', '.join(refresh)} would drop {', '.join(kept)}: fetch it whole once"
                             + (" or into another bundle (--label)" if self.source == "jenkins" else ""))
        stage = docs_dir() / self.source / f".{self.version}.staging-{os.getpid()}"
        if stage.exists():
            _remove(self.source, stage)
        stage.mkdir(parents=True)
        self.staging, self.pages = stage, []
        self.parts = {**kept, **{r: _now() for r in refresh or ()}}
        if not (old and listed.is_file()):
            return
        for page in (Page(**p) for p in json.loads(listed.read_text(encoding="utf-8"))):
            if covered(key(page), refresh) or not (self.home / page.path).is_file():
                continue
            (stage / page.path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.home / page.path, stage / page.path)
            self.pages.append(page)
        if self.pages:
            self.origin = {**old.get("origin", {}), **self.origin}
            self.components = {**old.get("components", {}), **self.components}

    def discard(self) -> None:
        """Delete the staging directory of a failed build; the bundle itself is untouched."""
        if self.staging is not None and self.staging.exists():
            _remove(self.source, self.staging)
        self.staging = None

    @contextmanager
    def staged(self, refresh: Iterable[str] | None = None, key: Callable[[Page], str] = lambda p: p.part):
        """reset(); if anything fails before finish() swapped the build in, only the staging directory goes."""
        try:
            self.reset(refresh, key)
            yield self
        except BaseException:
            self.discard()
            raise

    def finish(self, sections: list[str] | None = None, default: bool = False) -> Path:
        """Write INDEX.md, manifest.json and pages.json, swap the build in for the bundle, then make it the default
        version if ``default`` or none is selected, and rewrite the root index."""
        if self.staging is None:
            raise RuntimeError("Bundle.finish() without reset()")
        self.pages = list({p.path: p for p in self.pages}.values())  # a page written again replaces its record
        indexed = [p for p in self.pages if p.index]
        if not indexed:
            raise SystemExit(f"{self.source} {self.version}: nothing was fetched; the previous bundle is unchanged")
        order = sections or list(dict.fromkeys(p.section for p in indexed))
        subs = sorted({p.index for p in indexed} - {"INDEX.md"})
        for index in ["INDEX.md", *subs]:
            base = Path(index).parent
            if index == "INDEX.md":
                lines = [f"# {self.title}", "", f"> {self.summary}", ""]
            else:
                lines = [f"# {self.title}: {base}", "", "> Sub-index of [../INDEX.md](../INDEX.md).", ""]
            mine = [p for p in indexed if p.index == index]
            for section in order + sorted({p.section for p in mine} - set(order)):
                pages = [p for p in mine if p.section == section]
                if not pages:
                    continue
                lines += [f"## {section}", ""]
                lines += [f"- [{p.title}]({Path(p.path).relative_to(base)})" + (f": {p.blurb}" if p.blurb else "")
                          for p in pages]
                lines.append("")
            if index == "INDEX.md" and subs:
                lines += ["## Sub-indexes", ""]
                for sub in subs:
                    n = sum(1 for p in indexed if p.index == sub)
                    lines.append(f"- [{sub}]({sub}): {n} pages - " + "; ".join(
                        dict.fromkeys(p.section for p in indexed if p.index == sub)))
                lines.append("")
            (self.path / index).write_text("\n".join(lines), encoding="utf-8")
        meta = {
            "source": self.source, "version": self.version, "title": self.title, "origin": self.origin,
            "licence": self.licence, "components": self.components, "pages": len(indexed),
            "bytes": sum(f.stat().st_size for f in self.path.rglob("*.md")),
            "files": sum(1 for _ in self.path.rglob("*.md")),
            "fetched_at": _now(), "parts": self.parts,
        }
        (self.path / "pages.json").write_text("[\n" + ",\n".join(json.dumps(asdict(p)) for p in self.pages)
                                              + "\n]\n", encoding="utf-8")
        (self.path / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        self._swap()
        if default or not selected().get(self.source):
            select(self.source, self.version)
        else:
            write_root_index()
        return self.path

    def _swap(self) -> None:
        """bundle -> backup, staging -> bundle (the old bundle comes back if that fails), then drop the backup."""
        stage, home = self.staging, self.home
        if stage is None or not (stage / "manifest.json").is_file():
            raise RuntimeError(f"incomplete {self.source} {self.version} build in {stage}")
        backup = home.with_name(f".{self.version}.old-{os.getpid()}")
        if backup.exists():
            _remove(self.source, backup)
        if home.exists():
            os.replace(home, backup)
        try:
            os.replace(stage, home)
        except BaseException:
            if backup.exists() and not home.exists():
                os.replace(backup, home)
            raise
        self.staging = None
        if backup.exists():
            _remove(self.source, backup)


def manifest(source: str, version: str) -> dict | None:
    f = docs_dir() / source / version_label(source, version) / "manifest.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def families(meta: dict | None) -> dict[str, str]:
    """Families (``parts``) in a manifest; for bundles fetched before they were recorded, inferred from it."""
    if not meta:
        return {}
    if "parts" in meta:
        return meta["parts"]
    names = (meta.get("components", {}).get("sections", "").split(",") if meta.get("source") == "gha"
             else list(meta.get("origin", {})))
    return {n: meta.get("fetched_at", "") for n in names if n}


def bundles() -> list[dict]:
    out = []
    for source in SOURCES:
        base = docs_dir() / source
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            m = d / "manifest.json"
            if LABEL.fullmatch(d.name) and m.is_file():  # skips .<version>.staging-* / .old-* directories
                out.append({**json.loads(m.read_text()), "path": str(d)})
    return out


def selected() -> dict[str, str]:
    f = docs_dir() / "selected.json"
    return json.loads(f.read_text()) if f.is_file() else {}


def select(source: str, version: str) -> str:
    version = version_label(source, version)
    if not (docs_dir() / source / version / "manifest.json").is_file():
        raise SystemExit(f"no {source} docs for version {version!r}; fetch them first (j2gha docs fetch {source})")
    sel = {**selected(), source: version}
    docs_dir().mkdir(parents=True, exist_ok=True)
    (docs_dir() / "selected.json").write_text(json.dumps(sel, indent=2) + "\n")
    write_root_index()
    return version


def requested(source: str, version: str | None = None) -> str | None:
    """The version asked for: explicit, else $J2GHA_DOCS_<SOURCE>, else the selected one. Validated, but not
    necessarily downloaded (bundle_path() answers that)."""
    env = f"J2GHA_DOCS_{source.upper()}"
    for value, where in ((version, ""), (os.environ.get(env), f" (from ${env})"),
                         (selected().get(source), f" (from {docs_dir() / 'selected.json'})")):
        if value:
            return version_label(source, value, where)
    return None


def bundle_path(source: str, version: str | None = None) -> Path | None:
    """The bundle to use for ``source``: explicit version, else $J2GHA_DOCS_<SOURCE>, else the selected one."""
    version = requested(source, version)
    if not version:
        return None
    p = docs_dir() / source / version
    return p if (p / "manifest.json").is_file() else None


def write_root_index() -> None:
    sel = selected()
    lines = ["# Local reference documentation (j2gha)", "",
             "> Generated by `j2gha docs fetch`; not committed. Grep this directory, read a bundle's INDEX.md first, "
             "and cite the `> Source:` URL at the top of each page.", "",
             "| source | version | default | pages | fetched | index |", "|---|---|---|---|---|---|"]
    for b in bundles():
        default = "yes" if sel.get(b["source"]) == b["version"] else ""
        lines.append(f"| {b['source']} | {b['version']} | {default} | {b['pages']} | {b['fetched_at'][:10]} "
                     f"| [{b['source']}/{b['version']}/INDEX.md]({b['source']}/{b['version']}/INDEX.md) |")
    xref = docs_dir() / "xref.md"
    if xref.is_file():
        lines += ["", "Cross-reference (Jenkins construct -> GitHub Actions pages): [xref.md](xref.md)"]
    (docs_dir() / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
