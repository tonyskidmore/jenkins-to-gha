"""GitHub Actions documentation fetcher (``.docs/gha/<version>/``).

Source of truth: docs.github.com (content from github/docs, CC-BY-4.0). The repository Markdown is unusable as-is
(Liquid ``{% data reusables %}`` / ``{% ifversion %}``), so pages are taken *rendered for one product version*
from the endpoints advertised in https://docs.github.com/llms.txt:

* ``/api/pagelist/versions`` - supported versions (fpt, ghec, enterprise-server@3.x)
* ``/api/pagelist/en/<version>`` - every page path of that version
* ``/api/article/body?pathname=...`` - one page as Markdown

docs.github.com sits behind an edge rate limiter: parallel bursts get HTTP 429 (``retry-after: 0``) followed by a
site-wide block of roughly a minute. Requests are therefore sequential (1 s apart by default, slowing down after any
429), and raw page bodies are cached under ``.docs/.src/gha/<version>/`` so an interrupted fetch resumes where it
stopped. Archived (deprecated) GHES releases are not served as Markdown (HTTP 403), so fetch a GHES bundle while the
release is still supported if you need to keep it.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

from .markdown import tidy
from .store import Bundle, covered, docs_dir

SITE = "https://docs.github.com"
SECTIONS = ("actions",)
CACHE_DAYS = 7
_LINK = re.compile(r"\]\((/en/[^)\s#]*)(#[^)\s]*)?\)")
_SVG = re.compile(r"<svg\b([^>]*)>.*?</svg>", re.S)
_ARIA = re.compile(r'aria-label="([^"]*)"')


def _svg_text(m: re.Match) -> str:
    """Inline octicons (check/x in comparison tables) -> their aria-label ("Yes"/"No")."""
    label = _ARIA.search(m.group(1))
    return label.group(1) if label else ""


def versions() -> dict:
    return requests.get(f"{SITE}/api/pagelist/versions", timeout=30).json()


def label_of(version: str) -> str:
    """Any accepted spelling -> bundle label, offline: dotcom -> fpt, enterprise-server@3.22 / 3.22 -> ghes-3.22."""
    version = version.strip()
    if version in ("fpt", "free-pro-team@latest", "dotcom", "github.com"):
        return "fpt"
    if version in ("ghec", "enterprise-cloud@latest"):
        return "ghec"
    m = re.fullmatch(r"(?:ghes-|enterprise-server@)?(\d+\.\d+)", version)
    return f"ghes-{m.group(1)}" if m else version


def version_id(label: str) -> str | None:
    """Bundle label -> docs.github.com version id (None for a label no fetch produces, e.g. a bare ``ghes``)."""
    label = label_of(label)
    if label == "fpt":
        return "free-pro-team@latest"
    if label == "ghec":
        return "enterprise-cloud@latest"
    return f"enterprise-server@{label.removeprefix('ghes-')}" if re.fullmatch(r"ghes-\d+\.\d+", label) else None


def url_prefix(version_id: str) -> str:
    """Path prefix of a version's pages on docs.github.com (GitHub.com pages have none)."""
    return "/en" if version_id == "free-pro-team@latest" else f"/en/{version_id}"


def resolve_version(label: str | None) -> tuple[str, str]:
    """User label -> (docs version id, bundle label). fpt|ghec|ghes|ghes-3.22|3.22|enterprise-server@3.22."""
    label = label_of(label or "fpt")
    if label in ("fpt", "ghec"):
        return version_id(label), label
    info = versions()
    rel = info["ghesLatest"] if label in ("ghes", "enterprise-server") else label.removeprefix("ghes-")
    if rel not in info["ghesVersions"]:
        raise SystemExit(f"GHES {rel} is not on docs.github.com (supported: {', '.join(info['ghesVersions'])}; "
                         f"deprecated releases are only in the archived docs)")
    return f"enterprise-server@{rel}", f"ghes-{rel}"


class _Client:
    def __init__(self, delay: float):
        self.delay = delay
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "j2gha-docs-fetcher"
        self._last = 0.0

    def get(self, url: str) -> requests.Response:
        for attempt in range(8):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            r = self.s.get(url, timeout=60)
            if r.status_code not in (429, 502, 503, 504):
                return r
            # The edge limiter answers 429 with "retry-after: 0" and then blocks the IP for ~40-100 s.
            backoff = max(float(r.headers.get("Retry-After") or 0), min(90, 10 * 2 ** attempt))
            print(f"[docs] {r.status_code} from docs.github.com; waiting {backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
            self.delay = min(self.delay * 1.5, 5)  # stay slower for the rest of the run
        r.raise_for_status()
        return r


def _local_path(pathname: str, version_id: str) -> str:
    """/en/enterprise-server@3.22/actions/reference/x -> actions/reference/x.md"""
    rest = pathname.removeprefix("/en").removeprefix(f"/{version_id}")
    return rest.strip("/") + ".md"


def fetch(version: str | None = None, sections: tuple[str, ...] = SECTIONS, delay: float | None = None,
          refresh: bool = False) -> Bundle:
    """Build ``.docs/gha/<label>`` from ``sections`` (docs.github.com path prefixes). Pages of an existing bundle
    outside those sections (an earlier fetch of other sections) are kept; pages inside them are replaced."""
    version_id, label = resolve_version(version)
    sections = tuple(s.strip("/") for s in sections)
    client = _Client(delay if delay is not None else 1.0)
    prefix = url_prefix(version_id)
    listing = client.get(f"{SITE}/api/pagelist/en/{version_id}").text.split()
    wanted = [p for p in listing if any(p == f"{prefix}/{s}" or p.startswith(f"{prefix}/{s}/") for s in sections)]
    if not wanted:
        raise SystemExit(f"no pages under {sections} for {version_id}")

    cache = docs_dir() / ".src" / "gha" / label
    cache.mkdir(parents=True, exist_ok=True)
    bodies: dict[str, str] = {}
    print(f"[docs] docs.github.com {version_id}: {len(wanted)} pages (~{len(wanted) * client.delay / 60:.0f} min "
          f"at {client.delay}s/request; cached pages are reused)", file=sys.stderr)
    for i, pathname in enumerate(wanted, 1):
        cached = cache / _local_path(pathname, version_id)
        fresh = cached.is_file() and time.time() - cached.stat().st_mtime < CACHE_DAYS * 86400
        if fresh and not refresh:
            bodies[pathname] = cached.read_text(encoding="utf-8")
            continue
        r = client.get(f"{SITE}/api/article/body?pathname={pathname}")
        if r.status_code == 404:
            continue
        r.raise_for_status()
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(r.text, encoding="utf-8")
        bodies[pathname] = r.text
        if i % 25 == 0:
            print(f"[docs]   {i}/{len(wanted)}", file=sys.stderr)

    info = versions()["allVersions"].get(version_id, {})
    bundle = Bundle("gha", label, f"GitHub Actions documentation - {info.get('versionTitle', label)}", "",
                    origin={"pagelist": f"{SITE}/api/pagelist/en/{version_id}",
                            "article": f"{SITE}/api/article/body?pathname=<path>"},
                    licence="CC-BY-4.0 (github/docs content)", components={"docs.github.com": version_id})
    with bundle.staged(sections, key=lambda p: p.path.removesuffix(".md")):
        kept = {f"{prefix}/{p.path.removesuffix('.md')}": p.path for p in bundle.pages}
        local = {**kept, **{p: _local_path(p, version_id) for p in bodies}}
        for pathname, body in bodies.items():
            rel = local[pathname]
            lines = body.strip().split("\n")
            title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("# ") else rel
            body = "\n".join(lines[1:])
            here = Path(rel).parent

            def relink(m: re.Match, here: Path = here) -> str:
                target, anchor = m.group(1).rstrip("/"), m.group(2) or ""
                if target in local:
                    return f"]({_relpath(local[target], here)}{anchor})"
                return f"]({SITE}{target}{anchor})"

            body = _LINK.sub(relink, _SVG.sub(_svg_text, body))
            intro = next((ln.strip() for ln in body.split("\n") if ln.strip() and not ln.startswith(
                ("#", ">", "|", "-", "*", "`", "<"))), "")
            parts = rel.removesuffix(".md").split("/")
            section = parts[0] if len(parts) == 1 else parts[1] if len(parts) <= 3 else f"{parts[1]} / {parts[2]}"
            bundle.part = next(s for s in sections if covered(pathname, [f"{prefix}/{s}"]))
            bundle.write(rel, title, tidy(body), f"{SITE}{pathname}", section,
                         _short(intro), index=_sub_index(parts))
        pagelist = sorted({*bodies, *kept})
        bundle.components.update({"sections": ",".join(bundle.parts), "pages": str(len(pagelist))})
        bundle.summary = (f"docs.github.com rendered for {version_id} ({len(pagelist)} pages under "
                          f"/{', /'.join(bundle.parts)}). Start with actions/reference/workflows-and-actions/"
                          "workflow-syntax.md, contexts.md, expressions.md, events-that-trigger-workflows.md; Jenkins "
                          "migration guide: actions/tutorials/migrate-to-github-actions/manual-migrations/"
                          "migrate-from-jenkins.md. Links to pages in this bundle are relative; others point to "
                          "docs.github.com.")
        (bundle.path / "pagelist.json").write_text(json.dumps(pagelist, indent=0) + "\n")
        bundle.finish()
    return bundle


def _sub_index(parts: list[str]) -> str:
    """Reference pages + get-started stay in the top INDEX.md; the rest get one sub-index per category."""
    if len(parts) > 2 and parts[1] not in ("reference", "get-started"):
        return f"{parts[0]}/{parts[1]}/INDEX.md"
    return "INDEX.md"


def _short(text: str, limit: int = 110) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return text if len(text) <= limit else text[: limit - 3].rsplit(" ", 1)[0] + "..."


def _relpath(target: str, here: Path) -> str:
    import os

    return os.path.relpath(target, here if str(here) != "." else ".")
