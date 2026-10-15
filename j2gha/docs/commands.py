"""``j2gha docs`` sub-commands: fetch, status, use, path, xref."""

from __future__ import annotations

import argparse
import sys

from . import store


def add_parser(sub) -> None:
    d = sub.add_parser("docs", help="local Jenkins / GitHub Actions reference docs for agents (not committed)")
    ds = d.add_subparsers(dest="action", required=True)

    f = ds.add_parser("fetch", help="download docs into $J2GHA_DOCS_DIR (default .docs/) as Markdown")
    f.add_argument("source", choices=["jenkins", "gha", "all"], nargs="?", default="all")
    f.add_argument("--version", default=None,
                   help="gha: fpt (GitHub.com, default), ghec, ghes-X.Y (or enterprise-server@X.Y); "
                        "jenkins: the core version you expect - refused unless the running controller has it")
    f.add_argument("--label", default=None,
                   help="jenkins: bundle name (default: <core>+p<plugin-set digest>, or 'latest' without the "
                        "controller part); name an existing bundle to refresh only some --parts of it")
    f.add_argument("--ref", default="master", help="jenkins: jenkins.io commit/branch for the handbook")
    f.add_argument("--parts", default=None,
                   help="jenkins: comma list of controller,handbook,declarative,plugins (default: all); "
                        "gha: comma list of docs.github.com sections (default: actions). Onto an existing bundle "
                        "only these are replaced; its other parts/sections are kept")
    f.add_argument("--delay", type=float, default=None, help="gha: seconds between page requests")

    ds.add_parser("status", help="list downloaded bundles and the default version per source")

    u = ds.add_parser("use", help="make a downloaded version the default for its source")
    u.add_argument("source", choices=store.SOURCES)
    u.add_argument("version")

    p = ds.add_parser("path", help="print the bundle directory for a source (exit 1 if not downloaded)")
    p.add_argument("source", choices=[*store.SOURCES, "root"], nargs="?", default="root")
    p.add_argument("--version", default=None, help="bundle label (default: $J2GHA_DOCS_<SOURCE>, else the default)")

    x = ds.add_parser("xref", help="Jenkins construct -> local Jenkins + GitHub Actions doc pages")
    x.add_argument("terms", nargs="*", help="step/directive names (e.g. stash input when); none = whole table")
    x.add_argument("--write", action="store_true", help="(re)write <docs>/xref.md for the selected bundles")
    x.add_argument("--gha-version", default=None,
                   help="resolve GHA pages in this version's bundle, else link that version on docs.github.com "
                        "(e.g. ghes-3.18)")
    x.add_argument("--jenkins-version", default=None, help="resolve Jenkins pages in this bundle")

    d.set_defaults(func=run)


def run(a: argparse.Namespace) -> int:
    if a.action == "fetch":
        from ..config import offline

        if offline():
            raise SystemExit("j2gha docs fetch: J2GHA_OFFLINE is set (fetching downloads from jenkins.io and "
                             "docs.github.com); the bundles already in place still serve the skills")
        if a.label and a.source != "jenkins":
            raise SystemExit("--label applies to `j2gha docs fetch jenkins` only")
        sources = ["jenkins", "gha"] if a.source == "all" else [a.source]
        for source in sources:
            if source == "jenkins":
                from . import jenkins

                parts = tuple(a.parts.split(",")) if a.parts and a.source == "jenkins" else jenkins.PARTS
                b = jenkins.fetch(parts, ref=a.ref, version=a.version if a.source == "jenkins" else None,
                                  label=a.label)
            else:
                from . import gha

                sections = tuple(a.parts.split(",")) if a.parts and a.source == "gha" else gha.SECTIONS
                b = gha.fetch(a.version if a.source == "gha" else None, sections=sections, delay=a.delay)
            default = " (default)" if store.selected().get(b.source) == b.version else ""
            print(f"{b.source} {b.version}{default}: {sum(1 for p in b.pages if p.index)} indexed pages, parts "
                  f"{', '.join(b.parts)} -> {b.path}")
        from .xref import write_xref

        write_xref()
        return 0
    if a.action == "status":
        print(f"docs dir: {store.docs_dir()}")
        sel = store.selected()
        rows = store.bundles()
        if not rows:
            print("no bundles - run: uv run j2gha docs fetch [jenkins|gha]")
            return 0
        for b in rows:
            mark = "*" if sel.get(b["source"]) == b["version"] else " "
            print(f"{mark} {b['source']:<8} {b['version']:<22} {b['files']:>5} files {b['bytes'] / 1e6:6.1f} MB  "
                  f"fetched {b['fetched_at'][:16]}")
        return 0
    if a.action == "use":
        version = store.select(a.source, a.version)
        from .xref import write_xref

        write_xref()
        print(f"default {a.source} docs: {version}")
        return 0
    if a.action == "path":
        if a.source == "root":
            print(store.docs_dir())
            return 0 if (store.docs_dir() / "INDEX.md").is_file() else 1
        p = store.bundle_path(a.source, a.version)
        if p is None:
            v = store.requested(a.source, a.version)
            print(f"no local {a.source} docs" + (f" for {v}" if v else "") + f" (uv run j2gha docs fetch {a.source}"
                  + (f" --version {v})" if v and a.source == "gha" else ")"), file=sys.stderr)
            return 1
        print(p)
        return 0
    if a.action == "xref":
        from .xref import lookup, write_xref

        import os

        for source, version in (("gha", a.gha_version), ("jenkins", a.jenkins_version)):
            if version:  # store.bundle_path honours J2GHA_DOCS_<SOURCE>
                os.environ[f"J2GHA_DOCS_{source.upper()}"] = store.version_label(source, version)

        if a.write or not a.terms:
            path = write_xref()
            if not a.terms:
                print(path.read_text() if path else "no bundles downloaded")
                return 0
        print(lookup(a.terms))
        return 0
    return 2
