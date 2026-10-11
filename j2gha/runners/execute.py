"""Run an example through one or more execution tiers and compare behaviour against the Jenkins reference."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..convert.generator import to_yaml
from ..jenkins.localize import LOCALIZER_VERSION
from ..gha.environments import compare as compare_environments
from ..outputs import act_outputs, compare_outputs
from ..outputs import summary as output_summary
from ..provenance import jenkinsfile_sha256, sha256_json
from ..readme import update_section
from ..analysis.declarative import build_ir
from ..trace import compare, concurrent_stages, outcome, stage_order, step_name_key
from .variants import estimate_minutes, make_variant

TIER_ORDER = ["jenkins", "act", "selfhosted", "hosted"]


def log(msg: str) -> None:
    print(f"[run] {msg}", file=sys.stderr, flush=True)


def _load(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else None


def scenario_for(meta: dict[str, Any], branch: str | None = None,
                 params: dict[str, str] | None = None) -> dict[str, Any]:
    """The build context both sides are pinned to (Jenkins global env / GHA workflow env). ``params`` overrides
    declared parameters on both sides; it is part of the scenario, so a reference run with other values is refused."""
    branch = branch or (meta.get("repository") or {}).get("default_branch") or "main"
    # GIT_BRANCH as the git plugin reports it for a non-multibranch job
    scenario: dict[str, Any] = {"branch": branch, "git_branch": f"origin/{branch}"}
    if params:
        scenario["params"] = {k: str(v) for k, v in sorted(params.items())}
    return scenario


def run_status(rec: dict[str, Any]) -> str:
    """ran | refused | skipped | infra (the tier did not produce a result to compare: error, timeout, NOT_RUN)."""
    result = rec.get("result")
    if result in ("refused", "skipped"):
        return result
    return "ran" if outcome(result) != "infra" and not rec.get("error") else "infra"


def run_example(d: Path, tiers: list[str], mode: str = "trace", docker_socket: bool = False, yes: bool = False,
                max_minutes: int | None = None, branch: str | None = None,
                params: dict[str, str] | None = None, allow_edited_model: bool = False,
                environments: bool = False) -> dict[str, Any]:
    """``environments``: remote tiers keep the workflow's environments and check entry and secret visibility
    (gha.environments); act ignores environments."""
    d = d.resolve()
    if params:
        undeclared = sorted(set(params) - declared_parameters(d))
        if undeclared:  # before anything runs: an override of APP_NAME or BRANCH_NAME would compare other scenarios
            raise ValueError(f"--param {', '.join(undeclared)}: not a declared pipeline parameter of examples/{d.name} "
                             f"(declared: {', '.join(sorted(declared_parameters(d))) or 'none'})")
    meta = _load(d / "source.json") or {}
    scenario = scenario_for(meta, branch, params)
    runs = d / "runs"
    runs.mkdir(exist_ok=True)
    model = _load(d / "gha" / "workflow.model.json")
    conv = _load(d / "gha" / "conversion.json") or {}
    if any(t != "jenkins" for t in tiers) and model is None:
        log(f"{d.name}: no converted workflow (report-only?) - GHA tiers skipped")
        tiers = [t for t in tiers if t == "jenkins"]
    base = {"jenkinsfile_sha256": jenkinsfile_sha256(d), "scenario": scenario, "mode": mode}
    model_sha = sha256_json(model) if model is not None else None  # hash what is executed, not what convert recorded
    edited = model is not None and conv.get("model_sha256") != model_sha
    # an edited model is refused (the records would claim the conversion) unless a mutation test asks for it
    stale = model is not None and (conv.get("source_sha256") != base["jenkinsfile_sha256"]
                                   or (edited and not allow_edited_model))
    repo = (meta.get("repository") or {}).get("full_name")
    # full mode checks out the commit the Jenkinsfile was taken from (crawler snapshot; older examples: last commit)
    source = ({"repository": repo, "sha": meta.get("snapshot_commit") or meta.get("file_last_commit_sha")}
              if repo else None)
    images = image_provenance()
    stage_order_pairs = _source_order(d)
    records: dict[str, Any] = {}
    for tier in [t for t in TIER_ORDER if t in tiers]:
        out = runs / f"{tier}-{mode}"
        out.mkdir(parents=True, exist_ok=True)
        try:
            if tier != "jenkins" and stale:
                raise RuntimeError("the converted workflow is stale (the Jenkinsfile or gha/workflow.model.json changed "
                                   "since `j2gha convert`)")
            if tier == "jenkins":
                from ..jenkins.run import LOCALIZER_VERSION, run_jenkins
                rec = run_jenkins(d, mode, scenario, docker=docker_socket)
                prov = {**base, "localizer_version": LOCALIZER_VERSION}
            elif tier == "act":
                from .act import WORKFLOW_PATH as ACT_WORKFLOW_PATH, run_act
                if environments:
                    log(f"{d.name}: act ignores environments (--environments applies to selfhosted/hosted)")
                variant, notes = make_variant(model, mode, "act", scenario, source, max_minutes=max_minutes or 10)
                yml = to_yaml(variant, f"# j2gha act variant ({mode}) of examples/{d.name}\n")
                (out / "workflow.yml").write_text(yml)
                rec = run_act(out, yml, scenario["branch"], mode, source=source if mode == "full" else None,
                              timeout=900 if mode == "trace" else 3600)
                if mode == "full":
                    rec["outputs"] = act_outputs(out / "artifacts", model, injected={ACT_WORKFLOW_PATH: yml})
                rec["variant_notes"] = notes
                prov = {**base, "model_sha256": model_sha, **({"edited_model": True} if edited else {})}
            elif tier in ("hosted", "selfhosted"):
                from ..gha.remote import run_remote
                rec = run_remote(d, model, mode, tier, scenario, source, yes=yes, max_minutes=max_minutes,
                                 environments=environments)
                prov = {**base, "model_sha256": model_sha, **({"edited_model": True} if edited else {})}
            else:
                continue
        except Exception as e:  # noqa: BLE001
            log(f"{d.name}: {tier} failed: {e}")
            rec = {"tier": tier, "mode": mode, "result": "error", "error": str(e), "traces": []}
            prov = dict(base)
        rec["provenance"] = {**prov, "images": images}
        rec["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (out / "result.json").write_text(json.dumps(rec, indent=2, default=str) + "\n")
        records[tier] = rec
    # reference = Jenkins record from this or an earlier invocation, if it ran this Jenkinsfile and scenario
    ref = records.get("jenkins") or _load(runs / f"jenkins-{mode}" / "result.json")
    for tier, rec in records.items():
        if tier == "jenkins" or run_status(rec) != "ran":
            continue
        rec["comparison"] = c = _compare(ref, rec, base, model, stage_order_pairs)
        (runs / f"{tier}-{mode}" / "result.json").write_text(json.dumps(rec, indent=2, default=str) + "\n")
        log(f"{d.name}: {tier} vs jenkins ({mode}): {c['verdict'].upper()}"
            + (f" ({c['similarity_pct']}% step similarity)" if mode == "trace" and c.get("similarity_pct") is not None
               else f" (jenkins {c['jenkins_result']} at {c['jenkins_failed_stage']}, {tier} {c['gha_result']} at "
                    f"{c['gha_failed_stage']})" if mode == "full" else "")
            + (f" - {_inconclusive_text(c['inconclusive'])}" if c.get("inconclusive") else ""))
    update_section(d / "README.md", "execution", render_execution(d))
    statuses = {tier: run_status(rec) for tier, rec in records.items()}
    verdicts = {tier: rec["comparison"]["verdict"] for tier, rec in records.items() if rec.get("comparison")}
    return {"ok": "infra" not in statuses.values(), "statuses": statuses, "verdicts": verdicts, "records": records}


def image_provenance() -> dict[str, Any]:
    from .images import image_provenance as inspect
    return inspect()


def reference_problem(ref: dict[str, Any] | None, base: dict[str, Any]) -> str | None:
    """Why a saved Jenkins record cannot serve as the reference for this run (None: it can)."""
    if ref is None:
        return "no Jenkins reference run (run the jenkins tier)"
    if run_status(ref) != "ran":
        return f"the Jenkins reference did not run ({ref.get('result')})"
    prov = ref.get("provenance") or {}
    if prov.get("jenkinsfile_sha256") != base["jenkinsfile_sha256"]:
        return "the Jenkins reference ran another version of the Jenkinsfile (re-run the jenkins tier)"
    scenario = prov.get("scenario") or ref.get("scenario")
    if prov.get("localizer_version") != LOCALIZER_VERSION:
        return (f"the Jenkins reference was recorded by localiser v{prov.get('localizer_version')}, now "
                f"v{LOCALIZER_VERSION} (re-run the jenkins tier)")
    if scenario != base["scenario"]:
        return (f"the Jenkins reference ran scenario {scenario} but this run used {base['scenario']} "
                "(re-run the jenkins tier with the same --branch)")
    if base.get("mode") == "full" and "outputs" not in ref:
        return "the Jenkins reference recorded no archived files or test results (re-run the jenkins tier)"
    return None


def declared_parameters(d: Path) -> set[str]:
    """Names of the parameters the Jenkinsfile declares (from its AST)."""
    ast = _load(d / "analysis" / "groovy-ast.json")
    ir = build_ir(ast) if ast else None
    return {p.name for p in ir.parameters} if ir else set()


def _source_order(d: Path) -> list[tuple[str, str]]:
    """Stage order the original Jenkinsfile fixes (from its own AST, not from the converted workflow)."""
    ast = _load(d / "analysis" / "groovy-ast.json")
    try:
        return stage_order(build_ir(ast)) if ast else []
    except Exception:  # noqa: BLE001 - an unreadable AST only disables the cross-stage order check
        return []


def _compare(ref: dict[str, Any] | None, rec: dict[str, Any], base: dict[str, Any],
             model: dict[str, Any] | None, order: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    why = reference_problem(ref, base)
    if why:
        return {"mode": base["mode"], "equivalent": False, "verdict": "inconclusive", "similarity_pct": None,
                "stages": [], "inconclusive": {"reason": why, "stage": None},
                "jenkins_result": (ref or {}).get("result"), "gha_result": rec.get("result"),
                "jenkins_failed_stage": None, "gha_failed_stage": None, "gha_failed_step": None}
    if base["mode"] == "full":
        out = compare_outcome(ref, rec, model)
    else:
        out = compare(ref["traces"], rec.get("traces") or [], reference_result=ref.get("result"),
                      candidate_result=rec.get("result"), concurrent=concurrent_stages(model), order=order)
    if "environments" in rec:  # `run --environments`: the environments entered must follow Jenkins' inputs
        env = out["environments"] = compare_environments(ref, rec, model)
        if env["status"] == "differs":
            out.update(verdict="differs", equivalent=False)
        elif env["status"] == "inconclusive" and out["verdict"] == "equivalent":
            out.update(verdict="inconclusive", equivalent=False,
                       inconclusive={"reason": f"environments not compared: {env['reason']}", "stage": None})
    return out


def _inconclusive_text(inc: dict[str, Any]) -> str:
    if inc.get("reason") and "stages_before" not in inc:
        return inc["reason"]
    before = inc.get("stages_before") or []
    tail = (f"; the {len(before)} stage(s) before it are "
            + ("equivalent" if inc.get("stages_before_equivalent") else "not equivalent")) if before else ""
    return f"Jenkins stopped on the pipeline's own error() in stage '{inc['stage'] or '(no stage)'}'{tail}"


def step_stages(model: dict[str, Any] | None) -> dict[str, set[str]]:
    """Generated step name (step_name_key) -> the Jenkins stage(s) it belongs to (from the `_j2gha` metadata)."""
    out: dict[str, set[str]] = {}
    for job in ((model or {}).get("jobs") or {}).values():
        for st in job.get("steps", []):
            meta = st.get("_j2gha") or {}
            stage = meta.get("stage") or next((e[0] for e in meta.get("trace_events") or []), None)
            if stage is not None and st.get("name"):
                out.setdefault(step_name_key(st["name"]), set()).add(stage)
    return out


def compare_outcome(ref: dict[str, Any], rec: dict[str, Any], model: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full mode: compare the overall result and, for failures, the first failing stage (Jenkins wfapi vs the
    converted workflow's first failing step, mapped to its stage through the workflow model), then the outputs
    (`j2gha.outputs`: test cases and the set of archived files; content hashes are shown, not counted). Records
    without `outputs` (before Phase 4) compare on the outcome alone."""
    j, g = outcome(ref.get("result")), outcome(rec.get("result"))
    j_stage = next((s["name"] for s in ref.get("stages", []) if s.get("status") == "FAILED"), None)
    g_step = (rec.get("failed_steps") or [None])[0]
    stages = step_stages(model).get(step_name_key(g_step), set())
    g_stage = next(iter(stages)) if len(stages) == 1 else None
    reason = None
    if "infra" in (j, g):
        reason = f"a run did not finish normally (Jenkins {ref.get('result')}, converted {rec.get('result')})"
    elif "cancelled" in (j, g):
        reason = "a run was aborted/cancelled"
    elif not ref.get("stages") and not rec.get("jobs"):
        reason = "neither run reports a stage or job: two bare outcomes show nothing about the work done"
    elif j != g and "unstable" in (j, g):
        reason = "GitHub Actions has no UNSTABLE result"
    elif j == g == "failure" and (j_stage is None or g_stage is None):
        reason = "the failing stage is unknown on " + ("both sides" if j_stage is None and g_stage is None else
                                                       "the Jenkins side" if j_stage is None else "the converted side")
    outputs = (compare_outputs(ref.get("outputs"), rec.get("outputs"))
               if "outputs" in ref or "outputs" in rec else None)
    if reason:
        verdict = "inconclusive"
    elif j != g:
        verdict = "differs"
    else:
        verdict = "equivalent" if j == "success" or j_stage == g_stage else "differs"
    if verdict == "equivalent" and outputs and outputs["verdict"] != "same":
        verdict = outputs["verdict"] if outputs["verdict"] == "differs" else "inconclusive"
        if verdict == "inconclusive":
            reason = f"the outputs could not be compared: {outputs.get('reason')}"
    out = {"mode": "full", "verdict": verdict, "equivalent": verdict == "equivalent",
           "similarity_pct": 100.0 if verdict == "equivalent" else 0.0 if verdict == "differs" else None,
           "jenkins_result": ref.get("result"), "gha_result": rec.get("result"),
           "jenkins_failed_stage": j_stage, "gha_failed_stage": g_stage, "gha_failed_step": g_step, "stages": []}
    if outputs:
        out["outputs"] = outputs
    if reason:
        out["inconclusive"] = {"reason": reason, "stage": None}
    return out


def stale_reason(d: Path, rec: dict[str, Any], tier: str) -> str | None:
    """Why a saved run record no longer describes the example (Jenkinsfile or converted workflow changed)."""
    prov = rec.get("provenance")
    if not prov:
        return "recorded before provenance tracking"
    if prov.get("jenkinsfile_sha256") != jenkinsfile_sha256(d):
        return "the Jenkinsfile changed since this run"
    if tier == "jenkins":
        if prov.get("localizer_version") != LOCALIZER_VERSION:
            return "the Jenkins localiser changed since this run"
    elif prov.get("edited_model"):
        return "ran an edited workflow model (a mutation test, not a measurement of the conversion)"
    else:
        model = _load(d / "gha" / "workflow.model.json")
        if model is None or prov.get("model_sha256") != sha256_json(model):
            return "the converted workflow changed since this run"
    return None


VERDICT_LABEL = {"trace": {"equivalent": "✅ equivalent", "differs": "❌ differs", "inconclusive": "⚠️ inconclusive"},
                 "full": {"equivalent": "✅ same outcome", "differs": "❌ different outcome",
                          "inconclusive": "⚠️ inconclusive"}}


def render_execution(d: Path) -> str:
    runs = d / "runs"
    rows = []
    details = []
    for mode in ("trace", "full"):
        for tier in TIER_ORDER:
            rec = _load(runs / f"{tier}-{mode}" / "result.json")
            if not rec:
                continue
            comp = rec.get("comparison")
            stale = stale_reason(d, rec, tier)
            sim = f"{comp['similarity_pct']}%" if comp and comp.get("similarity_pct") is not None and \
                comp.get("mode") != "full" else "-"
            if comp and comp.get("mode") == "full":
                details.append(f"- full mode ({tier}): Jenkins **{comp['jenkins_result']}** "
                               f"(first failed stage: {comp['jenkins_failed_stage'] or '-'}); {tier} **{comp['gha_result']}** "
                               f"(first failed step: `{comp['gha_failed_step'] or '-'}`)"
                               + (f"; {output_summary(comp['outputs'])}" if comp.get("outputs") else ""))
            if cost := rec.get("handoff"):
                path = (f"; {cost['critical_path_seconds']} s on the critical path of a {cost['run_seconds']} s run"
                        if "critical_path_seconds" in cost and "run_seconds" in cost else "")
                details.append(f"- workspace hand-off ({tier}, {mode}): {cost['archives']} archives, "
                               f"{cost['bytes'] / 1e6:.1f} MB; {cost['steps']} steps, {cost['seconds']} s summed over "
                               f"jobs (of {cost['job_seconds']} s job time){path}")
            if comp and comp.get("environments"):
                env = comp["environments"]
                details.append(f"- environments ({tier}, {mode}): {env['status']}"
                               + (f" - expected {env.get('expected') or 'none'}, entered {env.get('entered') or 'none'}"
                                  if "expected" in env else f" ({env.get('reason')})")
                               + (f"; secret not visible in {', '.join(env['secret_not_visible'])}"
                                  if env.get("secret_not_visible") else ""))
            eq = (VERDICT_LABEL[mode].get(comp.get("verdict") or ("equivalent" if comp["equivalent"] else "differs"))
                  if comp else ("reference" if tier == "jenkins" else "-"))
            if stale:
                eq = f"⏸️ stale ({eq})"
            if comp and comp.get("inconclusive"):
                details.append(f"- {tier} ({mode}) inconclusive: {_inconclusive_text(comp['inconclusive'])}."
                               + (" Compare these runs in full mode instead." if "stages_before" in comp["inconclusive"]
                                  else ""))
            notes = [f"stale: {stale}"] if stale else []
            if tier == "jenkins":
                loc = rec.get("localisation", {})
                notes.append(f"{len(loc.get('changes', []))} localisation changes, {len(loc.get('stubs', []))} stubs")
                rep = loc.get("auto_repairs", {})
                if rep.get("removed") or rep.get("stubbed"):
                    notes.append(f"auto-repair: {rep.get('removed', []) + rep.get('stubbed', [])}")
                if rep.get("ineffective"):
                    notes.append(f"⚠️ auto-repair with no effect (not applied): {rep['ineffective']}")
            if rec.get("variant_notes", {}).get("dropped_jobs"):
                notes.append("dropped: " + ", ".join(rec["variant_notes"]["dropped_jobs"]))
            if rec.get("billable_minutes") is not None:
                notes.append(f"billable ≈ {rec['billable_minutes']} min")
            if rec.get("run_url"):
                notes.append(f"[run]({rec['run_url']})")
            if rec.get("error"):
                notes.append(str(rec["error"])[:120])
            result = rec.get("result")
            rows.append(f"| {tier} | {mode} | {result} | {len(rec.get('traces') or [])} | {sim} | {eq} | "
                        f"{'; '.join(notes)} |")
            if comp and not comp["equivalent"] and comp.get("mode") != "full" and comp.get("stages"):
                diff = [f"- `{s['stage'] or '(no stage)'}`: {s['status']} - jenkins {s['jenkins']} vs {tier} {s['gha']}"
                        for s in comp["stages"] if s["status"] != "match"]
                details.append(f"<details><summary>{tier} ({mode}) differences</summary>\n\n" + "\n".join(diff[:30]) +
                               "\n\n</details>")
            if tier == "jenkins" and rec.get("error_tail") and result not in ("SUCCESS",):
                details.append(f"<details><summary>jenkins ({mode}) failure</summary>\n\n```text\n"
                               f"{str(rec['error_tail'])[:1500]}\n```\n</details>")
    if not rows:
        return "_Not executed yet - run `uv run j2gha run <id> --tier jenkins,act`._"
    est = ""
    model = _load(d / "gha" / "workflow.model.json")
    if model:
        e = estimate_minutes(make_variant(model, "trace", "hosted", {"branch": "main"})[0], "trace")
        est = f"\nEstimated hosted cost of a trace run: ~{e['typical']} billable minute(s) (worst case {e['worst_case']})."
    return "\n".join(["### Execution\n",
                      "Trace mode compares the per-stage sequence of executed steps (`J2GHA-TRACE` markers) between the "
                      "localised Jenkinsfile on the disposable Jenkins controller and the converted workflow; full mode "
                      "runs the real commands. Trace markers carry the stage and step kind only: they show control-flow "
                      "fidelity, not that the commands themselves are equivalent, and only for the scenario that was "
                      "run: *equivalent* means no difference was found, not that the conversion is correct.\n",
                      "| Tier | Mode | Result | Trace events | Similarity | vs Jenkins | Notes |",
                      "|---|---|---|---:|---:|---|---|", *rows, est, "", *details])
