"""Workspace hand-off between split jobs (Phase 4, P4.3): jobs that Jenkins runs in the pipeline agent's one workspace
hand it on through `j2gha-ws-<job>` artifacts."""

import os
import shutil
import subprocess

import pytest

from handoff_sim import build, simulate
from j2gha.convert import workspace
from j2gha.convert.generator import convert
from j2gha.ir import Agent, Condition, Matrix, Pipeline, Stage, Step, When
from j2gha.runners.variants import make_variant


def sh(cmd):
    return Step("sh", args=[cmd])


def pipeline(stages, agent: str | None = "any", post=None, **options):
    return Pipeline(dialect="declarative", agent=Agent(agent) if agent else None, stages=stages,
                    options={"skipDefaultCheckout": True, **options}, post=post or {})


def jobs_of(ir):
    return convert(ir, "")["workflow"]["jobs"]


def handoff(job):
    return [s for s in job["steps"] if (s.get("_j2gha") or {}).get("role") == "handoff"]


def restored_from(job):
    return [s["with"]["name"].removeprefix("j2gha-ws-") for s in handoff(job) if s.get("uses", "").startswith(
        "actions/download-artifact")]


def hands_on(job):
    return any(s.get("uses", "").startswith("actions/upload-artifact") for s in handoff(job))


SPLIT = [
    Stage("Build", steps=[sh("make")]),
    Stage("Fan", parallel=[Stage("A", steps=[sh("test a")]),
                           Stage("B", agent=Agent("docker", image="node:20"), steps=[sh("test b")])]),
    Stage("Publish", steps=[sh("publish")]),
]
POST = {"always": [Step("archiveArtifacts", named={"artifacts": "out/*"})]}


def downloads(job):
    """{producer: the step's `if` (None: always downloaded)}"""
    return {s["with"]["name"].removeprefix("j2gha-ws-"): s.get("if") for s in handoff(job)
            if s.get("uses", "").startswith("actions/download-artifact")}


def test_jobs_in_the_pipeline_workspace_hand_it_on():
    jobs = jobs_of(pipeline(SPLIT, post=POST))
    assert hands_on(jobs["build"]) and restored_from(jobs["build"]) == []
    assert restored_from(jobs["fan-a"]) == ["build"] and hands_on(jobs["fan-a"])
    # a branch with its own agent has its own workspace in Jenkins too: nothing in, nothing out
    assert handoff(jobs["fan-b"]) == []
    # Publish needs both branches: A's workspace already holds Build's, so Build is only a fallback
    assert downloads(jobs["publish"]) == {"build": "(steps.j2gha-ws-fan-a.outcome != 'success')", "fan-a": None}
    # a workspace that was never uploaded (its job was skipped) must not fail the job: the fallback takes over
    assert all(s.get("continue-on-error") is True for s in handoff(jobs["publish"])
               if s.get("uses", "").startswith("actions/download-artifact"))
    assert downloads(jobs["post"])["publish"] is None
    # nothing restores Publish's workspace except the post job, so it does hand it on; post itself does not
    assert hands_on(jobs["publish"]) and not hands_on(jobs["post"])


def test_every_branch_is_always_restored():
    """Review finding 3: a download budget must never drop a branch (seven branches used to restore six). The
    branches' own change lists make the merge, so the workspace before them is only a fallback (follow-up 2)."""
    stages = [Stage("Build", steps=[sh("make")]),
              Stage("Fan", parallel=[Stage(f"B{i}", steps=[sh("true")]) for i in range(7)]),
              Stage("After", steps=[sh("ls")])]
    jobs = jobs_of(pipeline(stages))
    got = downloads(jobs["after"])
    assert {p: c for p, c in got.items() if p != "build"} == {f"fan-b{i}": None for i in range(7)}
    assert got["build"] == " || ".join(f"(steps.j2gha-ws-fan-b{i}.outcome != 'success')" for i in range(7))
    assert all(hands_on(jobs[f"fan-b{i}"]) for i in range(7))


def test_only_concurrent_producers_record_their_start_and_hand_on_their_changes():
    """A branch's changes are replayed onto another branch's workspace; a job nothing runs concurrently with is only
    ever restored whole."""
    def records(job):
        return any(s["name"] == "Record the starting workspace" for s in handoff(job))

    def uploaded(job):
        return next(s["with"]["path"] for s in handoff(job) if s.get("uses", "").startswith("actions/upload-artifact"))

    jobs = jobs_of(pipeline([Stage("Build", steps=[sh("make")]),
                             Stage("Fan", parallel=[Stage("A", steps=[sh("a")]), Stage("B", steps=[sh("b")])]),
                             Stage("After", steps=[sh("ls")])]))
    for jid in ("fan-a", "fan-b"):
        assert records(jobs[jid]) and uploaded(jobs[jid]) == ".j2gha-ws.tgz\n.j2gha-ws.changes"
        steps = [s.get("id") or s["name"] for s in jobs[jid]["steps"]]
        # the starting workspace is the restored one: recorded right after the merge (no checkout in this job)
        assert steps.index("Record the starting workspace") == steps.index(workspace.RESTORE_ID) + 1
    assert not records(jobs["build"]) and uploaded(jobs["build"]) == ".j2gha-ws.tgz"
    # SPLIT's B has its own agent: A runs concurrently with no other producer
    assert not records(jobs_of(pipeline(SPLIT))["fan-a"])


def test_fallback_downloads_are_deduplicated_and_capped_with_a_report(monkeypatch):
    monkeypatch.setattr(workspace, "MAX_HANDOFF_FALLBACKS", 1)
    chain = [Stage(f"S{i}", input={"message": "ok?"} if i else None, steps=[sh("true")]) for i in range(4)]
    out = convert(pipeline(chain, post=POST), "")
    post = out["workflow"]["jobs"]["post"]
    assert list(downloads(post)) == ["s3", "s2"]  # the nearest, then one fallback; s1, s0 left out
    assert any("workspace hand-off into 'post'" in i["jenkins"] and "not generated" in i["note"]
               for i in out["report"]["items"])
    from j2gha.validate.contexts import context_checks
    assert not [f for f in context_checks(out["workflow"]) if f["rule"] in ("handoff-source", "unknown-function")]


@pytest.mark.parametrize("ir", [
    pipeline(SPLIT, agent="none"),  # every stage has its own workspace in Jenkins
    pipeline(SPLIT, agent=None),
    pipeline([Stage("Only", steps=[sh("make")])]),  # one job: nothing to hand on
], ids=["agent-none", "no-agent", "single-job"])
def test_no_handoff_where_jenkins_shares_no_workspace(ir):
    assert not any(handoff(j) for j in jobs_of(ir).values())


def test_handoff_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("J2GHA_WORKSPACE_HANDOFF", "0")
    assert not any(handoff(j) for j in jobs_of(pipeline(SPLIT, post=POST)).values())
    items = convert(pipeline(SPLIT, post=POST), "")["report"]["items"]
    assert any("fresh workspace" in i["note"] and i["status"] == "approximated" for i in items)


def test_windows_pipelines_are_not_handed_on_yet():
    ir = pipeline(SPLIT)
    ir.agent = Agent("label", label="windows")
    assert not any(handoff(j) for j in jobs_of(ir).values())


def test_reuse_node_shares_the_pipeline_workspace():
    stages = [Stage("Build", steps=[sh("make")]),
              Stage("Test", agent=Agent("docker", image="python:3.12", reuse_node=True), input={"message": "ok?"},
                    steps=[sh("pytest")])]
    jobs = jobs_of(pipeline(stages))
    assert restored_from(jobs["test"]) == ["build"]


def test_matrix_cells_receive_the_workspace_but_do_not_hand_it_on():
    stages = [Stage("Build", steps=[sh("make")]),
              Stage("Cells", matrix=Matrix(axes={"OS": ["a", "b"]}, stages=[Stage("Run", steps=[sh("run")])])),
              Stage("After", steps=[sh("ls")])]
    jobs = jobs_of(pipeline(stages))
    assert restored_from(jobs["cells"]) == ["build"] and not hands_on(jobs["cells"])
    assert restored_from(jobs["after"]) == ["build"]


def test_a_restored_workspace_replaces_the_checkout():
    ir = pipeline(SPLIT)
    ir.options = {}  # Declarative's implicit checkout
    jobs = jobs_of(ir)
    co = next(s for s in jobs["fan-a"]["steps"] if (s.get("_j2gha") or {}).get("role") == "checkout")
    assert "steps.j2gha-ws-restore.outputs.restored != 'true'" in co["if"]
    # the first job's checkout carries Jenkins' implicit checkout event: untouched
    first = next(s for s in jobs["build"]["steps"] if (s.get("_j2gha") or {}).get("role") == "checkout")
    assert "if" not in first


def test_a_gate_decides_in_the_restored_workspace():
    stages = [Stage("Build", steps=[sh("make")]),
              Stage("Deploy", when=When(conditions=[Condition("expression", "fileExists('out/app')")],
                                         before_input=True),
                    input={"message": "Deploy?"}, steps=[sh("deploy")])]
    out = convert(pipeline(stages), "")
    jobs = out["workflow"]["jobs"]
    assert restored_from(jobs["deploy-gate"]) == ["build"] and not hands_on(jobs["deploy-gate"])
    assert restored_from(jobs["deploy"]) == ["build"]
    assert any("restored pipeline workspace" in i["note"] for i in out["report"]["items"])


def test_post_job_reads_the_restored_workspace_and_says_so():
    items = convert(pipeline(SPLIT, post=POST), "")["report"]["items"]
    (ws,) = [i for i in items if "workspace-dependent" in i["jenkins"]]
    assert ws["status"] == "mapped" and "restored pipeline workspace" in ws["note"]
    (split,) = [i for i in items if "parallel jobs" in i["gha"]]
    assert split["status"] == "approximated" and "do not see each other's files" in split["note"]


def test_trace_variants_are_unchanged_by_the_handoff(monkeypatch):
    """Trace parity: the hand-off is conversion-only, so the trace variant is the same with and without it."""
    def trace_variant():
        v, _ = make_variant(convert(pipeline(SPLIT, post=POST), "")["workflow"], "trace", "act", {"branch": "main"})
        return {jid: [s["run"] for s in j["steps"]] for jid, j in v["jobs"].items()}
    with_handoff = trace_variant()
    monkeypatch.setenv("J2GHA_WORKSPACE_HANDOFF", "0")
    assert with_handoff == trace_variant()


@pytest.mark.skipif(not shutil.which("tar"), reason="needs tar")
def test_the_generated_scripts_hand_on_files_modes_and_symlinks(tmp_path):
    """Run the generated steps (handoff_sim): what Build leaves is what Publish starts with."""
    jobs = jobs_of(pipeline([
        Stage("Build", steps=[sh("mkdir out && echo built > out/app && chmod 755 out/app && ln -s out/app latest && "
                                 "echo dotfile > .hidden")]),
        Stage("Publish", input={"message": "ok?"}, steps=[sh("true")])]))
    upload = next(s for s in handoff(jobs["build"]) if s.get("uses", "").startswith("actions/upload-artifact"))
    assert upload["with"]["include-hidden-files"] is True
    ws = simulate(jobs, build(tmp_path / "initial", {}))["publish"]
    assert ws["out/app"] == ("f", "0o755", b"built\n") and ws["latest"] == ("l", "out/app")
    assert ws[".hidden"][2] == b"dotfile\n"


def test_nothing_downloaded_means_not_restored(tmp_path):
    jobs = jobs_of(pipeline(SPLIT, post=POST))
    merge = next(s for s in handoff(jobs["publish"]) if s.get("id") == workspace.RESTORE_ID)
    out = tmp_path / "github-output"
    env = {**os.environ, **merge["env"], "GITHUB_WORKSPACE": str(tmp_path), "GITHUB_OUTPUT": str(out)}
    subprocess.run(["bash", "-e", "-c", merge["run"]], cwd=tmp_path, env=env, check=True)
    assert out.read_text().strip() == "restored=false"


def test_restoring_a_workspace_from_a_job_not_needed_is_a_structural_error():
    from j2gha.validate.contexts import context_checks
    wf = {"jobs": jobs_of(pipeline(SPLIT, post=POST))}
    assert not [f for f in context_checks(wf) if f["rule"] == "handoff-source"]
    wf["jobs"]["fan-a"]["needs"] = []  # A no longer waits for Build
    wf["jobs"]["publish"]["steps"] = [s for s in wf["jobs"]["publish"]["steps"]
                                      if not s.get("uses", "").startswith("actions/upload-artifact")]
    rules = [f["message"] for f in context_checks(wf) if f["rule"] == "handoff-source"]
    assert any("'fan-a' restores 'j2gha-ws-build'" in m for m in rules)
    assert any("'j2gha-ws-publish', which no job uploads" in m for m in rules)


# the merge step, executed against Jenkins' one workspace: test_handoff_model.py


def test_restore_steps_only_test_the_outcome_of_earlier_steps():
    """A fallback's `if:` reads `steps.<id>.outcome` of the downloads it falls back from: they must come first
    (actionlint rejects the workflow otherwise)."""
    import re
    chain = [Stage("S0", steps=[sh("true")]),
             Stage("Fan", parallel=[Stage("A", steps=[sh("a")]), Stage("B", steps=[sh("b")])]),
             *[Stage(f"S{i}", input={"message": "ok?"}, steps=[sh("true")]) for i in (1, 2)]]
    for job in jobs_of(pipeline(chain, post=POST)).values():
        seen = set()
        for st in job["steps"]:
            for ref in re.findall(r"steps\.([\w-]+)\.", str(st.get("if", ""))):
                assert ref in seen, (job["name"], st["name"], ref)
            seen.add(st.get("id"))


# ---------------------------------------------------- the migration report (third review of Phase 4: prerequisites)
FAN = [Stage("Build", steps=[sh("make")]),
       Stage("Fan", parallel=[Stage("A", steps=[sh("a")]), Stage("B", steps=[sh("b")])]),
       Stage("After", steps=[sh("ls")])]


def report_text(ir):
    from j2gha.render import migration_report
    out = convert(ir, "")
    analysis = {"complexity": {"classification": "assisted", "score": 1}, "convertibility": "automatic",
                "coverage": {"weighted_mapped_pct": 100}, "findings": []}
    return out["report"], migration_report({}, analysis, out["report"], ir)


def test_the_migration_report_states_the_handoffs_requirements_and_limits():
    report, text = report_text(pipeline(FAN))
    assert report["handoff"] == {"handed_on": ["build", "fan-a", "fan-b"], "merged": ["fan-a", "fan-b"],
                                 "restored_by": ["fan-a", "fan-b", "after"]}
    section = text.split("## Workspace hand-off")[1].split("\n## ")[0]
    for words in ("Runtime requirements:** bash, GNU tar", "busybox/Alpine", "Same as Jenkins", "Approximated",
                  "later branch's version", "Fails instead", "with a warning", "`fan-a`, `fan-b`"):
        assert words in section, words
    assert "hand its workspace on (see *Workspace hand-off*)" in text


def test_without_the_handoff_the_report_says_jobs_share_no_workspace(monkeypatch):
    monkeypatch.setenv("J2GHA_WORKSPACE_HANDOFF", "0")
    report, text = report_text(pipeline(FAN))
    assert not report["handoff"] and "## Workspace hand-off" not in text
    assert "They do **not** share a workspace" in text


def test_a_busybox_or_alpine_job_container_is_a_manual_item():
    """The hand-off steps need bash and GNU tools: said at conversion time, not found by a failing run."""
    ir = pipeline(FAN)
    ir.agent = Agent("docker", image="node:20-alpine")
    items = [i for i in convert(ir, "")["report"]["items"] if "hand-off in container" in i["jenkins"]]
    assert [(i["status"], i["jenkins"]) for i in items] == [("manual", "workspace hand-off in container 'node:20-alpine'")]
    ir.agent = Agent("docker", image="node:20-bookworm")
    assert not [i for i in convert(ir, "")["report"]["items"] if "hand-off in container" in i["jenkins"]]
