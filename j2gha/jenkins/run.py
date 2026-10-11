"""Execute a (localised) Jenkinsfile on the disposable controller and capture a behaviour record."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

from ..analysis.declarative import build_ir
from ..provenance import sha256_text
from ..trace import parse_traces
from . import controller
from .localize import LOCALIZER_VERSION, localize, provisioning_script, repairs_from_errors, tool_installs

__all__ = ["LOCALIZER_VERSION", "run_jenkins"]

# Jenkins reports one missing property per build, and a stubbed helper can leave several unset (example 015: 3).
MAX_ATTEMPTS = 8


def log(msg: str) -> None:
    print(f"[jenkins] {msg}", file=sys.stderr, flush=True)


def run_jenkins(d: Path, mode: str, scenario: dict[str, Any], docker: bool = False) -> dict[str, Any]:
    with controller.exclusive(f"jenkins {mode} run of examples/{d.name}"):
        return _run_jenkins(d, mode, scenario, docker)


def _run_jenkins(d: Path, mode: str, scenario: dict[str, Any], docker: bool) -> dict[str, Any]:
    text = (d / "Jenkinsfile").read_text()
    ast = json.loads((d / "analysis" / "groovy-ast.json").read_text())
    analysis = json.loads((d / "analysis" / "analysis.json").read_text())
    # the localiser edits the Jenkinsfile by the AST's source ranges: they must describe this text
    if not ast.get("source_sha256") or {ast.get("source_sha256"), analysis.get("source_sha256")} != {sha256_text(text)}:
        raise RuntimeError(f"examples/{d.name}/analysis does not match the Jenkinsfile (changed since, or analysed "
                           f"before provenance tracking): run `j2gha analyze {d.name}` first")
    meta = json.loads((d / "source.json").read_text()) if (d / "source.json").exists() else {}
    ir = build_ir(ast)
    repo = meta.get("repository", {}).get("full_name")
    sha = meta.get("snapshot_commit") or meta.get("file_last_commit_sha")  # the commit the Jenkinsfile came from
    source = {"url": f"https://github.com/{repo}.git", "sha": sha} if repo else None
    j = controller.up(docker_socket=docker)
    if docker and not controller.docker_enabled():
        log("controller is running without the Docker socket; restart with `j2gha jenkins down` then --docker")
    j.set_global_env({"BRANCH_NAME": scenario.get("branch", "main"),
                      "GIT_BRANCH": scenario.get("git_branch", scenario.get("branch", "main"))})
    j.script("jenkins.model.Jenkins.get().setNumExecutors(16); println 'ok'")  # wide parallel fan-outs
    prov = j.script(provisioning_script(analysis.get("credentials", []), tool_installs(ir) if mode == "full" else [], text))
    log(f"{d.name}: {prov.strip()[:200]}")
    removes: list[tuple[str, str]] = []
    extra: list[str] = []
    job = f"ex-{d.name}-{mode}"
    has_params = bool(ir and ir.parameters)
    timeout = 600 if mode == "trace" else 1800
    attempts = []
    ineffective: list = []
    res = None
    loc = None

    def triage(r: list, s: list, current: str) -> tuple[list, list, list]:
        """New repairs/stubs split into those that change the localised script and those that would not, which are
        recorded as ineffective instead of being reported as applied while the build keeps failing (015's buildType)."""
        def changes(rem: list, stubs: list) -> bool:
            return localize(text, ast, analysis, mode, source=source, docker=docker, extra_stubs=stubs,
                            remove=rem).script != current
        new_r = [x for x in r if x not in removes]
        new_s = [x for x in s if x not in extra]
        eff_r = [x for x in new_r if changes(removes + [x], extra)]
        eff_s = [x for x in new_s if changes(removes, extra + [x])]
        noop = [x for x in new_r + new_s if x not in eff_r + eff_s]
        if noop:
            ineffective.extend(x for x in noop if x not in ineffective)
            log(f"{d.name}: auto-repair would not change the script, not applied: {noop}")
        return eff_r, eff_s, noop

    for attempt in range(MAX_ATTEMPTS):
        loc = localize(text, ast, analysis, mode, source=source, docker=docker, extra_stubs=extra, remove=removes)
        if analysis["dialect"] in ("declarative",):
            ok, msg = j.validate(loc.script)
            if not ok:
                new_r, new_s, noop = triage(*repairs_from_errors(msg), loc.script)
                attempts.append({"attempt": attempt, "phase": "validate", "errors": msg[:1500],
                                 "repairs": new_r, "stubs": new_s, **({"ineffective": noop} if noop else {})})
                if new_r or new_s:
                    removes += new_r
                    extra += new_s
                    log(f"{d.name}: auto-repair {new_r + new_s}")
                    continue
        scenario_params = scenario.get("params") or {}
        defined = xml_parameters(ir.parameters) if has_params else None
        j.upsert_pipeline_job(job, loc.script, description=f"j2gha {mode} run of examples/{d.name}", parameters=defined)
        started = time.time()
        if defined:
            # the job already defines its parameters: the one build is the requested scenario
            n = j.trigger(job, params={**param_defaults(ir.parameters), **scenario_params})
            res = j.wait(job, n, timeout=timeout)
        else:
            n = j.trigger(job)
            res = j.wait(job, n, timeout=timeout)
            if has_params and (scenario_params or not _build_has_params(j, job, n)) and "parameters" not in str(removes):
                # Declarative registers parameters during the first build, which therefore ran the pipeline with
                # its defaults: keep that build in the record, then run the requested scenario
                attempts.append({"attempt": attempt, "phase": "register", "build": n, "result": res.result,
                                 "note": "parameters could not be defined up front: this build ran with defaults"})
                log(f"{d.name}: parameters registered by a full default build #{n}; running the scenario next")
                n = j.trigger(job, params={**param_defaults(ir.parameters), **scenario_params})
                res = j.wait(job, n, timeout=timeout)
        new_r, new_s, noop = triage(*repairs_from_errors(res.console), loc.script)
        attempts.append({"attempt": attempt, "phase": "run", "build": n, "result": res.result,
                         "seconds": round(time.time() - started, 1), "repairs": new_r, "stubs": new_s,
                         **({"ineffective": noop} if noop else {})})
        if (new_r or new_s) and attempt < MAX_ATTEMPTS - 1:
            removes += new_r
            extra += new_s
            log(f"{d.name}: runtime auto-repair {new_r + new_s}")
            continue
        break
    out = d / "runs" / f"jenkins-{mode}"
    out.mkdir(parents=True, exist_ok=True)
    assert loc is not None
    (out / "Jenkinsfile.localized").write_text(loc.script)
    record: dict[str, Any] = {"tier": "jenkins", "mode": mode, "scenario": scenario,
                              "localisation": {"changes": loc.changes, "stubs": loc.stubs,
                                               "auto_repairs": {"removed": removes, "stubbed": extra,
                                                                "ineffective": ineffective}},
                              "attempts": attempts}
    if res is not None:
        (out / "console.log").write_text(res.console)
        record.update({"result": res.result, "build": res.number, "duration_ms": res.duration_ms,
                       "stages": res.stages, "traces": parse_traces(res.console),
                       "approved_inputs": res.approved_inputs,
                       "error_tail": _error_tail(res.console) if res.result != "SUCCESS" else None})
        if mode == "full":  # archived files and test results, compared with the converted run's (j2gha.outputs)
            try:
                record["outputs"] = j.build_outputs(job, res.number)
            except (requests.RequestException, ValueError) as e:
                record["outputs"] = {"archived": [], "tests": None, "problems": [f"Jenkins outputs unreadable: {e}"]}
    else:
        record.update({"result": "NOT_RUN", "traces": [], "stages": []})
    (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    log(f"{d.name}: jenkins {mode} -> {record['result']} ({len(record['traces'])} trace events)")
    return record


def xml_parameters(parameters: list) -> list[dict[str, Any]] | None:
    """The parameters as job-XML definitions, or None when any cannot be defined faithfully (an unsupported type, or a
    default Jenkins must evaluate itself): the pipeline then registers them by running once."""
    out = []
    for p in parameters:
        if p.kind in ("string", "text", "password") and p.default is not None:
            out.append({"name": p.name, "kind": p.kind, "default": p.default})
        elif p.kind == "booleanParam" and isinstance(p.default, bool):
            out.append({"name": p.name, "kind": p.kind, "default": p.default})  # None: absent or an expression
        elif p.kind == "choice" and p.choices:
            out.append({"name": p.name, "kind": p.kind, "choices": p.choices})
        else:
            return None
    return out or None


def param_defaults(parameters: list) -> dict[str, Any]:
    """Literal defaults (or the first choice) to build with. Parameters left out get their declared default, which
    Jenkins evaluates itself (defaultValue: "${cfg.stage}") - sending '' would override it."""
    return {p.name: str(p.default).lower() if isinstance(p.default, bool) else
            (p.default if p.default is not None else p.choices[0])
            for p in parameters if p.default is not None or p.choices}


def _build_has_params(j, job: str, number: int) -> bool:
    info = j.build_info(job, number)
    return any(a.get("_class", "").endswith("ParametersAction") for a in info.get("actions", []) if isinstance(a, dict))


def _error_tail(console: str, n: int = 12) -> str:
    lines = [ln for ln in console.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if "ERROR:" in ln or "Exception" in ln or "MultipleCompilationErrors" in ln:
            return "\n".join(lines[i:i + n])
    return "\n".join(lines[-n:])
