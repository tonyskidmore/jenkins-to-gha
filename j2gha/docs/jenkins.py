"""Jenkins documentation fetchers (one bundle per controller, ``.docs/jenkins/<core>+p<plugin-set digest>/``).

Parts, in order of authority for this harness:

* ``controller`` - ``steps/``, ``globals/``, ``plugins.md`` and the installed ``declarative/<directive>/`` symbols:
  the step, global-variable and directive reference the harness controller generates for *its own* core + plugin
  versions (``/pipeline-syntax/html``, ``/globals``, ``/descriptor/<id>/help``).
  The only version-exact Jenkins reference: it is what the controller validates and runs Jenkinsfiles against.
* ``handbook`` - ``book/``: the Pipeline chapters of the jenkins.io handbook (AsciiDoc in jenkins-infra/jenkins.io,
  CC BY-SA 4.0), pinned by commit SHA (the site has no tags or per-release docs), plus workflow-cps ``doc/*.md``
  at the installed plugin's release tag.
* ``declarative`` - ``declarative/<directive>/``: the agent/options/parameters/triggers/when symbols of plugins the
  controller does *not* have (reports.jenkins.io/declarative.zip, latest releases, rebuilt weekly; ETag recorded).
* ``plugins`` - ``plugins/<plugin>.md``: the step reference of all ~720 plugins (reports.jenkins.io/allAscii.zip,
  latest releases) for steps the controller does not have installed.

A fetch of some parts onto an existing bundle replaces only those parts and keeps the others (pages, provenance).
"""

from __future__ import annotations

import hashlib
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

from .asciidoc import adoc_to_md, report_sections
from .markdown import html_to_md, indent, slug
from .store import Bundle, Page, docs_dir, version_label

PARTS = ("controller", "handbook", "declarative", "plugins")
JENKINS_IO_REPO = "https://github.com/jenkins-infra/jenkins.io"
HANDBOOK_PATHS = ("content/doc/book/pipeline", "content/doc/pipeline/tour", "content/doc/book/using",
                  "content/doc/book/glossary")
REPORTS = "https://reports.jenkins.io"

STEP_DOC_URL = "https://www.jenkins.io/doc/pipeline/steps/{plugin}/#{anchor}"
# Manifest components recorded by the non-controller parts; the rest (core + plugin versions) are the controller's.
COMPONENT_PARTS = {"jenkins.io": "handbook", "reports.jenkins.io/declarative.zip": "declarative",
                   "reports.jenkins.io/allAscii.zip": "plugins"}
_VERSION = re.compile(r"\d+(?:\.\d+)+")  # a Jenkins core version, as opposed to a bundle label
_IDENTITY = re.compile(r"(\d+(?:\.\d+)+)(?:\+p[0-9a-f]{8})?")  # labels that claim a core (+ plugin set)

# Which plugin (and version) provides each step: StepDescriptors first, then @Symbol-annotated describables
# (archiveArtifacts, junit, cleanWs... are SimpleBuildSteps exposed through their symbol).
_PLUGIN_MAP = r"""
import org.jenkinsci.plugins.workflow.steps.StepDescriptor
def j = jenkins.model.Jenkins.get()
def pm = j.pluginManager
def show = { name, cls ->
  def p = pm.whichPlugin(cls)
  println "${name}\t${p?.shortName ?: 'core'}\t${p?.version ?: jenkins.model.Jenkins.VERSION}"
}
new ArrayList(StepDescriptor.all()).each { d -> show(d.functionName, d.clazz) }
j.getExtensionList(hudson.model.Descriptor).each { d ->
  def s = d.getClass().getAnnotation(org.jenkinsci.Symbol)
  if (s) s.value().each { n -> show(n, d.clazz) }
}
"""


# Declarative directive symbols (triggers/options/parameters/when/agent) the controller has installed, with their
# descriptor ids so the help can be fetched from /descriptor/<id>/help[/<field>] exactly as the UI shows it.
_DIRECTIVES = r"""
import org.jenkinsci.plugins.structs.describable.DescribableModel
import groovy.json.JsonOutput
def j = jenkins.model.Jenkins.get()
def pm = j.pluginManager
def cats = [triggers: 'hudson.triggers.TriggerDescriptor', options: 'hudson.model.JobPropertyDescriptor',
            options2: 'org.jenkinsci.plugins.pipeline.modeldefinition.options.DeclarativeOptionDescriptor',
            parameters: 'hudson.model.ParameterDefinition$ParameterDescriptor',
            when: 'org.jenkinsci.plugins.pipeline.modeldefinition.when.DeclarativeStageConditionalDescriptor',
            agent: 'org.jenkinsci.plugins.pipeline.modeldefinition.agent.DeclarativeAgentDescriptor']
def res = []
cats.each { cat, cls ->
  j.getExtensionList(j.pluginManager.uberClassLoader.loadClass(cls)).each { d ->
    def sym = d.getClass().getAnnotation(org.jenkinsci.Symbol)
    if (!sym) return
    def p = pm.whichPlugin(d.getClass())
    def params = []
    try { DescribableModel.of(d.clazz).parameters.each { pp -> params << [name: pp.name, type: (pp.rawType?.simpleName ?: pp.type.toString()), required: pp.required] } } catch (Throwable t) {}
    res << [category: cat.replace('2', ''), symbol: sym.value()[0], id: d.id, plugin: p?.shortName ?: 'core',
            version: p?.version ?: jenkins.model.Jenkins.VERSION, displayName: d.displayName, params: params]
  }
}
println JsonOutput.toJson(res)
"""


# --------------------------------------------------------------------------- controller step reference
def _type_of(dd) -> str:
    for div in dd.find_all("div", recursive=False):
        strong = None if div.get("class") else div.find("strong", recursive=False)
        if strong and strong.get_text(strip=True) == "Type:":
            return div.get_text(" ", strip=True).replace("Type:", "").strip()
    return ""


def _help_text(node) -> str:
    helps = [h for h in node.find_all("div", class_="help", recursive=False)]
    return "\n\n".join(html_to_md(str(h)).strip() for h in helps if h.get_text(strip=True))


def _params(dd, depth: int = 0) -> list[str]:
    """Render the mandatory/optional parameter lists of a step (or nested object) as Markdown bullets."""
    out: list[str] = []
    for dl in dd.find_all("dl", class_="help-list", recursive=False):
        optional = "optional" in dl.get("class", [])
        for dt in dl.find_all("dt", class_="help-title", recursive=False):
            body = dt.find_next_sibling("dd")
            name = dt.code.get_text(strip=True) if dt.code else dt.get_text(strip=True)
            kind = _type_of(body) if body else ""
            line = f"- `{name}`" + (" (optional)" if optional else "") + (f": {kind}" if kind else "")
            out.append(line)
            if body is None:
                continue
            text = _help_text(body)
            if text:
                out.append(indent(text, "  "))
            out += [indent(x, "  ") for x in _nested(body, depth + 1)]
    return out


def _nested(body, depth: int) -> list[str]:
    out: list[str] = []
    for child in body.find_all(recursive=False):
        classes = child.get("class", [])
        if "values-box" in classes:
            vals = [c.get_text(strip=True) for c in child.select("div.value code")]
            out.append("Values: " + ", ".join(f"`{v}`" for v in vals))
        elif "array-list-box" in classes:
            inner = child.select_one("div.array-list")
            out.append("Array/List of:")
            if inner:
                out += _nested(inner, depth)
        elif child.name == "dl" and "nested-object-box" in classes:
            dd = child.find("dd", recursive=False)
            if dd and depth < 6:
                out += _params(dd, depth)
        elif child.name == "dl" and "nested-choice-box" in classes:
            schema = child.select_one("dd > dl.schema")
            if not schema:
                continue
            choices = schema.find_all("dt", recursive=False)
            out.append("One of: " + ", ".join(f"`{c.get_text(strip=True)}`" for c in choices))
            if depth < 4:
                for c in choices:
                    dd = c.find_next_sibling("dd")
                    sub = _params(dd, depth) if dd else []
                    if sub:
                        out.append(f"- `{c.get_text(strip=True)}`")
                        out += [indent(x, "  ") for x in sub]
        elif child.name == "pre":
            out.append("```\n" + child.get_text().strip() + "\n```")
    return out


def _plugin_map(jenkins) -> dict[str, tuple[str, str]]:
    out = {}
    for line in jenkins.script(_PLUGIN_MAP).splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            out.setdefault(parts[0], (parts[1], parts[2]))
    return out


def installed_plugins(jenkins) -> dict[str, str]:
    plugins = jenkins.s.get(f"{jenkins.base}/pluginManager/api/json?tree=plugins[shortName,version]",
                            timeout=30).json()["plugins"]
    return {p["shortName"]: p["version"] for p in plugins}


def default_label(core: str, plugins: dict[str, str]) -> str:
    """``<core>+p<8 hex>``: controllers on the same core with different plugin sets get different bundles."""
    digest = hashlib.sha256("\n".join(f"{k}:{v}" for k, v in sorted(plugins.items())).encode()).hexdigest()
    return f"{core}+p{digest[:8]}"


def fetch_controller(bundle: Bundle, jenkins, plugins: dict[str, str] | None = None) -> None:
    """Steps + globals for the running controller's exact plugin set."""
    from bs4 import BeautifulSoup

    version = jenkins.s.get(f"{jenkins.base}/api/json", timeout=10).headers.get("X-Jenkins", "unknown")
    bundle.components.update({"jenkins": version, **(installed_plugins(jenkins) if plugins is None else plugins)})
    owners = _plugin_map(jenkins)

    html = jenkins.s.get(f"{jenkins.base}/pipeline-syntax/html", timeout=120).text
    ref = BeautifulSoup(html, "html.parser").select_one("div.dsl-reference")
    if ref is None:
        raise SystemExit("unexpected /pipeline-syntax/html layout (no div.dsl-reference)")
    for box in ref.select("div.steps-box"):
        advanced = "advanced" in box.get("class", [])
        for dt in box.select("dl.steps.root > dt.step-title"):
            name = dt.code.get_text(strip=True)
            title = dt.get_text(" ", strip=True).split(":", 1)[-1].strip()
            dd = dt.find_next_sibling("dd")
            plugin, pver = owners.get(name, ("", ""))
            url = STEP_DOC_URL.format(plugin=plugin or "core", anchor=name.lower())
            parts = [f"Plugin: `{plugin}` {pver}" if plugin else "Plugin: (not a StepDescriptor - see symbol)",
                     ("Advanced/deprecated step." if advanced else "")]
            desc = _help_text(dd)
            params = _params(dd)
            body = "\n\n".join(p for p in parts if p)
            body += "\n\n" + (desc or "(no description)")
            body += "\n\n## Parameters\n\n" + ("\n".join(params) if params else "(none)")
            bundle.write(f"steps/{slug(name)}.md", name, f"**{title}**\n\n" + body, url,
                         "Advanced/deprecated steps" if advanced else "Steps",
                         f"{title} - {plugin} {pver}" if plugin else title)

    _globals(bundle, jenkins, BeautifulSoup)
    _directives(bundle, jenkins)
    plugin_lines = [f"- `{k}` {v}" for k, v in sorted(bundle.components.items())]
    bundle.write("plugins.md", "Installed core and plugin versions", "\n".join(plugin_lines),
                 f"{jenkins.base}/pluginManager/", "Versions", "exact versions the step reference was generated from")


def _directives(bundle: Bundle, jenkins) -> None:
    """Installed Declarative directive symbols with core/plugin help at the installed versions."""
    import json

    def help_md(path: str) -> str:
        r = jenkins.s.get(f"{jenkins.base}{path}", timeout=30)
        return html_to_md(r.text).strip() if r.status_code == 200 and r.text.strip() else ""

    seen = set()  # a symbol listed under two descriptor types; the installed page replaces a kept latest-release one
    for d in json.loads(jenkins.script(_DIRECTIVES)):
        cat, sym = d["category"], d["symbol"]
        rel = f"declarative/{cat}/{slug(sym)}.md"
        if rel in seen:
            continue
        seen.add(rel)
        parts = [f"**{d['displayName']}**", f"Plugin: `{d['plugin']}` {d['version']} (installed in the harness controller)"]
        desc = help_md(f"/descriptor/{d['id']}/help")
        if desc:
            parts.append(desc)
        params = []
        for prm in d["params"]:
            kind = prm["type"] if len(prm["type"]) <= 80 else prm["type"][:77] + "..."
            line = f"- `{prm['name']}`" + ("" if prm["required"] else " (optional)") + f": {kind}"
            text = help_md(f"/descriptor/{d['id']}/help/{prm['name']}")
            params.append(line + ("\n" + indent(text) if text else ""))
        parts.append("## Parameters\n\n" + ("\n".join(params) if params else "(none)"))
        bundle.write(rel, f"{cat} `{sym}`", "\n\n".join(parts),
                     f"https://www.jenkins.io/doc/book/pipeline/syntax/#{cat}", f"Declarative {cat} (installed)",
                     f"{d['displayName']} - {d['plugin']} {d['version']}", index="declarative/INDEX.md")


def _globals(bundle: Bundle, jenkins, BeautifulSoup) -> None:
    html = jenkins.s.get(f"{jenkins.base}/pipeline-syntax/globals", timeout=60).text
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("#main-panel") or soup
    for dt in main.select("dl.root > dt") or []:
        name = dt.get_text(strip=True)
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        body = html_to_md(str(dd))
        first = next((ln for ln in body.splitlines() if ln.strip() and not ln.startswith("#")), "")
        bundle.write(f"globals/{slug(name)}.md", f"Global variable `{name}`", body,
                     "https://www.jenkins.io/doc/book/pipeline/getting-started/#global-variable-reference",
                     "Global variables", first[:120])


# --------------------------------------------------------------------------- jenkins.io handbook
def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def fetch_handbook(bundle: Bundle, ref: str = "master", cps_version: str | None = None) -> str:
    """Sparse, blob-filtered checkout of the handbook chapters at ``ref``; returns the resolved commit SHA."""
    repo = docs_dir() / ".src" / "jenkins.io"
    if not (repo / ".git").is_dir():
        repo.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", JENKINS_IO_REPO, str(repo))
    _git("sparse-checkout", "set", "--no-cone", *[f"/{p}/**" for p in HANDBOOK_PATHS], cwd=repo)
    _git("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", ref, cwd=repo)
    _git("checkout", "-q", "--detach", "FETCH_HEAD", cwd=repo)
    sha = _git("rev-parse", "HEAD", cwd=repo)
    for prefix in HANDBOOK_PATHS:
        for f in sorted((repo / prefix).rglob("*.adoc")):
            rel = f.relative_to(repo / "content")  # doc/book/pipeline/syntax.adoc
            url_path = "/" + str(rel.with_suffix("")).removesuffix("/index") + "/"
            title, md = adoc_to_md(f.read_text(encoding="utf-8"), "https://www.jenkins.io" + url_path)
            out = "handbook/" + str(rel.relative_to("doc").with_suffix(".md")).removeprefix("book/").replace(
                "pipeline/tour/", "tour/")
            first = next((ln for ln in md.splitlines() if ln and not ln.startswith(("#", ">", "<", "-", "`"))), "")
            bundle.write(out, title or rel.stem, md, f"https://www.jenkins.io{url_path} @ {sha[:12]}",
                         "Handbook (jenkins.io)", first[:110])
    bundle.origin["handbook"] = f"{JENKINS_IO_REPO}/tree/{sha}/content/doc"
    bundle.components["jenkins.io"] = sha
    if cps_version:
        _cps_docs(bundle, cps_version)
    return sha


def _cps_docs(bundle: Bundle, version: str) -> None:
    """workflow-cps ``doc/*.md`` (CPS transformation, sandbox, persistence) at the installed release tag."""
    from ..github import GitHub

    try:
        listing = GitHub().get("/repos/jenkinsci/workflow-cps-plugin/contents/doc", params={"ref": version})
    except Exception as e:  # noqa: BLE001 - optional extra; never fail the bundle for it
        print(f"[docs] skipping workflow-cps docs: {e}", file=sys.stderr)
        return
    for item in listing:
        if not item["name"].endswith(".md"):
            continue
        text = requests.get(item["download_url"], timeout=30).text
        title = next((ln.lstrip("# ") for ln in text.splitlines() if ln.startswith("#")), item["name"])
        body = "\n".join(ln for ln in text.splitlines() if ln.lstrip("# ") != title or not ln.startswith("#"))
        bundle.write(f"handbook/cps/{item['name']}", f"{title} (workflow-cps)", body, item["html_url"],
                     "Scripted Pipeline internals (workflow-cps)", f"workflow-cps {version}")


# --------------------------------------------------------------------------- reports.jenkins.io (latest plugins)
def _report_zip(bundle: Bundle, name: str) -> zipfile.ZipFile:
    r = requests.get(f"{REPORTS}/{name}", timeout=300)
    r.raise_for_status()
    bundle.components[f"reports.jenkins.io/{name}"] = (f"{r.headers.get('Last-Modified', '')} "
                                                       f"etag {r.headers.get('ETag', '')}").strip()
    return zipfile.ZipFile(io.BytesIO(r.content))


def fetch_declarative(bundle: Bundle) -> None:
    z = _report_zip(bundle, "declarative.zip")
    for name in sorted(z.namelist()):
        if not name.endswith(".adoc"):
            continue
        directive = Path(name).stem
        _, sections = report_sections(z.read(name).decode("utf-8"))
        plugin, seen = "", set()
        for heading, body in sections:
            if not heading.startswith("`"):
                continue
            symbol = heading.split("`")[1]
            plugin = body.split("](https://plugins.jenkins.io/", 1)[1].split(")", 1)[0] if "plugins.jenkins.io/" in body \
                else plugin
            key = symbol if symbol not in seen else f"{symbol}-{plugin}"
            seen.add(symbol)
            if (bundle.path / f"declarative/{directive}/{slug(key)}.md").exists():
                continue  # the controller already documented its installed version
            bundle.write(f"declarative/{directive}/{slug(key)}.md", f"{directive} {heading}", body,
                         f"https://www.jenkins.io/doc/book/pipeline/syntax/#{directive}",
                         f"Declarative {directive} (other plugins, latest release)",
                         heading.split(":", 1)[-1].strip()[:100] + (f" - {plugin}" if plugin else ""),
                         index="declarative/INDEX.md")


def fetch_plugins(bundle: Bundle) -> None:
    """One page per plugin; ``plugins/INDEX.md`` maps every step symbol to its plugin page."""
    z = _report_zip(bundle, "allAscii.zip")
    index = ["# Pipeline steps of all Jenkins plugins (latest releases)", "",
             "> reports.jenkins.io/allAscii.zip. Grep for a step as `` `stepName` `` to find its plugin page.", ""]
    for name in sorted(z.namelist()):
        if not name.endswith(".adoc") or "/" in name:
            continue
        plugin = Path(name).stem
        title, sections = report_sections(z.read(name).decode("utf-8"))
        steps = [h.split("`")[1] for h, _ in sections if h.startswith("`")]
        body = "\n\n".join((f"## {h}\n\n{b}" if h.startswith("`") else b) for h, b in sections
                           if h != title).strip()
        rel = f"plugins/{slug(plugin)}.md"
        target = bundle.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {title or plugin}\n\n> Source: https://www.jenkins.io/doc/pipeline/steps/{plugin}/ "
                          f"(latest plugin release, reports.jenkins.io)\n\n{body}\n", encoding="utf-8")
        index.append(f"- [{title or plugin}]({slug(plugin)}.md): " + ", ".join(f"`{s}`" for s in steps))
        bundle.pages.append(Page(rel, title or plugin, "Steps of plugins not installed in the controller", index="",
                                 part=bundle.part))  # listed by plugins/INDEX.md, not the bundle index
    (bundle.path / "plugins" / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    bundle.pages.append(Page("plugins/INDEX.md", "All plugins' steps (latest releases)",
                             "Steps of plugins not installed in the controller",
                             f"{len(index) - 4} plugins; find which plugin provides a step, then open its page",
                             part=bundle.part))


def controller_client():
    """The harness controller (started if needed) and its Jenkins version."""
    from ..jenkins import controller

    j = controller.Jenkins()
    if not j.available():
        print("[docs] starting the harness Jenkins controller (j2gha jenkins up)", file=sys.stderr)
        j = controller.up()
    return j, j.s.get(f"{j.base}/api/json", timeout=10).headers.get("X-Jenkins", "unknown")


def fetch(parts: tuple[str, ...] = PARTS, ref: str = "master", version: str | None = None,
          label: str | None = None) -> Bundle:
    """Build ``.docs/jenkins/<label>``: the reference of the *running* harness controller.

    ``label`` defaults to ``<core>+p<plugin-set digest>``, or ``latest`` when the controller part is skipped.
    ``version`` is the core version the caller expects; the bundle can only document the running controller, so a
    different one is refused (a value that is not a version number is taken as ``label``, as before ``--label``).
    Fetching some parts onto an existing bundle keeps its other parts. A controller fetch under the default label
    becomes the default Jenkins bundle."""
    unknown = sorted(set(parts) - set(PARTS))
    if unknown:
        raise SystemExit(f"unknown jenkins docs parts {', '.join(unknown)} (choose from {', '.join(PARTS)})")
    if version and not _VERSION.fullmatch(version):
        label, version = label or version, None
    label = label and version_label("jenkins", label)  # before starting the controller
    j = core = ident = None
    plugins: dict[str, str] = {}
    if "controller" in parts:
        j, core = controller_client()
        plugins = installed_plugins(j)
        ident = default_label(core, plugins)
    claim = _IDENTITY.fullmatch(label or "")
    if (version and version != core) or (j is not None and claim and label not in (core, ident)):
        raise SystemExit(
            f"--{'version' if version else 'label'} {version or label}: a Jenkins bundle documents the running "
            + (f"harness controller, which is {ident}" if j is not None else
               "harness controller, and --parts skips it so it can't be checked")
            + ". To document another Jenkins, change J2GHA_JENKINS_BASE / docker/jenkins/plugins.txt and rebuild the "
            "controller; to name the bundle, use a --label that is not a version number.")
    label = label or ident or "latest"
    bundle = Bundle("jenkins", label, f"Jenkins documentation - {label}",
                    "Version-exact step/global reference from the harness controller (steps/, globals/, "
                    "plugins.md); jenkins.io handbook pinned by commit (handbook/); Declarative directives and "
                    "steps of all plugins at their latest release (declarative/INDEX.md, plugins/INDEX.md). Prefer "
                    "steps/ for anything the controller has installed; fall back to plugins/ for other plugins.",
                    licence="jenkins.io content CC BY-SA 4.0; plugin help texts under each plugin's licence (mostly MIT)")
    with bundle.staged(parts):
        # kept parts keep their provenance; the parts fetched now record theirs afresh
        bundle.origin = {k: v for k, v in bundle.origin.items() if k not in parts}
        bundle.components = {k: v for k, v in bundle.components.items()
                             if COMPONENT_PARTS.get(k, "controller") not in parts}
        if j is not None:
            print(f"[docs] jenkins controller {core}: steps + globals", file=sys.stderr)
            bundle.part = "controller"
            bundle.origin["controller"] = f"{j.base}/pipeline-syntax/html"
            fetch_controller(bundle, j, plugins)
        if "handbook" in parts:
            print(f"[docs] jenkins.io handbook @ {ref}", file=sys.stderr)
            bundle.part = "handbook"
            fetch_handbook(bundle, ref, cps_version=bundle.components.get("workflow-cps"))
        if "declarative" in parts:
            print("[docs] reports.jenkins.io declarative.zip", file=sys.stderr)
            bundle.part = "declarative"
            bundle.origin["declarative"] = f"{REPORTS}/declarative.zip"
            fetch_declarative(bundle)
        if "plugins" in parts:
            print("[docs] reports.jenkins.io allAscii.zip (~40 s to convert)", file=sys.stderr)
            bundle.part = "plugins"
            bundle.origin["plugins"] = f"{REPORTS}/allAscii.zip"
            fetch_plugins(bundle)
        directives = ("agent", "options", "parameters", "triggers", "when")
        bundle.finish(["Steps", "Advanced/deprecated steps", "Global variables", "Versions", "Handbook (jenkins.io)",
                       "Scripted Pipeline internals (workflow-cps)",
                       *[f"Declarative {d} (installed)" for d in directives],
                       *[f"Declarative {d} (other plugins, latest release)" for d in directives],
                       "Steps of plugins not installed in the controller"], default=label == ident)
    return bundle
