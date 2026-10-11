"""Local documentation bundles: converters, store/index layout, crosswalk integrity. Offline (no Docker/network)."""

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from j2gha.docs import store, xref
from j2gha.docs.asciidoc import adoc_to_md, report_sections
from j2gha.docs.gha import _local_path, resolve_version
from j2gha.docs.jenkins import _params

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def docs(tmp_path, monkeypatch):
    monkeypatch.setenv("J2GHA_DOCS_DIR", str(tmp_path))
    for var in ("J2GHA_DOCS_JENKINS", "J2GHA_DOCS_GHA"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_adoc_to_md_handbook_constructs():
    src = """---
layout: section
title: "Pipeline Syntax"
---
:toc:

== Declarative Pipeline

[[agent]]
=== agent

See link:../getting-started[Getting started], plugin:docker-workflow[Docker Pipeline] and <<when,the when directive>>.

NOTE: Only *one* agent.

[source,groovy]
----
pipeline {
    agent any
}
----

timeout::
Set a timeout.

* first
** nested
image::foo.png[]
"""
    title, md = adoc_to_md(src, "https://www.jenkins.io/doc/book/pipeline/syntax/")
    assert title == "Pipeline Syntax"
    assert "## Declarative Pipeline" in md and "### agent" in md
    assert '<a id="agent"></a>' in md
    assert "[Getting started](https://www.jenkins.io/doc/book/pipeline/getting-started)" in md
    assert "[Docker Pipeline](https://plugins.jenkins.io/docker-workflow)" in md
    assert "[the when directive](#when)" in md
    assert "> **Note:** Only **one** agent." in md
    assert "```groovy\npipeline {\n    agent any\n}\n```" in md
    assert "- **timeout**" in md and "- first" in md and "  - nested" in md
    assert "image::" not in md and ":toc:" not in md


def test_report_sections_splits_symbols_and_converts_html():
    src = """---
layout: pipelinesteps
title: "when"
---
:notitle:

== when

plugin:pipeline-model-definition[View this plugin on the Plugins Index]

=== `branch`: Execute the stage when the branch matches
++++
<div><p>Matches the <code>BRANCH_NAME</code>.</p></div>
<ul><li><code>pattern : String</code></li></ul>
++++
"""
    title, sections = report_sections(src)
    assert title == "when"
    heading, body = sections[-1]
    assert heading.startswith("`branch`")
    assert "`BRANCH_NAME`" in body and "- `pattern : String`" in body and "<div>" not in body


def test_controller_step_parameters_render_nested_types():
    from bs4 import BeautifulSoup

    html = """<dd class="step-body"><dl class="help-list mandatory"><dt class="help-title"><code>time</code></dt>
    <dd class="help-body"><div><strong>Type:</strong>int</div></dd></dl>
    <dl class="help-list optional"><dt class="help-title"><code>unit</code> (optional)</dt><dd class="help-body">
    <div class="help"><div>The unit of the time parameter.</div></div>
    <div class="values-box nested"><div class="value list-item"><code>SECONDS</code></div>
    <div class="value list-item"><code>MINUTES</code></div></div></dd></dl></dd>"""
    lines = _params(BeautifulSoup(html, "html.parser").dd)
    text = "\n".join(lines)
    assert "- `time`: int" in text
    assert "- `unit` (optional)" in text
    assert "  The unit of the time parameter." in text
    assert "  Values: `SECONDS`, `MINUTES`" in text


def test_bundle_indexes_manifest_and_selection(docs):
    b = store.Bundle("gha", "fpt", "GHA docs", "summary")
    b.reset()
    b.write("actions/reference/limits.md", "Actions limits", "# Actions limits\n\nBody.", "https://x/limits",
            "reference / limits", "Limits.")
    b.write("actions/how-tos/a/b.md", "B", "Body", "https://x/b", "how-tos / a", "b page",
            index="actions/how-tos/INDEX.md")
    b.finish()
    page = (docs / "gha/fpt/actions/reference/limits.md").read_text()
    assert page.startswith("# Actions limits\n\n> Source: https://x/limits (gha fpt)\n\nBody.")
    assert page.count("# Actions limits") == 1  # duplicated H1 dropped
    top = (docs / "gha/fpt/INDEX.md").read_text()
    assert "- [Actions limits](actions/reference/limits.md): Limits." in top
    assert "[actions/how-tos/INDEX.md](actions/how-tos/INDEX.md): 1 pages" in top
    sub = (docs / "gha/fpt/actions/how-tos/INDEX.md").read_text()
    assert "- [B](a/b.md): b page" in sub
    manifest = json.loads((docs / "gha/fpt/manifest.json").read_text())
    assert manifest["files"] == 4 and manifest["licence"] == ""
    assert store.selected() == {"gha": "fpt"}  # first bundle of a source becomes the default
    assert store.bundle_path("gha") == docs / "gha" / "fpt"
    assert store.bundle_path("jenkins") is None
    assert "| gha | fpt | yes |" in (docs / "INDEX.md").read_text()


def test_gha_version_labels_and_paths():
    assert resolve_version(None) == ("free-pro-team@latest", "fpt")
    assert resolve_version("ghec") == ("enterprise-cloud@latest", "ghec")
    assert _local_path("/en/actions/reference/limits", "free-pro-team@latest") == "actions/reference/limits.md"
    assert _local_path("/en/enterprise-server@3.19/actions/reference/limits",
                       "enterprise-server@3.19") == "actions/reference/limits.md"


def test_xref_pages_exist_on_docs_github_com():
    pages = {p.removeprefix("/en/actions/") for p in (FIXTURES / "gha-pagelist-fpt.txt").read_text().split()}
    table = yaml.safe_load((Path(xref.RULES) / "docs-xref.yaml").read_text())["xref"]
    missing = [(k, g) for k, e in table.items() for g in e.get("gha", []) if g.split("#")[0] not in pages]
    assert not missing, missing
    assert all(e.get("kind") in ("directive", "step", "global", "concept") for e in table.values())


def test_xref_without_bundles_falls_back_to_urls(docs):
    out = xref.lookup(["stash"])
    assert "### `stash` (step)" in out
    assert "Catalog: **policy**" in out
    assert "https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts" in out
    path = xref.write_xref()
    text = path.read_text()
    assert "## Declarative directives and options" in text and "### `agent` (directive)" in text


def test_gha_inline_svg_icons_become_text():
    from j2gha.docs.gha import _SVG, _svg_text

    cell = '| Yes | <svg version="1.1" class="octicon octicon-x" aria-label="No" role="img"><path d="M3"></path></svg> |'
    assert _SVG.sub(_svg_text, cell) == "| Yes | No |"


def test_xref_unknown_term_and_version_override(docs, monkeypatch):
    out = xref.lookup(["frobnicate"])
    assert "Not in the crosswalk or the step catalog" in out
    b = store.Bundle("gha", "ghes-3.18", "GHES", "s")
    b.reset()
    b.write("actions/reference/workflows-and-actions/workflow-syntax.md", "Workflow syntax", "x", "u", "reference")
    b.finish()
    monkeypatch.setenv("J2GHA_DOCS_GHA", "ghes-3.18")
    assert "/gha/ghes-3.18/actions/reference/workflows-and-actions/workflow-syntax.md#onschedule" in xref.lookup(["cron"])


def test_web_refs_never_use_local_bundles(docs, monkeypatch):
    """The migration report is committed: its links must not depend on what this machine has downloaded."""
    b = store.Bundle("gha", "ghes-3.18", "GHES", "s")
    b.reset()
    b.write("actions/reference/workflows-and-actions/workflow-syntax.md", "Workflow syntax", "x", "u", "reference")
    b.finish()
    monkeypatch.setenv("J2GHA_DOCS_GHA", "ghes-3.18")
    assert str(docs) in xref.lookup(["cron"])  # the interactive lookup does use the bundle
    monkeypatch.setattr(store, "docs_dir", lambda: pytest.fail("web_refs read the local docs directory"))
    refs = xref.web_refs("CRON")
    urls = [url for side in ("jenkins", "gha") for _, url in refs[side]]
    assert refs["key"] == "cron" and urls
    assert all(u.startswith(("https://www.jenkins.io/", "https://docs.github.com/en/actions/")) for u in urls)
    assert "https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule" in urls
    assert xref.web_refs("frobnicate") is None and xref.web_refs("echo") is None  # echo: catalog only


def test_xref_anchors_resolve_in_local_bundles():
    """Runs only where bundles were fetched (j2gha docs fetch); catches renamed headings after a re-fetch."""
    jb, gb = store.bundle_path("jenkins"), store.bundle_path("gha", "fpt")
    if not (jb and gb):
        pytest.skip("no local docs bundles")

    def anchors(path: Path) -> set[str]:
        text = path.read_text(encoding="utf-8")
        found = set(re.findall(r'<a id="([^"]+)"', text))
        for heading in re.findall(r"^#{1,6}\s+(.*)$", text, re.M):
            found.add(re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-"))
        return found

    broken = []
    for key, entry in yaml.safe_load((Path(xref.RULES) / "docs-xref.yaml").read_text())["xref"].items():
        for base, pages in ((gb / "actions", [f"{p.split('#')[0]}.md#{p.partition('#')[2]}" for p in entry.get("gha", [])]),
                            (jb, entry.get("jenkins", []))):
            for page in pages:
                rel, _, anchor = page.partition("#")
                path = base / rel
                if not path.is_file() or (anchor and anchor not in anchors(path)):
                    broken.append((key, page))
    assert not broken, broken


# --------------------------------------------------------------------------- fetch safety (offline fakes)
class _Resp:
    def __init__(self, text="", js=None, headers=None, status=200, content=b""):
        self.text, self._js, self.headers, self.status_code, self.content = text, js, headers or {}, status, content

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _report(title: str, symbols: dict[str, str]) -> str:
    return f'---\nlayout: pipelinesteps\ntitle: "{title}"\n---\n:notitle:\n\n== {title}\n\n' + "".join(
        f"=== `{s}`: {s} step\n++++\n<div><p>{text}</p></div>\n++++\n" for s, text in symbols.items())


def _zip(files: dict[str, str]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


@pytest.fixture
def fake_jenkins(docs, monkeypatch):
    """Offline jenkins.fetch: fake controller, handbook clone and reports.jenkins.io zips; ``state`` drives them."""
    import subprocess
    from types import SimpleNamespace

    from j2gha.docs import jenkins

    state = {"core": "2.580.1", "plugins": {"workflow-cps": "4000.v1", "workflow-durable-task-step": "1400.v1"},
             "rev": "r1", "fail": None, "cps": [],
             "plugin_zip": {"workflow-basic-steps.adoc": _report("Basic Steps", {"sleep": "Sleep."}),
                            "pipeline-utility-steps.adoc": _report("Utility Steps", {"readJSON": "Read JSON."})}}
    html = ('<div class="dsl-reference"><div class="steps-box"><dl class="steps root"><dt class="step-title">'
            '<code>sh</code>: Shell Script</dt><dd><div class="help">Runs {rev}.</div></dd></dl></div></div>')
    state["directives"] = [{"category": "options", "symbol": "disableConcurrentBuilds", "id": "d", "plugin": "job",
                            "version": "1.0", "displayName": "Do not allow concurrent builds", "params": []}]

    def get(url, **kw):
        if state["fail"] == "controller" and "pipeline-syntax" in url:
            raise ConnectionError("controller died")
        if url.endswith("/api/json"):
            return _Resp(headers={"X-Jenkins": state["core"]})
        if "pluginManager" in url:
            return _Resp(js={"plugins": [{"shortName": k, "version": v} for k, v in state["plugins"].items()]})
        if url.endswith("/pipeline-syntax/html"):
            return _Resp(html.format(rev=state["rev"]))
        if url.endswith("/pipeline-syntax/globals"):
            return _Resp('<div id="main-panel"><dl class="root"><dt>env</dt><dd><p>Environment.</p></dd></dl></div>')
        return _Resp("")

    def script(code):
        if "StepDescriptor" in code:
            return f"sh\tworkflow-durable-task-step\t{state['plugins'].get('workflow-durable-task-step', '1')}"
        return json.dumps(state["directives"])

    ctl = SimpleNamespace(base="http://fake:18080", s=SimpleNamespace(get=get), script=script)

    def handbook(bundle, ref="master", cps_version=None):
        if state["fail"] == "handbook":
            raise subprocess.CalledProcessError(128, ["git", "fetch"], stderr="unable to access jenkins.io")
        state["cps"].append(cps_version)
        bundle.write("handbook/pipeline/syntax.md", "Pipeline Syntax", f"handbook {state['rev']}", "u",
                     "Handbook (jenkins.io)")
        bundle.origin["handbook"], bundle.components["jenkins.io"] = "repo", state["rev"]

    def reports(url, **kw):
        if state["fail"] == "plugins":
            raise ConnectionError("reports.jenkins.io unreachable")
        files = state["plugin_zip"] if url.endswith("allAscii.zip") else {
            "options.adoc": _report("options", {"disableConcurrentBuilds": "latest", "buildDiscarder": "Discard."})}
        return _Resp(content=_zip(files), headers={"ETag": state["rev"]})

    monkeypatch.setattr(jenkins, "controller_client", lambda: (ctl, state["core"]))
    monkeypatch.setattr(jenkins, "fetch_handbook", handbook)
    monkeypatch.setattr(jenkins, "requests", SimpleNamespace(get=reports))
    return state


def _snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


def test_jenkins_failed_fetch_keeps_previous_bundle(docs, fake_jenkins):
    from j2gha.docs import jenkins

    b = jenkins.fetch()
    before = _snapshot(docs)
    for fail in ("controller", "handbook", "plugins"):
        fake_jenkins["fail"] = fail
        with pytest.raises(Exception, match="died|exit status|unreachable"):
            jenkins.fetch()
        with pytest.raises(Exception, match="died|exit status|unreachable"):
            jenkins.fetch((fail,), label=b.version)
        assert _snapshot(docs) == before, fail  # bundle, selected.json, INDEX.md: all untouched
        assert [p.name for p in (docs / "jenkins").iterdir()] == [b.version]  # no staging/backup dirs left
    assert store.bundle_path("jenkins") == docs / "jenkins" / b.version


def test_jenkins_partial_refresh_keeps_other_parts(docs, fake_jenkins):
    from j2gha.docs import jenkins

    label = jenkins.fetch().version
    home = docs / "jenkins" / label
    full = set(_snapshot(home))
    fake_jenkins["rev"] = "r2"
    jenkins.fetch(("handbook",), label=label)
    assert "handbook r2" in (home / "handbook/pipeline/syntax.md").read_text()
    assert "Runs r1." in (home / "steps/sh.md").read_text()  # controller part kept as fetched
    assert set(_snapshot(home)) == full
    assert fake_jenkins["cps"] == ["4000.v1", "4000.v1"]  # the kept controller part still tells the handbook its cps
    m = json.loads((home / "manifest.json").read_text())
    assert m["components"]["workflow-cps"] == "4000.v1" and m["components"]["jenkins.io"] == "r2"
    assert set(m["parts"]) == set(jenkins.PARTS) and set(m["origin"]) == set(jenkins.PARTS)
    index = (home / "INDEX.md").read_text()
    assert "[sh](steps/sh.md)" in index and "[Pipeline Syntax](handbook/pipeline/syntax.md)" in index
    installed = home / "declarative/options/disableConcurrentBuilds.md"
    assert "(installed in the harness controller)" in installed.read_text()

    del fake_jenkins["plugin_zip"]["pipeline-utility-steps.adoc"]  # refreshing a part also drops what it no longer has
    jenkins.fetch(("plugins",), label=label)
    assert (home / "plugins/workflow-basic-steps.md").is_file()
    assert not (home / "plugins/pipeline-utility-steps.md").exists()
    assert (home / "handbook/pipeline/syntax.md").is_file() and (home / "steps/sh.md").is_file()

    discard = home / "declarative/options/buildDiscarder.md"
    assert "latest" in (home / "declarative/INDEX.md").read_text() and discard.is_file()
    fake_jenkins["rev"] = "r3"
    fake_jenkins["directives"].append({**fake_jenkins["directives"][0], "symbol": "buildDiscarder"})
    jenkins.fetch(("controller",))  # same core + plugins = same default label
    assert "Runs r3." in (home / "steps/sh.md").read_text()
    assert "(installed in the harness controller)" in installed.read_text()
    assert "(installed in the harness controller)" in discard.read_text()  # replaces the kept latest-release page
    assert (home / "declarative/INDEX.md").read_text().count("(options/buildDiscarder.md)") == 1


def test_partial_refresh_of_legacy_bundle_is_refused(docs, fake_jenkins):
    from j2gha.docs import jenkins

    b = store.Bundle("jenkins", "2.580.1", "old", "s", origin={"controller": "c", "handbook": "h"})
    b.reset()
    b.write("steps/sh.md", "sh", "old", "u", "Steps")
    b.finish()
    m = json.loads((b.path / "manifest.json").read_text())
    del m["parts"]  # as written before parts/pages.json existed
    (b.path / "manifest.json").write_text(json.dumps(m))
    (b.path / "pages.json").unlink()
    with pytest.raises(SystemExit, match="predates partial refresh"):
        jenkins.fetch(("handbook",), label="2.580.1")
    assert (b.path / "steps/sh.md").read_text().endswith("old\n")
    jenkins.fetch(label="2.580.1")  # a whole refresh is fine (core-only label of the running core)
    assert "Runs r1." in (b.path / "steps/sh.md").read_text()


def test_jenkins_label_identifies_core_and_plugins(docs, fake_jenkins):
    import hashlib

    from j2gha.docs import jenkins

    a = jenkins.fetch(("controller",))
    digest = hashlib.sha256(b"workflow-cps:4000.v1\nworkflow-durable-task-step:1400.v1").hexdigest()[:8]
    assert a.version == f"2.580.1+p{digest}"
    fake_jenkins["plugins"]["kubernetes"] = "4300.v1"
    b = jenkins.fetch(("controller",))
    assert b.version != a.version and (docs / "jenkins" / a.version / "steps/sh.md").is_file()
    assert store.selected()["jenkins"] == b.version  # the running controller's docs become the default
    for kwargs in ({"version": "2.400.1"}, {"label": "2.400.1"}, {"label": "2.580.1+pdeadbeef"}):
        with pytest.raises(SystemExit, match=re.escape(f"running harness controller, which is {b.version}")):
            jenkins.fetch(("controller",), **kwargs)
    with pytest.raises(SystemExit, match="can't be checked"):
        jenkins.fetch(("handbook",), version="2.580.1")
    assert jenkins.fetch(("controller",), version="2.580.1").version == b.version
    assert jenkins.fetch(("controller",), version="mine").version == "mine"  # not a version number: a label
    assert store.selected()["jenkins"] == b.version  # custom labels don't take over the default
    with pytest.raises(SystemExit, match="unknown jenkins docs parts"):
        jenkins.fetch(("steps",))
    legacy = store.Bundle("jenkins", "2.580.1", "core-only label", "s")  # bundles named before the plugin digest
    legacy.reset()
    legacy.write("steps/sh.md", "sh", "x", "u", "Steps")
    legacy.finish()
    assert store.select("jenkins", "2.580.1") == "2.580.1"
    assert store.bundle_path("jenkins") == docs / "jenkins" / "2.580.1"


@pytest.fixture
def fake_gha(docs, monkeypatch):
    """Offline gha.fetch: ``state["pages"]`` maps actions/... page paths to Markdown bodies."""
    from j2gha.docs import gha

    state = {"fail": False, "pages": {
        "actions/reference/limits": "# Limits\n\nlimits v1",
        "actions/how-tos/a/b": "# B\n\nSee [limits](/en/actions/reference/limits).",
        "actions/concepts/workflows-and-actions/workflow-artifacts": "# Workflow artifacts\n\nartifacts"}}

    class Client:
        def __init__(self, delay):
            self.delay = 0

        def get(self, url):
            if "/api/pagelist/en/" in url:
                prefix = gha.url_prefix(url.rsplit("/", 1)[1])
                return _Resp("\n".join(f"{prefix}/{p}" for p in state["pages"]))
            if state["fail"]:
                raise ConnectionError("docs.github.com unreachable")
            path = url.split("pathname=", 1)[1]
            rel = next((p for p in state["pages"] if path.endswith(f"/{p}")), None)
            return _Resp(state["pages"][rel]) if rel else _Resp(status=404)

    monkeypatch.setattr(gha, "_Client", Client)
    monkeypatch.setattr(gha, "versions", lambda: {"allVersions": {}, "ghesVersions": ["3.18"], "ghesLatest": "3.18"})
    return state


def test_gha_failed_fetch_keeps_previous_bundle(docs, fake_gha, monkeypatch):
    from j2gha.docs import gha

    gha.fetch("fpt")
    before = _snapshot(docs / "gha") | {"INDEX.md": (docs / "INDEX.md").read_text()}
    fake_gha["fail"] = True
    with pytest.raises(ConnectionError):
        gha.fetch("fpt", refresh=True)  # download fails
    fake_gha["fail"] = False

    def broken(text):
        raise ValueError("conversion failed")

    monkeypatch.setattr(gha, "tidy", broken)  # fails while writing the new bundle
    with pytest.raises(ValueError):
        gha.fetch("fpt")
    assert _snapshot(docs / "gha") | {"INDEX.md": (docs / "INDEX.md").read_text()} == before
    assert [p.name for p in (docs / "gha").iterdir()] == ["fpt"] and store.selected() == {"gha": "fpt"}


def test_gha_partial_refresh_keeps_other_sections(docs, fake_gha):
    from j2gha.docs import gha

    gha.fetch("fpt")
    fake_gha["pages"]["actions/how-tos/a/b"] = "# B\n\nb v2, see [limits](/en/actions/reference/limits#x)."
    b = gha.fetch("fpt", sections=("actions/how-tos",), refresh=True)
    home = docs / "gha" / "fpt"
    page = (home / "actions/how-tos/a/b.md").read_text()
    assert "b v2" in page and "[limits](../../reference/limits.md#x)" in page  # relinked to the kept page
    assert "limits v1" in (home / "actions/reference/limits.md").read_text()
    assert (home / "actions/concepts/workflows-and-actions/workflow-artifacts.md").is_file()
    assert "- [B](a/b.md)" in (home / "actions/how-tos/INDEX.md").read_text()
    assert "- [Limits](actions/reference/limits.md)" in (home / "INDEX.md").read_text()
    assert len(json.loads((home / "pagelist.json").read_text())) == 3
    m = json.loads((home / "manifest.json").read_text())
    assert list(m["parts"]) == ["actions", "actions/how-tos"] and m["components"]["pages"] == "3"
    assert b.path == home and m["pages"] == 3
    gha.fetch("fpt")  # a whole-section fetch supersedes the narrower one
    assert list(json.loads((home / "manifest.json").read_text())["parts"]) == ["actions"]


@pytest.mark.parametrize("bad", ["..", "../x", "/abs", "a/b", ".", ".hidden", "x" * 65, "a b"])
def test_unsafe_version_labels_are_rejected(docs, monkeypatch, bad):
    with pytest.raises(SystemExit, match="invalid jenkins docs version"):
        store.Bundle("jenkins", bad, "t", "s")
    with pytest.raises(SystemExit, match="invalid gha docs version"):
        store.select("gha", bad)
    with pytest.raises(SystemExit, match="invalid jenkins docs version"):
        store.bundle_path("jenkins", bad)
    monkeypatch.setenv("J2GHA_DOCS_GHA", bad)
    with pytest.raises(SystemExit, match=r"from \$J2GHA_DOCS_GHA"):
        store.bundle_path("gha")


def test_cli_rejects_unsafe_labels_before_touching_anything(docs, monkeypatch):
    from j2gha import cli
    from j2gha.docs import jenkins

    monkeypatch.setattr(jenkins, "controller_client", lambda: pytest.fail("controller started"))
    for argv in (["docs", "path", "gha", "--version", "../x"], ["docs", "use", "jenkins", "../gha/fpt"],
                 ["docs", "fetch", "jenkins", "--label", "../.."], ["docs", "xref", "stash", "--gha-version", "/abs"]):
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        assert exc.value.code and "invalid" in str(exc.value.code), argv
    assert not any(docs.iterdir())


def test_rmtree_stays_inside_the_source_dir(docs):
    (docs / "jenkins" / "x").mkdir(parents=True)
    (docs / "keep.txt").write_text("keep")
    for path in (docs / "jenkins" / "..", docs / "jenkins", docs / "jenkins" / "x" / ".." / ".."):
        with pytest.raises(RuntimeError, match="refusing to delete"):
            store._remove("jenkins", path)
    assert (docs / "keep.txt").is_file() and (docs / "jenkins" / "x").is_dir()


def test_xref_keeps_requested_ghes_version_without_bundle(docs, monkeypatch, capsys):
    from j2gha import cli

    monkeypatch.setenv("J2GHA_DOCS_GHA", "ghes-3.18")
    out = xref.lookup(["stash"])
    assert ("https://docs.github.com/en/enterprise-server@3.18/actions/concepts/workflows-and-actions/"
            "workflow-artifacts") in out
    assert "https://docs.github.com/en/actions/" not in out
    assert ("GitHub Actions docs: ghes-3.18 not downloaded (https://docs.github.com/en/enterprise-server@3.18 links)"
            in xref.write_xref().read_text())
    monkeypatch.setenv("J2GHA_DOCS_GHA", "")  # empty = unset; lets monkeypatch undo the CLI's own setting
    assert cli.main(["docs", "xref", "stash", "--gha-version", "enterprise-server@3.19"]) == 0
    assert "https://docs.github.com/en/enterprise-server@3.19/actions/tutorials/store-and-share-data" in \
        capsys.readouterr().out


def test_xref_reports_page_missing_from_ghes_bundle(docs, fake_gha, monkeypatch):
    from j2gha.docs import gha

    gha.fetch("ghes-3.18")  # has workflow-artifacts, not tutorials/store-and-share-data
    monkeypatch.setenv("J2GHA_DOCS_GHA", "ghes-3.18")
    out = xref.lookup(["stash"])
    assert "/gha/ghes-3.18/actions/concepts/workflows-and-actions/workflow-artifacts.md" in out
    assert ("[tutorials/store-and-share-data - not in the ghes-3.18 docs (GitHub.com page)]"
            "(https://docs.github.com/en/actions/tutorials/store-and-share-data)") in out
    shutil.rmtree(docs / "gha" / "ghes-3.18")
    gha.fetch("ghes-3.18", sections=("actions/concepts",))  # tutorials/ not fetched: not claimed missing
    out = xref.lookup(["stash"])
    assert "not in the ghes-3.18 docs" not in out
    assert "(https://docs.github.com/en/enterprise-server@3.18/actions/tutorials/store-and-share-data)" in out
