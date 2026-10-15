"""j2gha command line interface.

    j2gha crawl --count N            find & score example Jenkinsfiles on github.com -> examples/NNN
    j2gha add PATH [--name N]        copy your own Jenkinsfile (any file name) in as pipeline N
    j2gha analyze [IDS]              AST analysis (+ Jenkins model when the controller is up) -> README
    j2gha convert [IDS]              IR -> GitHub Actions workflow + migration report
    j2gha validate [IDS]             actionlint / zizmor / policy checks on the generated workflow
    j2gha run IDS --tier T           execute: jenkins (Docker), act, selfhosted (JIT runner), hosted (GHA)
    j2gha pipeline [IDS]             analyze -> convert -> validate -> run (local tiers)
    j2gha jenkins up|down|status     manage the disposable JCasC Jenkins controller
    j2gha docker build               build harness images
    j2gha budget                     GitHub Actions minutes usage + guard status
    j2gha gaps | scoreboard | guard  rule-improvement evals (docs/self-improvement.md)
    j2gha summary                    write examples/README.md (corpus index), or J2GHA_PIPELINES_DIR's index
    j2gha docs fetch|status|use|path|xref   local, version-pinned Jenkins + GHA reference docs for agents

IDS are corpus numbers (003, 1-5, "004 009") or pipeline names; `all` (the default) is the numbered corpus, or every
pipeline in J2GHA_PIPELINES_DIR (--pipelines-dir) when that is set: keep your own pipelines there, outside the clone.
J2GHA_OFFLINE=1 (--offline): no GitHub API calls (cached lookups only), no source or docs fetch; the remote tiers and
full mode on a cited source are refused.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import config
from .config import list_pipeline_ids, normalise_id


def _ids(values: list[str] | None) -> list[str]:
    if not values or values == ["all"]:
        return list_pipeline_ids()
    out = []
    for v in (p for val in values for p in val.replace(",", " ").split()):  # "004 009" / "004,009" too
        if "-" in v and all(p.isdigit() for p in v.split("-", 1)):
            a, b = (int(x) for x in v.split("-", 1))
            out += [f"{i:03d}" for i in range(a, b + 1)]
        else:
            out.append(normalise_id(v))
    return out


def _pipelines(values: list[str] | None) -> list[str]:
    """`_ids` for the stage commands: every pipeline must have a Jenkinsfile (a clear error, not a crash later)."""
    ids = _ids(values)
    own = config.pipelines_dir()
    where = f"{own} (J2GHA_PIPELINES_DIR) or {config.EXAMPLES_DIR}" if own else str(config.EXAMPLES_DIR)
    if not ids:
        raise SystemExit(f"j2gha: no pipelines in {where}; add one with `j2gha add PATH`")
    missing = [i for i in ids if not (config.example_dir(i) / "Jenkinsfile").is_file()]
    if missing:
        raise SystemExit(f"j2gha: no Jenkinsfile for {', '.join(missing)} in {where}; add one with "
                         "`j2gha add PATH --name NAME`" + ("" if own else ", or set J2GHA_PIPELINES_DIR"))
    return ids


def cmd_add(a: argparse.Namespace) -> int:
    from .stages import add_pipeline

    try:
        d = add_pipeline(Path(a.path), name=a.name, force=a.force)
    except ValueError as e:
        raise SystemExit(f"j2gha add: {e}") from None
    print(d.name)
    return 0


def _online(what: str) -> None:
    if config.offline():
        raise SystemExit(f"j2gha {what}: J2GHA_OFFLINE is set, and this command works on GitHub")


def cmd_crawl(a: argparse.Namespace) -> int:
    from .crawl.crawler import crawl, rescore

    _online("crawl")

    if a.rescore:
        rescore()
        return 0
    written = crawl(a.count, per_query=a.per_query, pages=a.pages, max_analyse=a.max_analyse,
                    allow_unlicensed=a.allow_unlicensed, styles=a.styles, dry_run=a.dry_run, verbose=a.verbose,
                    owners=[o.rstrip("/").rsplit("/", 1)[-1] for o in a.owner] if a.owner else None)
    for w in written:
        if isinstance(w, dict) and "id" in w:
            print(f"{w['id']}  {w['score']['total']:>4}  {w['primary_style']:<20} {w['repository']['full_name']}:{w['path']}")
        else:
            print(f"(dry-run) {w['score']['total']:>4}  {w['primary_style']:<20} {w['full_name']}:{w['path']}")
    return 0


def cmd_analyze(a: argparse.Namespace) -> int:
    from .stages import analyze_examples

    analyze_examples(_pipelines(a.ids), use_jenkins=a.jenkins)
    return 0


def cmd_convert(a: argparse.Namespace) -> int:
    from .stages import convert_examples

    convert_examples(_pipelines(a.ids))
    return 0


def cmd_validate(a: argparse.Namespace) -> int:
    from .stages import validate_examples

    return validate_examples(_pipelines(a.ids))


TIERS = ("jenkins", "act", "selfhosted", "hosted")


def _tiers(value: str) -> list[str]:
    tiers = [t.strip() for t in value.split(",") if t.strip()]
    unknown = [t for t in tiers if t not in TIERS]
    if unknown or not tiers:
        raise argparse.ArgumentTypeError(f"unknown tier(s) {', '.join(unknown) or '(none)'}; choose from "
                                         f"{', '.join(TIERS)}")
    return tiers


def _param(text: str) -> tuple[str, str]:
    name, sep, value = text.partition("=")
    if not sep or not name.isidentifier():
        raise argparse.ArgumentTypeError(f"expected NAME=VALUE, got {text!r}")
    return name, value


def cmd_run(a: argparse.Namespace) -> int:
    from .stages import run_examples

    return run_examples(_pipelines(a.ids), tiers=a.tier, mode=a.mode, docker_socket=a.docker, yes=a.yes,
                        max_minutes=a.max_minutes, branch=a.branch, fail_on_differs=a.fail_on_differs,
                        params=dict(a.param) or None, allow_edited_model=a.edited_model,
                        environments=a.environments)


def cmd_pipeline(a: argparse.Namespace) -> int:
    from .stages import analyze_examples, convert_examples, log, run_examples, validation_failures

    ids = _pipelines(a.ids)
    analyze_examples(ids, use_jenkins=True)
    convert_examples(ids)
    invalid = validation_failures(ids)
    if invalid and not a.continue_on_invalid:
        log(f"static validation failed for {', '.join(invalid)}: not executed (--continue-on-invalid runs them)")
        ids = [i for i in ids if i not in invalid]
    rc = run_examples(ids, tiers=a.tier, mode=a.mode, docker_socket=False, yes=a.yes, max_minutes=a.max_minutes,
                      branch=a.branch, fail_on_differs=a.fail_on_differs, params=dict(a.param) or None) if ids else 0
    return max(rc, 1 if invalid else 0)


def cmd_summary(a: argparse.Namespace) -> int:
    from .stages import summarize_examples, summarize_pipelines

    own = config.pipelines_dir()
    print(summarize_pipelines(own) if own else summarize_examples())
    return 0


def cmd_gaps(a: argparse.Namespace) -> int:
    from . import improve

    own = config.pipelines_dir()
    ids = _ids(a.ids) if a.ids or own else None
    # your own pipelines are read from J2GHA_PIPELINES_DIR; the default (and any corpus id among them) from examples/
    root = own if own and ids and all(config.example_dir(i).parent == own for i in ids) else None
    rows = improve.gaps(ids, examples_dir=root, include_holdout=a.include_holdout, unmapped_only=a.unmapped_only)
    print(json.dumps(rows, indent=2) if a.json else improve.format_gaps(rows, a.limit))
    return 0


def cmd_scoreboard(a: argparse.Namespace) -> int:
    from . import improve

    now = improve.scoreboard(_ids(a.ids) if a.ids else None)
    path = improve.baseline_path()
    if a.write:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(now, indent=1, sort_keys=True) + "\n")
        print(f"wrote {path}")
        return 0
    print(json.dumps(now, indent=1) if a.json else improve.format_scoreboard(now))
    if a.check:
        if not path.exists():
            print(f"no baseline at {path}; create one with `j2gha scoreboard --write`", file=sys.stderr)
            return 2
        reg, imp, unmeasured = improve.compare(json.loads(path.read_text()), now)
        for line in imp:
            print(f"improved:   {line}")
        for line in unmeasured:
            print(f"unmeasured: {line}")
        for line in reg:
            print(f"REGRESSED:  {line}")
        return 1 if reg or (a.strict and unmeasured) else 0
    return 0


def cmd_guard(a: argparse.Namespace) -> int:
    from . import improve

    bad, notes = improve.guard(a.base)
    for line in notes:
        print(f"review:    {line}")
    for line in bad:
        print(f"PROTECTED: {line}")
    if not bad:
        print("guard: no protected file touched")
    return 1 if bad else 0


def cmd_jenkins(a: argparse.Namespace) -> int:
    from .jenkins import controller

    if a.action == "up":
        with controller.exclusive("jenkins up"):
            controller.up(docker_socket=a.docker, rebuild=a.rebuild)
        print(f"Jenkins ready at {controller.Jenkins().base} (user admin)")
    elif a.action == "down":
        with controller.exclusive("jenkins down"):
            controller.down()
    else:
        print("running" if controller.Jenkins().available() else "not running")
    return 0


def cmd_docker(a: argparse.Namespace) -> int:
    from .runners.images import build_all

    build_all(only=a.only)
    return 0


def cmd_budget(a: argparse.Namespace) -> int:
    from .gha.budget import clear_reservations, report

    if a.clear:
        print(f"cleared {clear_reservations(a.clear)} pending reservation(s)")
        return 0
    _online("budget")
    r = report(refresh=a.refresh)
    print(json.dumps(r, indent=2) if a.json else r["text"])
    return 0


def cmd_environments(a: argparse.Namespace) -> int:
    from .gha.environments import delete_harness, list_harness
    from .gha.remote import harness_repo
    from .github import GitHub

    _online("environments")
    gh, repo = GitHub(cache_ttl=0), harness_repo()
    if a.action == "clean":
        names = delete_harness(gh, repo)
        print(f"deleted {len(names)} harness environment(s) from {repo}" + (f": {', '.join(names)}" if names else ""))
    else:
        names = list_harness(gh, repo)
        print("\n".join(names) if names else f"no harness environments (j2gha-*) in {repo}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="j2gha", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--offline", action="store_true", default=None,
                        help="no GitHub API calls (cached lookups only) and no source fetch; default: $J2GHA_OFFLINE")
    common.add_argument("--pipelines-dir", metavar="DIR", default=None,
                     help="directory of your own pipelines, outside the clone (default: $J2GHA_PIPELINES_DIR)")

    c = sub.add_parser("crawl", help="crawl github.com for example Jenkinsfiles")
    c.add_argument("--count", "-n", type=int, default=10, help="number of examples to add")
    c.add_argument("--per-query", type=int, default=30)
    c.add_argument("--pages", type=int, default=1)
    c.add_argument("--max-analyse", type=int, default=None)
    c.add_argument("--styles", nargs="*", default=None, help="restrict to these style ids")
    c.add_argument("--allow-unlicensed", action="store_true", help="include repos without a detected licence")
    c.add_argument("--owner", action="append", default=None, metavar="OWNER",
                   help="walk this GitHub user/org's repositories instead of code search (repeatable)")
    c.add_argument("--dry-run", action="store_true", help="select and score but do not write examples")
    c.add_argument("--rescore", action="store_true", help="recompute scores for existing examples")
    c.add_argument("--verbose", "-v", action="store_true")
    c.set_defaults(func=cmd_crawl)

    ad = sub.add_parser("add", parents=[common], help="copy your own Jenkinsfile in as a pipeline")
    ad.add_argument("path", help="the Jenkinsfile, whatever its name (or a directory containing a Jenkinsfile)")
    ad.add_argument("--name", default=None,
                    help="pipeline name (default: its directory, plus the file name when that is not Jenkinsfile)")
    ad.add_argument("--force", action="store_true", help="replace an existing pipeline's Jenkinsfile")
    ad.set_defaults(func=cmd_add)

    an = sub.add_parser("analyze", aliases=["analyse"], parents=[common], help="AST analysis of examples")
    an.add_argument("ids", nargs="*")
    an.add_argument("--no-jenkins", dest="jenkins", action="store_false",
                    help="skip Jenkins' authoritative Declarative model even if the controller can start")
    an.set_defaults(func=cmd_analyze)

    cv = sub.add_parser("convert", parents=[common], help="convert examples to GitHub Actions")
    cv.add_argument("ids", nargs="*")
    cv.set_defaults(func=cmd_convert)

    va = sub.add_parser("validate", parents=[common], help="static validation of generated workflows")
    va.add_argument("ids", nargs="*")
    va.set_defaults(func=cmd_validate)

    for name, func, default_tier in (("run", cmd_run, "jenkins,act"), ("pipeline", cmd_pipeline, "jenkins,act")):
        r = sub.add_parser(name, parents=[common], help="execute examples in one or more tiers" if name == "run"
                           else "analyze, convert, validate and run examples")
        r.add_argument("ids", nargs="*")
        r.add_argument("--tier", type=_tiers, default=_tiers(default_tier),
                       help="comma list of: jenkins, act, selfhosted, hosted")
        r.add_argument("--mode", choices=["trace", "full"], default="trace",
                       help="trace = control-flow differential run (commands stubbed); full = run real commands")
        r.add_argument("--yes", action="store_true", help="do not prompt before spending GitHub-hosted minutes")
        r.add_argument("--max-minutes", type=int, default=None, help="per-run worst-case minute ceiling for hosted tier")
        r.add_argument("--branch", default=None,
                       help="scenario branch (BRANCH_NAME/GIT_BRANCH on both sides); default: the source repo default branch")
        r.add_argument("--param", action="append", type=_param, default=[], metavar="NAME=VALUE",
                       help="scenario parameter value on both sides (Jenkins build parameter / workflow input); "
                            "repeatable; parameters left out keep their declared default")
        r.add_argument("--fail-on-differs", action="store_true",
                       help="exit 2 when a comparison differs or is inconclusive (default: only errors fail; exit 1 = "
                            "a tier produced no result, 3 = a hosted run was refused)")
        if name == "pipeline":
            r.add_argument("--continue-on-invalid", action="store_true",
                           help="also execute examples whose static validation failed (exit status stays 1)")
        if name == "run":
            r.add_argument("--edited-model", action="store_true",
                           help="run gha/workflow.model.json although it was edited after `convert` (mutation test: "
                                "the record is marked and never counted as a measurement)")
            r.add_argument("--docker", action="store_true",
                           help="mount the Docker socket into Jenkins for docker agents (privileged)")
            r.add_argument("--environments", action="store_true",
                           help="selfhosted/hosted: keep job environments (as j2gha-<name>, created in the harness "
                                "repository with a canary secret) and check which ones the run enters and that their "
                                "secret is visible (act ignores environments)")
        r.set_defaults(func=func)

    sm = sub.add_parser("summary", parents=[common],
                        help="write examples/README.md (corpus index with harness results), or the index of "
                             "J2GHA_PIPELINES_DIR when that is set")
    sm.set_defaults(func=cmd_summary)

    g = sub.add_parser("gaps", parents=[common],
                       help="steps the converter does not map, ranked by cost (rule-improvement worklist)")
    g.add_argument("ids", nargs="*")
    g.add_argument("--limit", type=int, default=20)
    g.add_argument("--json", action="store_true")
    g.add_argument("--unmapped-only", action="store_true",
                   help="only steps not in the catalog or listed as manual in a migration report")
    g.add_argument("--include-holdout", action="store_true", help="also count holdout examples (human use)")
    g.set_defaults(func=cmd_gaps)

    sc = sub.add_parser("scoreboard", help="per-example results; --check compares with evals/baseline.json")
    sc.add_argument("ids", nargs="*")
    sc.add_argument("--check", action="store_true", help="exit 1 on any regression against the baseline")
    sc.add_argument("--strict", action="store_true", help="with --check, also fail on unmeasured (stale/none) verdicts")
    sc.add_argument("--write", action="store_true", help="overwrite evals/baseline.json (a human decision)")
    sc.add_argument("--json", action="store_true")
    sc.set_defaults(func=cmd_scoreboard)

    gd = sub.add_parser("guard", help="fail if the change touches files that decide how results are judged")
    gd.add_argument("--base", default="HEAD", help="git ref to diff against (default HEAD; use main for a branch)")
    gd.set_defaults(func=cmd_guard)

    j = sub.add_parser("jenkins", help="manage the disposable Jenkins controller")
    j.add_argument("action", choices=["up", "down", "status"])
    j.add_argument("--docker", action="store_true", help="mount the Docker socket (docker agents)")
    j.add_argument("--rebuild", action="store_true")
    j.set_defaults(func=cmd_jenkins)

    d = sub.add_parser("docker", help="build harness docker images")
    d.add_argument("action", choices=["build"])
    from .runners.images import BUILD_TARGETS
    d.add_argument("--only", choices=BUILD_TARGETS, default=None)
    d.set_defaults(func=cmd_docker)

    b = sub.add_parser("budget", help="GitHub Actions minutes usage and guard status")
    b.add_argument("--json", action="store_true")
    b.add_argument("--refresh", action="store_true", help="ignore cached run timings")
    b.add_argument("--clear", nargs="+", metavar="ID", default=None,
                   help="clear pending minute reservations after checking their runs by hand")
    b.set_defaults(func=cmd_budget)

    en = sub.add_parser("environments", help="the harness repository's j2gha-* environments (run --environments)")
    en.add_argument("action", choices=["list", "clean"], nargs="?", default="list",
                    help="list them, or delete them with their canary secrets")
    en.set_defaults(func=cmd_environments)

    from .docs.commands import add_parser as add_docs_parser

    add_docs_parser(sub)

    a = p.parse_args(argv)
    if getattr(a, "pipelines_dir", None):
        os.environ["J2GHA_PIPELINES_DIR"] = str(Path(a.pipelines_dir).expanduser().resolve())
    if getattr(a, "offline", None):
        os.environ["J2GHA_OFFLINE"] = "1"
    return int(a.func(a) or 0)


if __name__ == "__main__":
    sys.exit(main())
