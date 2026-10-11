"""Append a "Result" paragraph to examples/<id>/LOCAL.md from the twin's run records, one line per tier.

    uv run python .claude/skills/jenkins-example-twin/scripts/twin_results.py 109 [--note "free text"]

Reads runs/jenkins-<mode>/result.json and runs/<tier>-<mode>/result.json (full mode by default; --mode trace for
trace runs) and prints what it appended, so the same facts land in LOCAL.md and in your report. Run it again after
more tiers ran: each record is identified by its tier, mode and `finished_at`, so a run already recorded is not
repeated, while a re-run (or the other mode's run) of the same day is recorded.
"""
import argparse
import datetime
import json
import pathlib


def load(p: pathlib.Path):
    return json.loads(p.read_text()) if p.exists() else None


def when(rec: dict) -> str:
    """A record's identity in LOCAL.md: when it finished (records without it: the date this script runs)."""
    return rec.get("finished_at") or datetime.date.today().isoformat()


def outputs_line(cmp: dict) -> str:
    o = cmp.get("outputs") or {}
    tests, arch = o.get("tests") or {}, o.get("archived") or {}
    parts = []
    jt, gt = tests.get("jenkins") or {}, tests.get("gha") or {}
    if jt.get("cases") or gt.get("cases"):
        parts.append(f"JUnit cases {jt.get('cases', 0)} (Jenkins) / {gt.get('cases', 0)} (converted), {tests.get('status')}")
    if arch.get("jenkins") or arch.get("gha"):
        extra = ""
        if arch.get("missing") or arch.get("extra"):
            extra = f" (missing {len(arch.get('missing') or [])}, extra {len(arch.get('extra') or [])})"
        parts.append(f"archived files {arch.get('jenkins')} (Jenkins) / {arch.get('gha')} (converted), {arch.get('status')}{extra}")
    return "; ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("example")
    ap.add_argument("--mode", default="full", choices=["full", "trace"])
    ap.add_argument("--note", default="", help="one or two sentences explaining the verdicts (why they differ, what they prove)")
    a = ap.parse_args()
    d = pathlib.Path("examples") / a.example
    local = d / "LOCAL.md"
    if not local.exists():
        raise SystemExit(f"{local} does not exist: this script is for twins (see mk_twin.py)")
    j = load(d / "runs" / f"jenkins-{a.mode}" / "result.json")
    if not j:
        raise SystemExit(f"no Jenkins {a.mode}-mode record under {d}/runs")
    text = local.read_text()
    lines = []
    stamp = f"Result ({a.mode} mode, Jenkins run {when(j)})"
    if stamp not in text:
        failed = [s["name"] for s in j.get("stages", []) if s.get("status") not in ("SUCCESS", "NOT_EXECUTED", None)]
        lines.append(f"\n{stamp}: Jenkins **{j.get('result')}**" + (f" (failed: {', '.join(failed[:4])})" if failed else "") + ".")
    for tier in ("act", "selfhosted", "hosted"):
        rec = load(d / "runs" / f"{tier}-{a.mode}" / "result.json")
        if not rec:
            continue
        # the run's own identity: tier, mode and when it finished (not the date this script runs)
        marker = f"- {tier} {a.mode} ({when(rec)})"
        if marker in text:
            continue
        cmp = rec.get("comparison") or {}
        where = ""
        if rec.get("result") != "success":
            where = f" at *{cmp.get('gha_failed_stage') or cmp.get('gha_failed_step') or '?'}*"
        line = f"{marker}: **{rec.get('result')}**{where}, verdict **{cmp.get('verdict')}**"
        if (ol := outputs_line(cmp)):
            line += f"; {ol}"
        if rec.get("run_url"):
            line += f" ({rec['run_url']})"
        lines.append(line + ".")
    if a.note:
        lines.append(a.note.strip())
    if not lines:
        print("nothing new to record")
        return
    block = "\n".join(lines) + "\n"
    local.write_text(text.rstrip("\n") + "\n" + block)
    print(block)


if __name__ == "__main__":
    main()
