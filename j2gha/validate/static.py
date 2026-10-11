"""Static validation of generated workflows: actionlint (+shellcheck), zizmor and j2gha policy checks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..config import ACTIONLINT_IMAGE, ZIZMOR_IMAGE
from ..readme import update_section

ACTIONLINT_PINNED = "rhysd/actionlint:1.7.12"
ZIZMOR_PINNED = "ghcr.io/zizmorcore/zizmor:1.30.1"


def log(msg: str) -> None:
    print(f"[validate] {msg}", file=sys.stderr, flush=True)


def _image(default: str, pinned: str) -> str:
    return pinned if default.endswith(":latest") else default


def _tool_error(tool: str, img: str, p: subprocess.CompletedProcess, what: str = "") -> dict[str, Any]:
    detail = (p.stderr or p.stdout or "").strip()[-800:]
    return {"tool": tool, "image": img, "ok": False, "findings": [],
            "error": f"exit {p.returncode}" + (f", {what}" if what else "") + (f": {detail}" if detail else "")}


def _list_of_dicts(items: Any) -> bool:
    return isinstance(items, list) and all(isinstance(i, dict) for i in items)


def run_actionlint(gha_dir: Path, filename: str = "workflow.yml") -> dict[str, Any]:
    img = _image(ACTIONLINT_IMAGE, ACTIONLINT_PINNED)
    cmd = ["docker", "run", "--rm", "--network", "none", "-v", f"{gha_dir}:/repo", "-w", "/repo", img,
           "-format", "{{json .}}", filename]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode not in (0, 1):
        return _tool_error("actionlint", img, p)
    try:
        items = json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        return _tool_error("actionlint", img, p, "unparseable JSON output")
    # exit 1 means "findings reported": no findings with it is a failed run, not a clean workflow
    if not _list_of_dicts(items) or (p.returncode == 1 and not items):
        return _tool_error("actionlint", img, p, "unexpected output")
    findings = [{"line": i.get("line"), "col": i.get("column"), "kind": i.get("kind"), "message": i.get("message")}
                for i in items]
    structural = [f for f in findings if f["kind"] not in ("shellcheck", "pyflakes")]
    return {"tool": "actionlint", "image": img, "ok": not structural, "findings": findings,
            "structural": len(structural), "shellcheck": sum(1 for f in findings if f["kind"] == "shellcheck")}


def run_zizmor(gha_dir: Path, filename: str = "workflow.yml") -> dict[str, Any]:
    img = _image(ZIZMOR_IMAGE, ZIZMOR_PINNED)
    cmd = ["docker", "run", "--rm", "--network", "none", "-v", f"{gha_dir}:/repo:ro", "-w", "/repo", img,
           "--offline", "--no-exit-codes", "--format", "json", filename]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:  # --no-exit-codes: any non-zero exit is zizmor (or docker) failing, not a finding
        return _tool_error("zizmor", img, p)
    try:
        items = json.loads(p.stdout)
    except json.JSONDecodeError:
        return _tool_error("zizmor", img, p, "unparseable JSON output")
    if not _list_of_dicts(items):
        return _tool_error("zizmor", img, p, "unexpected output")
    findings = []
    for i in items:
        loc = (i.get("locations") or [{}])[0]
        span = (loc.get("concrete") or {}).get("location", {}).get("start_point", {})
        findings.append({"rule": i.get("ident"), "severity": (i.get("determinations") or {}).get("severity"),
                         "confidence": (i.get("determinations") or {}).get("confidence"),
                         "message": i.get("desc"), "line": (span.get("row", -1) + 1) if span else None})
    high = [f for f in findings if f["severity"] in ("High",)]
    return {"tool": "zizmor", "image": img, "ok": not high, "findings": findings}


from .contexts import context_checks  # noqa: E402


def policy_checks(workflow_text: str) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    try:
        wf = yaml.safe_load(workflow_text)
    except yaml.YAMLError as e:
        return {"tool": "j2gha-policy", "ok": False, "findings": [{"rule": "yaml", "severity": "error", "message": str(e)}]}
    if not isinstance(wf, dict):
        return {"tool": "j2gha-policy", "ok": False, "findings": [{"rule": "yaml", "severity": "error",
                                                                  "message": "not a mapping"}]}
    on = wf.get("on", wf.get(True))
    if not wf.get("permissions"):
        findings.append({"rule": "explicit-permissions", "severity": "error", "message": "no top-level permissions"})
    if isinstance(on, dict) and "pull_request_target" in on:
        findings.append({"rule": "no-pull-request-target", "severity": "error",
                         "message": "pull_request_target runs untrusted code with secrets"})
    for jid, job in (wf.get("jobs") or {}).items():
        if "timeout-minutes" not in job:
            findings.append({"rule": "job-timeout", "severity": "warning", "message": f"job '{jid}' has no timeout-minutes "
                             "(GitHub default is 360 minutes)"})
        for st in job.get("steps", []) or []:
            uses = st.get("uses", "")
            if uses and "@" in uses and not re.search(r"@[0-9a-f]{40}$", uses) and not uses.startswith("./"):
                findings.append({"rule": "pin-actions", "severity": "warning", "message": f"{uses} not pinned to a SHA"})
            run = str(st.get("run", ""))
            if "J2GHA_TODO" in run or "TODO-j2gha" in json.dumps(st.get("env", {})):
                findings.append({"rule": "unresolved-groovy", "severity": "warning",
                                 "message": f"job '{jid}' step '{st.get('name')}' contains untranslated Groovy"})
            if "requires manual migration" in run or "manual migration:" in run:
                findings.append({"rule": "manual-placeholder", "severity": "info",
                                 "message": f"job '{jid}' step '{st.get('name')}' is a manual-migration placeholder"})
            if re.search(r"\$\{\{\s*github\.event\.(issue|pull_request|comment|head_commit)\.[^}]*(title|body|message)", run):
                findings.append({"rule": "script-injection", "severity": "error",
                                 "message": f"untrusted event data interpolated into run in '{st.get('name')}'"})
    findings += context_checks(wf)
    secrets = sorted(set(re.findall(r"secrets\.([A-Za-z0-9_]+)", workflow_text)))
    ok = not any(f["severity"] == "error" for f in findings)
    return {"tool": "j2gha-policy", "ok": ok, "findings": findings, "secrets": secrets}


def validate_example(d: Path) -> dict[str, Any]:
    gha = d / "gha"
    text = (gha / "workflow.yml").read_text()
    results = {"actionlint": run_actionlint(gha), "zizmor": run_zizmor(gha), "policy": policy_checks(text)}
    # structural (actionlint + policy) gates; zizmor findings are advisory, but a scanner that did not run is a failure
    tools_ok = not any(r.get("error") for r in results.values())
    structural_ok = results["actionlint"]["ok"] and results["policy"]["ok"]
    security_ok = results["zizmor"]["ok"]
    ok = structural_ok and tools_ok
    summary = {"ok": ok, "structural_ok": structural_ok, "security_ok": security_ok, "tools_ok": tools_ok,
               "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **results}
    (gha / "validation.json").write_text(json.dumps(summary, indent=2) + "\n")
    update_section(d / "README.md", "validation", render(summary))
    al, zz, po = results["actionlint"], results["zizmor"], results["policy"]
    errors = [f"{r['tool']} error ({r['error'][:120]})" for r in results.values() if r.get("error")]
    log(f"{d.name}: actionlint {len(al['findings'])} ({al.get('shellcheck', 0)} shellcheck), zizmor "
        f"{len(zz['findings'])}, policy {len(po['findings'])} -> {'OK' if ok else 'FAIL'}"
        + (f" - {'; '.join(errors)}" if errors else ""))
    return summary


def render(v: dict[str, Any]) -> str:
    al, zz, po = v["actionlint"], v["zizmor"], v["policy"]
    sev: dict[str, int] = {}
    for f in zz["findings"]:
        sev[f["severity"] or "?"] = sev.get(f["severity"] or "?", 0) + 1

    def err(r: dict[str, Any]) -> str:
        return f"tool error: {r['error'][:200]}".replace("|", "\\|").replace("\n", " ")

    out = ["### Static validation\n",
           "Structural checks (actionlint, j2gha policy) gate the result; zizmor security findings are advisory "
           "(⚠️), but a scanner that fails to run fails validation.\n",
           "| Check | Result | Findings |", "|---|---|---|",
           f"| actionlint ({al.get('image', '')}) | {'✅' if al['ok'] else '❌'} | "
           + (err(al) if al.get("error") else f"{al.get('structural', 0)} structural") + " |",
           f"| shellcheck via actionlint (SAST on converted `sh` bodies) | {'✅' if not al.get('shellcheck') else 'ℹ️'} | "
           f"{al.get('shellcheck', 0)} |",
           f"| zizmor ({zz.get('image', '')}, offline) | {'❌' if zz.get('error') else '✅' if zz['ok'] else '⚠️'} | "
           + (err(zz) if zz.get("error") else ", ".join(f"{k}: {n}" for k, n in sorted(sev.items())) or "0") + " |",
           f"| j2gha policy | {'✅' if po['ok'] else '❌'} | {len(po['findings'])} |", ""]
    if al["findings"]:
        out += ["<details><summary>actionlint findings</summary>\n"]
        out += [f"- L{f['line']}: [{f['kind']}] {f['message']}" for f in al["findings"][:25]]
        out.append("\n</details>\n")
    if zz["findings"]:
        rules: dict[str, int] = {}
        for f in zz["findings"]:
            rules[f["rule"]] = rules.get(f["rule"], 0) + 1
        out.append("zizmor rules: " + ", ".join(f"`{k}`×{n}" for k, n in rules.items()))
    if po["findings"]:
        kinds: dict[str, int] = {}
        for f in po["findings"]:
            kinds[f["rule"]] = kinds.get(f["rule"], 0) + 1
        out.append("\nPolicy: " + ", ".join(f"`{k}`×{n}" for k, n in kinds.items()))
    return "\n".join(out)
