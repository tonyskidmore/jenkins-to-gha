"""Harness stages operating on examples/NNN: analyze -> convert -> validate -> run."""

from __future__ import annotations

import json
import os
import re
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis.analyze import analyse
from .analysis.ast import dump_sources
from .analysis.declarative import build_ir, find_pipeline_call
from .config import display_dir, example_dir, is_corpus
from .jenkins.localize import provisioning_script, tool_installs
from .provenance import sha256_json, sha256_text
from .readme import update_section
from .render import analysis_section, conversion_section, migration_report


def log(msg: str) -> None:
    print(f"[j2gha] {msg}", file=sys.stderr, flush=True)


def _meta(d: Path) -> dict[str, Any]:
    f = d / "source.json"
    # an example without a crawl citation (the examples/000 walkthrough, your own pipelines) is named after its directory
    return json.loads(f.read_text()) if f.exists() else {"id": d.name, "path": "Jenkinsfile",
                                                          "repository": {"full_name": display_dir(d)}}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")


def _jenkins_version(j) -> str:
    try:
        r = j.s.get(f"{j.base}/api/json", timeout=5)
        return r.headers.get("X-Jenkins", "?")
    except Exception:  # noqa: BLE001
        return "?"


def _declarative_source(text: str, ast: dict) -> str:
    """For shared-library templates validate just the pipeline {} block."""
    call, method = find_pipeline_call(ast)
    if call is None or method is None:
        return text
    lines = text.splitlines()
    return "\n".join(lines[call["line"] - 1: call["endLine"]])


# ------------------------------------------------------------------------------------------------- analyze
def analyze_examples(ids: list[str], use_jenkins: bool = True) -> None:
    dirs = {i: example_dir(i) for i in ids}
    texts = {i: (d / "Jenkinsfile").read_text() for i, d in dirs.items() if (d / "Jenkinsfile").exists()}
    log(f"parsing {len(texts)} Jenkinsfile(s) with Jenkins' Groovy")
    asts = dump_sources(texts)
    with ExitStack() as stack:
        jenkins = None
        jver = "?"
        if use_jenkins:
            from .jenkins import controller
            try:
                stack.enter_context(controller.exclusive("analyze"))  # provisions tools on the shared controller
                jenkins = controller.up()
                jver = _jenkins_version(jenkins)
            except Exception as e:  # noqa: BLE001
                log(f"Jenkins controller unavailable ({e}); continuing without the Declarative model")
                jenkins = None
        _analyze(dirs, texts, asts, jenkins, jver)


def _analyze(dirs: dict[str, Path], texts: dict[str, str], asts: dict[str, dict], jenkins, jver: str) -> None:
    env = {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "jenkins": jver, "groovy": "2.4.21"}
    for i, text in texts.items():
        d = dirs[i]
        ast = asts[i]
        ir = build_ir(ast)
        model = None
        if jenkins is not None and ast.get("ok"):
            try:
                # Declarative validation rejects `tools {}` names that have no matching installation
                if tools := tool_installs(ir):
                    jenkins.script(provisioning_script([], tools, text))
                model = jenkins.to_json(_declarative_source(text, ast))
            except Exception as e:  # noqa: BLE001
                log(f"{i}: toJson failed: {e}")
        a = analyse(text, ast, model)
        # later stages (convert, the Jenkins localiser) check these against the Jenkinsfile they read
        ast["source_sha256"] = a["source_sha256"] = sha256_text(text)
        out = d / "analysis"
        _write_json(out / "groovy-ast.json", ast)
        if model is not None:
            _write_json(out / "jenkins-model.json", model)
        _write_json(out / "ir.json", ir.to_dict() if ir else None)
        _write_json(out / "analysis.json", a)
        update_section(d / "README.md", "analysis", analysis_section(a, ir, env))
        log(f"{i}: {a['dialect']:<16} difficulty {a['complexity']['score']:>3} ({a['complexity']['classification']}), "
            f"coverage {a['coverage']['weighted_mapped_pct']}%, convertibility {a['convertibility']}")


# ------------------------------------------------------------------------------------------------- convert
def load_ir(d: Path):
    """IR of the current Jenkinsfile: the saved AST only if it was parsed from this text, otherwise a fresh parse."""
    from .analysis.ast import dump_source

    text = (d / "Jenkinsfile").read_text()
    ast_file = d / "analysis" / "groovy-ast.json"
    ast = json.loads(ast_file.read_text()) if ast_file.exists() else None
    if ast is None or ast.get("source_sha256") != sha256_text(text):
        ast = dump_source(text)
        ast["source_sha256"] = sha256_text(text)
    return build_ir(ast), ast


# Generated from the conversion: removed when an example is no longer converted, so no stage uses a stale workflow
GHA_OUTPUTS = ("workflow.yml", "workflow.model.json", "conversion.json", "migration-report.md", "validation.json")


def convert_examples(ids: list[str]) -> None:
    from .convert.generator import convert, github_resolver, pin_actions, to_yaml

    resolver = github_resolver()

    for i in ids:
        d = example_dir(i)
        text = (d / "Jenkinsfile").read_text()
        analysis_file = d / "analysis" / "analysis.json"
        if not analysis_file.exists() or json.loads(analysis_file.read_text()).get("source_sha256") != sha256_text(text):
            log(f"{i}: analysis missing or older than the Jenkinsfile - re-analysing")
            analyze_examples([i], use_jenkins=False)
        analysis = json.loads(analysis_file.read_text())
        ir, _ = load_ir(d)
        meta = _meta(d)
        gha = d / "gha"
        if ir is None or analysis["convertibility"] == "report-only":
            removed = [f for f in GHA_OUTPUTS if (gha / f).exists()]
            for f in removed:
                (gha / f).unlink()
            update_section(d / "README.md", "conversion",
                           "### Conversion\n\nNot converted: the pipeline is "
                           f"`{analysis['dialect']}` (convertibility `report-only`); see the analysis findings.")
            update_section(d / "README.md", "validation", "### Static validation\n\n_Not converted._")
            log(f"{i}: report-only ({analysis['dialect']}), skipped"
                + (f"; removed the earlier conversion ({', '.join(removed)})" if removed else ""))
            continue
        title = f"{meta.get('repository', {}).get('full_name', 'example')} {meta.get('path', '')}".strip()
        result = convert(ir, text, title=f"j2gha {i}: {title}"[:100])
        gha.mkdir(exist_ok=True)
        url = f" ({meta['file_url']})" if meta.get("file_url") else ""
        header = (f"# Generated by j2gha from {display_dir(d)}/Jenkinsfile{url}\n"
                  f"# Classification: {analysis['complexity']['classification']} "
                  f"(difficulty {analysis['complexity']['score']}/100); automation {result['report']['automation_pct']}%\n"
                  "# Review gha/migration-report.md before use.\n")
        pins = pin_actions(result["workflow"], resolver)
        yml = to_yaml(result["workflow"], header, pins)
        old = gha / "workflow.yml"
        if old.exists() and old.read_text() != yml and (gha / "validation.json").exists():
            (gha / "validation.json").unlink()  # validated another workflow
            update_section(d / "README.md", "validation",
                           "### Static validation\n\n_Not validated since the last conversion: run `j2gha validate`._")
        old.write_text(yml)
        _write_json(gha / "workflow.model.json", result["workflow"])
        result["report"]["source_sha256"] = sha256_text(text)
        result["report"]["model_sha256"] = sha256_json(result["workflow"])
        _write_json(gha / "conversion.json", result["report"])
        (gha / "migration-report.md").write_text(migration_report(meta, analysis, result["report"], ir))
        update_section(d / "README.md", "conversion", conversion_section(result["report"], "gha/workflow.yml"))
        c = result["report"]["counts"]
        log(f"{i}: {len(result['workflow']['jobs'])} job(s); mapped {c.get('mapped', 0)}, approx "
            f"{c.get('approximated', 0)}, manual {c.get('manual', 0)} -> automation {result['report']['automation_pct']}%")


# ------------------------------------------------------------------------------------------------- validate
def validate_examples(ids: list[str]) -> int:
    return 1 if validation_failures(ids) else 0


def validation_failures(ids: list[str]) -> list[str]:
    """Validate the converted workflows; returns the ids whose workflow failed (structure, policy or a scanner)."""
    from .validate.static import validate_example

    failed = []
    for i in ids:
        d = example_dir(i)
        if not (d / "gha" / "workflow.yml").exists():
            log(f"{i}: no workflow (not converted)")
            continue
        if not validate_example(d)["ok"]:
            failed.append(i)
    return failed


# ------------------------------------------------------------------------------------------------- run
# `j2gha run` / `pipeline` exit status
EXIT_OK, EXIT_ERROR, EXIT_DIFFERS, EXIT_REFUSED = 0, 1, 2, 3
REMOTE_TIERS = ("selfhosted", "hosted")


def remote_refusal(d: Path) -> str | None:
    """Why the remote tiers may not run this pipeline, or None.

    They push the converted workflow (stage names, commands) to J2GHA_REPO, by default this clone's origin: a public
    repository. Corpus examples are public already; any other pipeline is pushed only to a repository named in
    J2GHA_REPO that GitHub reports as private (or internal)."""
    if is_corpus(d):
        return None
    repo = os.environ.get("J2GHA_REPO")
    if not repo:
        return ("not a public corpus example, and the remote tiers push its converted workflow to J2GHA_REPO "
                "(default: this clone's origin); set J2GHA_REPO=owner/repo to a private repository you control")
    from .github import GitHub

    try:
        info = GitHub().request("GET", f"/repos/{repo}", use_cache=False)
    except Exception as e:  # noqa: BLE001
        return f"cannot confirm that J2GHA_REPO={repo} is private ({e})"
    if not info.get("private"):
        return f"J2GHA_REPO={repo} is {info.get('visibility', 'public')}; use a private repository you control"
    return None


def run_examples(ids: list[str], tiers: list[str], mode: str = "trace", docker_socket: bool = False,
                 yes: bool = False, max_minutes: int | None = None, branch: str | None = None,
                 fail_on_differs: bool = False, params: dict[str, str] | None = None,
                 allow_edited_model: bool = False, environments: bool = False) -> int:
    """Exit status: 1 when a tier failed to produce a result (error, timeout, Jenkins NOT_RUN), else 3 when a
    hosted run was refused, else 2 when `fail_on_differs` and a comparison differed or was inconclusive, else 0.
    A converted workflow that runs and fails is a result, not an error: the comparison judges it."""
    from .runners.execute import run_example

    errors, refused, differs = [], [], []
    remote = [t for t in tiers if t in REMOTE_TIERS]
    for i in ids:
        d, run_tiers = example_dir(i), tiers
        if remote and (why := remote_refusal(d)):
            log(f"{i}: {', '.join(remote)} refused: {why}")
            refused += [f"{i} {t}" for t in remote]
            run_tiers = [t for t in tiers if t not in REMOTE_TIERS]
            if not run_tiers:
                continue
        try:
            res = run_example(d, tiers=run_tiers, mode=mode, docker_socket=docker_socket, yes=yes,
                              max_minutes=max_minutes, branch=branch, params=params,
                              allow_edited_model=allow_edited_model, environments=environments)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"{i}: run failed: {e}")
            errors.append(i)
            continue
        statuses = res.get("statuses", {})
        errors += [f"{i} {t}" for t, st in statuses.items() if st == "infra"]
        refused += [f"{i} {t}" for t, st in statuses.items() if st == "refused"]
        differs += [f"{i} {t} ({v})" for t, v in res.get("verdicts", {}).items() if v != "equivalent"]
    for what, items in (("no result (error/timeout/not run)", errors), ("refused", refused),
                        ("not equivalent", differs)):
        if items:
            log(f"{what}: {', '.join(items)}")
    if errors:
        return EXIT_ERROR
    if refused:
        return EXIT_REFUSED
    return EXIT_DIFFERS if fail_on_differs and differs else EXIT_OK



# ------------------------------------------------------------------------------------------------- summary
def _validation_cell(val: dict[str, Any]) -> str:
    if not val:
        return "-"
    return ("✅" if val.get("ok") else "❌") + (" ⚠️" if val.get("security_ok") is False else "")



def summarize_examples() -> Path:
    """Write examples/README.md: one row per example across every harness stage."""
    from .config import EXAMPLES_DIR, list_example_ids

    def load(p: Path):
        return json.loads(p.read_text()) if p.exists() else None

    rows = []
    from .runners.execute import stale_reason

    totals = {"equivalent": 0, "inconclusive": 0, "compared": 0, "stale": 0}
    for i in list_example_ids():
        d = EXAMPLES_DIR / i
        meta = _meta(d)
        a = load(d / "analysis" / "analysis.json") or {}
        conv = load(d / "gha" / "conversion.json") or {}
        val = load(d / "gha" / "validation.json") or {}
        jen = load(d / "runs" / "jenkins-trace" / "result.json") or {}
        cells = []
        for tier in ("act", "selfhosted", "hosted"):
            r = load(d / "runs" / f"{tier}-trace" / "result.json")
            if r and r.get("comparison"):
                c = r["comparison"]
                sim = f" {c['similarity_pct']}%" if c.get("similarity_pct") is not None else ""
                if stale_reason(d, r, tier) or stale_reason(d, jen, "jenkins"):
                    totals["stale"] += 1
                    cells.append(f"{tier}: ⏸️ stale")
                    continue
                totals["compared"] += 1
                totals["equivalent"] += int(c["equivalent"])
                inconclusive = c.get("verdict") == "inconclusive"
                totals["inconclusive"] += int(inconclusive)
                cells.append(f"{tier}: {'✅' if c['equivalent'] else '⚠️' if inconclusive else '❌'}{sim}")
        repo = meta.get("repository", {})
        cx = a.get("complexity", {})
        original = (meta.get("derived_from") or {}).get("example")
        twin = f"<br>twin of [{original}]({original}/README.md)" if original else ""
        rows.append(
            f"| [{i}]({i}/README.md){twin} | [{repo.get('full_name', '?')}]({meta.get('file_url', '')}) | "
            f"{meta.get('score', {}).get('total', '-')} | `{meta.get('primary_style', '-')}` | `{a.get('dialect', '-')}` | "
            f"{cx.get('score', '-')} {cx.get('classification', '')} | {conv.get('automation_pct', '-')}% | "
            f"{_validation_cell(val)} | {jen.get('result', '-')} | {'<br>'.join(cells) or '-'} |")
    out = EXAMPLES_DIR / "README.md"
    out.write_text("\n".join([
        "# Example corpus",
        "",
        "Real-world Jenkins pipelines collected by the `jenkins-example-crawler` skill (`uv run j2gha crawl --count N`),",
        "each with a citation, a 0-10 score and the results of every harness stage. Regenerate this index with",
        "`uv run j2gha summary`.",
        "",
        "Examples below 100 are the crawled originals: each cited Jenkinsfile as published, never edited. `1NN`, marked",
        "*twin of* `0NN`, is a minimally edited copy of that original, made so that the pipeline runs to completion on the",
        "harness's local Jenkins (most originals need private services, credentials or other nodes); every edit is listed",
        "in its `LOCAL.md`. Twins exist for full mode, which runs the real commands and compares the outcome with a",
        "successful Jenkins run: see [docs/results.md](../docs/results.md#twins-full-mode-against-a-successful-jenkins-reference).",
        "",
        "| Example | Source | Score | Primary style | Dialect | Difficulty (0-100) | Automation | Static validation | "
        "Jenkins (trace) | Converted vs Jenkins (trace) |",
        "|---|---|---:|---|---|---|---:|---|---|---|",
        *rows,
        "",
        f"Trace equivalence: {totals['equivalent']}/{totals['compared']} tier runs equivalent to the Jenkins reference"
        + (f"; {totals['inconclusive']} inconclusive (⚠️: the traces cannot decide - e.g. Jenkins stopped on the "
           "pipeline's own error(), decided by values trace mode stubs; see the example's README)"
           if totals["inconclusive"] else "")
        + (f"; {totals['stale']} stale (⏸️: recorded for an earlier Jenkinsfile or conversion, not counted)"
           if totals["stale"] else "") + ".",
        "",
        "Trace equivalence is control-flow fidelity: the same stages run the same kinds of steps in the same order. "
        "It does not show that the commands, their outputs or the artifacts are equivalent (full mode compares the "
        "outcome of real runs), and covers only the scenario that was run: `equivalent` means no difference was "
        "found, not that the conversion is correct. Automation is an effort estimate (report items weighted by "
        "status), not a measure of correctness. Static validation: ✅/❌ actionlint + j2gha policy (a scanner that fails to run is ❌); "
        "⚠️ marks zizmor security findings.",
        "",
    ]))
    log(f"wrote {out}")
    return out


# ------------------------------------------------------------------------------------------------- add
PIPELINE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def pipeline_name(src: Path) -> str:
    """Default name for a pipeline added from `src`: its directory for a `Jenkinsfile`, else directory and file name
    (`payments/Jenkinsfile.deploy` -> `payments-jenkinsfile-deploy`). Never all digits: those are corpus ids."""
    stem = src.parent.name if src.name == "Jenkinsfile" else f"{src.parent.name}-{src.name}"
    name = re.sub(r"[^a-z0-9_]+", "-", stem.lower()).strip("-_") or "pipeline"
    return f"p-{name}" if name.isdigit() else name


def add_pipeline(src: Path, name: str | None = None, force: bool = False) -> Path:
    """Copy a Jenkinsfile (any file name) in as `<pipelines dir>/<name>/Jenkinsfile`; returns the directory.

    The pipelines directory is J2GHA_PIPELINES_DIR, or the clone's examples/ when that is unset (with a warning:
    examples/ is tracked and this repository is public)."""
    from . import config

    src = src.expanduser()
    if src.is_dir():
        src = src / "Jenkinsfile"
    if not src.is_file():
        raise ValueError(f"{src}: no such file (give the path of a Jenkinsfile, whatever its name)")
    name = name or pipeline_name(src.resolve())
    if not PIPELINE_NAME.fullmatch(name) or name.isdigit():
        raise ValueError(f"{name!r}: a pipeline name is letters, digits, '-' and '_', starts with a letter or digit "
                         "and is not all digits (numbers are corpus ids)")
    own = config.pipelines_dir()
    d = (own or config.EXAMPLES_DIR) / name
    target, text = d / "Jenkinsfile", src.read_text()
    if target.exists() and target.read_text() != text and not force:
        raise ValueError(f"{target} exists with other content (--force replaces it; later stages see the change and "
                         "re-analyse)")
    d.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    log(f"{name}: {src} -> {target}")
    if own is None:
        log(f"warning: {d} is inside this clone, and examples/ is tracked in a public repository. For a pipeline that "
            "is not public, set J2GHA_PIPELINES_DIR to a directory outside the clone (docs/own-pipelines.md)")
    return d
