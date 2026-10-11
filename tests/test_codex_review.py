"""Regression tests for the defects found by the Codex assessment of the converter and harness. A finding that is still open belongs here as
`xfail(strict=True, reason=OPEN.format(<n>))`: it fails today and turns into an error (XPASS) the moment the fix
lands, so the marker goes with the fix.
"""

import itertools
import re
import subprocess

import pytest

from conftest import load
from test_convert import _gha_if
from j2gha.analysis.analyze import analyse
from j2gha.analysis.declarative import build_ir
from j2gha.convert.expressions import glob_condition
from j2gha.convert.generator import convert
from j2gha.gha.remote import _timed_traces
from j2gha.ir import Agent, Condition, EnvValue, Parameter, Pipeline, Stage, Step, When
from j2gha.runners.execute import compare_outcome, reference_problem, stale_reason
from j2gha.runners.variants import make_variant
from j2gha.trace import compare, order_violations, stage_order

OPEN = "codex-assessment #{}: not fixed yet"


@pytest.fixture(autouse=True)
def no_workspace_handoff(monkeypatch):
    """These tests check the job structure without the workspace hand-off (Phase 4, P4.3: tests/test_handoff.py);
    the cross product in tests/test_contexts.py runs with it."""
    monkeypatch.setenv("J2GHA_WORKSPACE_HANDOFF", "0")


def ev(*pairs):
    return [{"stage": s, "step": st} for s, st in pairs]


def steps_of(wf):
    return [s for j in wf["jobs"].values() for s in j["steps"]]


def probes():
    text, ast = load("probes")
    return text, ast


# ------------------------------------------------------------------------------------- #1 container confinement
def _container_options(options):
    ir = Pipeline(dialect="declarative", agent=Agent("docker", image="alpine:3", args=options),
                  stages=[Stage("Build", steps=[Step("sh", args=["echo hi"])])])
    wf = convert(ir, "")["workflow"]
    variant, notes = make_variant(wf, "full", "act", {"branch": "main"})
    converted = wf["jobs"]["build"]["container"].get("options")
    return variant["jobs"]["build"]["container"].get("options"), notes.get("dropped_container_options", {}), converted


@pytest.mark.parametrize("options", [
    "-v /var/run/docker.sock:/var/run/docker.sock",
    "-v/var/run/docker.sock:/var/run/docker.sock",  # attached value
    "--volume=/var/run/docker.sock:/var/run/docker.sock",
    "-itv/var/run/docker.sock:/var/run/docker.sock",  # flag cluster ending in an option
    "--mount type=bind,src=/,dst=/host",
    "--privileged", "--cap-add SYS_ADMIN", "--network host", "--pid=host", "--device /dev/sda", "--env-file /etc/env",
    "-e HOME",  # copies the host's value
    "--some-future-option value",  # unknown options are dropped, not kept
])
def test_host_reaching_container_options_are_dropped_however_spelled(options):
    kept, dropped, converted = _container_options(options)
    assert kept is None, kept
    assert dropped.get("build") or not converted, "a drop in the execution variant is recorded"


def test_harmless_container_options_survive():
    kept, dropped, _ = _container_options("--user 0 -e A=b -w /src --init -v/x:/y")
    assert kept == "--user 0 -e A=b -w /src --init"
    assert dropped["build"] == "-v/x:/y"


# ------------------------------------------------------------------------------------------ #3 glob conditions
def _ant(pattern, value):
    """Reference Ant `matchPath` for the pattern shapes the converter handles (Jenkins' GLOB comparator)."""
    if pattern.endswith("/**") and value == pattern[:-3]:
        return True
    rx = re.escape(pattern).replace(r"\*\*", "\0").replace(r"\*", "[^/]*").replace(r"\?", "[^/]").replace("\0", ".*")
    return re.fullmatch(rx, value) is not None


NAMES = ["main", "release", "release/", "release/1.0", "release/1/2", "feature", "feature/a/b", "prod", "xprod",
         "xprod?", "a", "ac", "acb", "acbc", "abc", "aXbYc", "v1", "v1.0", "v1/x", "v", "a/b", "x/main", "x/y/main"]


@pytest.mark.parametrize("pattern", ["release/*", "release/**", "feature*", "v*", "*", "**", "*prod", "*-rc", "*/main",
                                     "*prod?", "a*b*c", "a?c", "release-?.*", "x*/main", "release/*/x"])
def test_glob_translation_is_exact_or_manual(pattern):
    expr, status = glob_condition("env.B", pattern)
    if status == "manual":
        # an unset gate keeps the stage off: it can never run where Jenkins would not run it
        assert all(not _gha_if(expr, {"B": n}) for n in NAMES)
        return
    for name in NAMES:
        got, want = _gha_if(expr, {"B": name}), _ant(pattern, name)
        if status == "mapped":
            assert got == want, (pattern, name, expr)
        else:
            assert status == "approximated"
            assert got or not want, f"{expr} is narrower than Jenkins for {name!r}"  # may widen, never narrow


def test_the_only_approximated_glob_is_a_prefix_with_a_slash():
    assert glob_condition("env.B", "release/*")[1] == "approximated"
    assert glob_condition("env.B", "release-*")[1] == "mapped"
    assert _gha_if(glob_condition("env.B", "release/*")[0], {"B": "release/1/2"})  # the known widening


GHA_FUNCTIONS = {"contains", "startsWith", "endsWith", "format", "join", "toJSON", "fromJSON", "hashFiles",
                 "always", "failure", "success", "cancelled"}


@pytest.mark.parametrize("pattern", ["release/*", "release/**", "feature*", "v*", "*", "**", "*prod", "*-rc", "x/*"])
def test_glob_expressions_only_use_functions_github_has(pattern):
    """GitHub has no `substring`: act and GitHub reject a workflow that calls it (actionlint did not)."""
    used = set(re.findall(r"\b([A-Za-z]\w*)\(", glob_condition("env.B", pattern)[0]))
    assert used <= GHA_FUNCTIONS, used


@pytest.mark.parametrize("pattern", ["release/*", "release/**", "*", "**", "v*", "*-rc"])
def test_an_unset_branch_or_tag_matches_no_pattern(pattern):
    """TAG_NAME is empty outside tag builds: `tag 'v*'` must not run there (Jenkins: no tag, no match)."""
    assert not _gha_if(glob_condition("env.B", pattern)[0], {})


@pytest.mark.parametrize("pattern", ["a*b*c", "*prod?", "a?c", "*/main"])
def test_patterns_without_an_exact_expression_need_a_manual_gate(pattern):
    assert glob_condition("env.B", pattern, line=7) == ("vars.J2GHA_WHEN_L7 == 'true'", "manual")


# ------------------------------------------------------------------------------------------- #2 stage ordering
def _tiered():
    return Pipeline(dialect="declarative", stages=[
        Stage("Build"), Stage("Test", parallel=[Stage("Unit"), Stage("Lint")]), Stage("Deploy")])


def _branchy():
    """Left: BuildA -> TestA (sequential inside one branch), Right: one stage; then Deploy."""
    return Pipeline(dialect="declarative", stages=[
        Stage("Build"),
        Stage("Par", parallel=[Stage("Left", stages=[Stage("BuildA"), Stage("TestA")]), Stage("Right")]),
        Stage("Deploy")])


def test_stage_order_comes_from_the_original_pipeline():
    pairs = set(stage_order(_tiered()))
    assert {("Build", "Unit"), ("Build", "Lint"), ("Unit", "Deploy"), ("Lint", "Deploy"), ("Build", "Deploy")} <= pairs
    assert ("Unit", "Lint") not in pairs and ("Lint", "Unit") not in pairs  # branches are unordered
    assert stage_order(None) == []
    nested = Pipeline(dialect="declarative", stages=[Stage("A", stages=[Stage("A1"), Stage("A2")]), Stage("B")])
    assert set(stage_order(nested)) == {("A1", "A2"), ("A1", "B"), ("A2", "B")}
    gstring = Pipeline(dialect="declarative", stages=[Stage("Build"), Stage("${OS} test"), Stage("Build")])
    assert stage_order(gstring) == []  # runtime names and duplicates cannot be told apart in a trace


def test_sequential_stages_inside_a_parallel_branch_stay_ordered_between_branches_they_do_not():
    pairs = set(stage_order(_branchy()))
    assert ("BuildA", "TestA") in pairs and ("TestA", "BuildA") not in pairs
    assert not {("BuildA", "Right"), ("Right", "BuildA"), ("TestA", "Right"), ("Right", "TestA")} & pairs
    order = stage_order(_branchy())
    ref = ev(("Build", "sh"), ("BuildA", "sh"), ("TestA", "sh"), ("Right", "sh"), ("Deploy", "sh"))
    reversed_in_branch = ev(("Build", "sh"), ("TestA", "sh"), ("BuildA", "sh"), ("Right", "sh"), ("Deploy", "sh"))
    c = compare(ref, reversed_in_branch, "SUCCESS", "success", order=order)
    assert c["verdict"] == "differs" and c["order_violations"] == [["BuildA", "TestA"]]
    interleaved = ev(("Build", "sh"), ("Right", "sh"), ("BuildA", "sh"), ("TestA", "sh"), ("Deploy", "sh"))
    assert compare(ref, interleaved, "SUCCESS", "success", order=order)["verdict"] == "equivalent"


def test_matrix_cells_interleave_their_inner_stages():
    from j2gha.ir import Matrix
    ir = Pipeline(dialect="declarative", stages=[
        Stage("Build"), Stage("M", matrix=Matrix(axes={"OS": ["a", "b"]}, stages=[Stage("Compile"), Stage("Check")])),
        Stage("Deploy")])
    pairs = set(stage_order(ir))
    assert ("Build", "Compile") in pairs and ("Check", "Deploy") in pairs
    assert ("Compile", "Check") not in pairs and ("Check", "Compile") not in pairs  # cell 1 can be at Check, cell 2 at Compile


def test_reversed_sequential_stages_are_not_equivalent():
    ref = ev(("Build", "sh"), ("Deploy", "sh"))
    order = [("Build", "Deploy")]
    c = compare(ref, list(reversed(ref)), "SUCCESS", "success", order=order)
    assert c["verdict"] == "differs" and not c["equivalent"]
    assert c["order_violations"] == [["Build", "Deploy"]]
    assert {r["stage"]: r["status"] for r in c["stages"]} == {"Build": "out-of-order", "Deploy": "out-of-order"}
    assert compare(ref, ref, "SUCCESS", "success", order=order)["verdict"] == "equivalent"


def test_parallel_branches_may_interleave_but_not_cross_the_sequence():
    order = stage_order(_tiered())
    ref = ev(("Build", "sh"), ("Unit", "sh"), ("Lint", "sh"), ("Deploy", "sh"))
    swapped = ev(("Build", "sh"), ("Lint", "sh"), ("Unit", "sh"), ("Deploy", "sh"))
    assert compare(ref, swapped, "SUCCESS", "success", order=order)["verdict"] == "equivalent"
    early = ev(("Build", "sh"), ("Unit", "sh"), ("Deploy", "sh"), ("Lint", "sh"))
    assert compare(ref, early, "SUCCESS", "success", order=order)["verdict"] == "differs"


def test_order_violations_ignore_stages_that_did_not_run():
    assert order_violations(ev(("Deploy", "sh")), [("Build", "Deploy")]) == []
    assert order_violations(ev(("Deploy", "sh"), ("Build", "sh")), [("Build", "Deploy")]) == [("Build", "Deploy")]


def test_an_order_the_reference_itself_breaks_is_not_held_against_the_candidate():
    ref = ev(("Deploy", "sh"), ("Build", "sh"))  # the model of the pipeline is wrong, not the candidate
    assert compare(ref, ref, "SUCCESS", "success", order=[("Build", "Deploy")])["verdict"] == "equivalent"


def test_remote_job_logs_are_merged_by_timestamp_not_by_job_name():
    line = 'printf J2GHA-TRACE {"stage":"%s","step":"sh"}'

    def log(stage, ts):
        return f'{ts} J2GHA-TRACE {{"stage":"{stage}","step":"sh"}}\n'
    logs = {"a-deploy.txt": log("Deploy", "2025-01-01T00:00:09.1000000Z"),
            "z-build.txt": log("Build", "2025-01-01T00:00:01.5000000Z")}
    assert [e["stage"] for e in _timed_traces(logs)] == ["Build", "Deploy"]
    assert line  # (documents the marker shape the helper parses)


# ----------------------------------------------------------------------------------------------- open findings
def _when_if(kind, expression, default="x"):
    ir = Pipeline(dialect="declarative", parameters=[Parameter(kind, "P", default=default)],
                  stages=[Stage("S", when=When([Condition("expression", text=expression, line=4)]),
                                steps=[Step("echo", args=["x"])])])
    entry = next(s for s in steps_of(convert(ir, "")["workflow"]) if s["_j2gha"]["kind"] == "stage-entry")
    return entry["if"]


@pytest.mark.parametrize("kind, expression, expected", [
    ("booleanParam", "params.P", "env.P == 'true'"),
    ("booleanParam", "!params.P", "env.P != 'true'"),
    # a string is true when non-empty: the string "false" and "1.4.0" both run the stage
    ("string", "params.P", "env.P != ''"),
    ("string", "!params.P", "env.P == ''"),
    ("choice", "params.P", "env.P != ''"),
    ("string", "params.P.trim() == 'prod'", "vars.J2GHA_WHEN_L4 == 'true'"),  # trim() cannot be preserved
    ("string", "params.OTHER", "vars.J2GHA_WHEN_L4 == 'true'"),  # not a declared parameter: type unknown
])
def test_parameter_truth_follows_the_declared_type(kind, expression, expected):
    assert _when_if(kind, expression) == expected


def test_case_changing_string_methods_are_harmless_because_github_ignores_case():
    from j2gha.convert.expressions import translate_groovy
    assert translate_groovy("env.TARGET.toLowerCase() == 'prod'") == "env.TARGET == 'prod'"


def test_trim_is_not_silently_dropped():
    from j2gha.convert.expressions import translate_groovy
    assert translate_groovy("env.TARGET.trim() == 'prod'") is None


def _before_input_pipeline(**kw):
    return Pipeline(dialect="declarative", agent=Agent("any"),
                    environment={"FLAG": EnvValue("shell", "if test -f deploy.enabled; then printf yes; else printf no; fi")},
                    stages=[Stage("Build", steps=[Step("echo", args=["b"])]),
                            Stage("Deploy", when=When([Condition("expression", text="env.FLAG == 'yes'")],
                                                      before_input=True),
                                  input={"message": "Deploy?"}, environment={"X": EnvValue("literal", "1")},
                                  steps=[Step("echo", args=["d"])]),
                            Stage("After", steps=[Step("echo", args=["a"])])], **kw)


def test_before_input_condition_is_evaluated_before_the_protected_environment():
    jobs = convert(_before_input_pipeline(), "")["workflow"]["jobs"]
    gate, stage = jobs["deploy-gate"], jobs["deploy"]
    # the stage job is the protected job (so its environment secrets are available) and a skipped gate skips it
    # before any reviewer is asked: job-level `if` may only read `needs`
    assert stage["environment"] == "Deploy" and "deploy-gate" in stage["needs"]
    assert stage["if"] == "needs.deploy-gate.outputs.run == 'true'"
    assert "environment" not in gate and gate["outputs"] == {"run": "${{ steps.%s.outputs.run }}" % gate["steps"][-1]["id"]}
    assert not any(s.get("_j2gha", {}).get("kind") == "input" for j in (gate,) for s in j["steps"])
    assert any(s.get("_j2gha", {}).get("kind") == "input" for s in stage["steps"])
    assert "deploy-input" not in jobs


def test_a_gated_stage_uses_the_gates_decision_and_never_evaluates_when_again():
    """F1: the gate and the stage must not decide separately (they would see different checkouts/environments)."""
    jobs = convert(_before_input_pipeline(), "")["workflow"]["jobs"]
    gate, stage = jobs["deploy-gate"], jobs["deploy"]
    # the gate sees what the stage sees: the same checkout and the same computed environment
    assert [s["_j2gha"]["kind"] for s in gate["steps"]] == ["checkout", "environment", "stage-entry"]
    assert gate["steps"][2]["if"] == "env.FLAG == 'yes'"
    entry = next(s for s in stage["steps"] if s["_j2gha"]["kind"] == "stage-entry")
    assert entry["if"] == "needs.deploy-gate.outputs.run == 'true'"
    assert not any("env.FLAG" in s.get("if", "") for s in stage["steps"])
    # a stage after a skippable one tolerates the skip
    assert jobs["after"]["if"] == "!failure() && !cancelled()"
    assert "if" not in jobs["build"]


def test_parallel_stage_with_before_input_gates_every_branch_job():
    ir = Pipeline(dialect="declarative", options={"skipDefaultCheckout": True}, stages=[
        Stage("Deploy", when=When([Condition("expression", text="env.X == 'y'")], before_input=True),
              input={"message": "Go?"},
              parallel=[Stage("A", steps=[Step("echo", args=["a"])]), Stage("B", steps=[Step("echo", args=["b"])])])])
    jobs = convert(ir, "")["workflow"]["jobs"]
    assert jobs["deploy-input"]["if"] == "needs.deploy-gate.outputs.run == 'true'" and jobs["deploy-input"]["environment"]
    for branch in ("deploy-a", "deploy-b"):
        job = jobs[branch]
        assert "deploy-gate" in job["needs"] and "deploy-input" in job["needs"]
        assert job["if"] == "!failure() && !cancelled() && needs.deploy-gate.outputs.run == 'true'"
        entry = next(s for s in job["steps"] if s["_j2gha"]["kind"] == "stage-entry")
        assert entry["if"] == "needs.deploy-gate.outputs.run == 'true'"


def test_input_without_before_input_keeps_the_environment_on_the_stage_job():
    """Jenkins asks for approval before evaluating `when`: the protected job is the stage's own job."""
    ir = Pipeline(dialect="declarative", options={"skipDefaultCheckout": True}, stages=[
        Stage("Deploy", when=When([Condition("branch", value="main")]), input={"message": "Deploy?"},
              steps=[Step("echo", args=["d"])])])
    (job,) = convert(ir, "")["workflow"]["jobs"].values()
    assert job["environment"] == "Deploy" and "if" not in job


def test_dir_checkout_goes_into_the_directory():
    text, ast = probes()
    ir = build_ir(ast)
    assert ir is not None
    wf = convert(ir, text)["workflow"]
    checkouts = [s for s in steps_of(wf) if s.get("uses", "").startswith("actions/checkout") and s.get("name") != "Checkout"]
    assert checkouts and checkouts[0]["with"].get("path") == "new/subdir"
    mkdir = next(s for s in steps_of(wf) if s.get("_j2gha", {}).get("kind") == "dir")
    assert mkdir["env"] == {"J2GHA_DIR": "new/subdir"} and mkdir["run"].startswith("mkdir -p")
    pwd = next(s for s in steps_of(wf) if s.get("run") == "pwd")
    assert pwd["working-directory"] == "new/subdir"


def test_helper_argument_used_as_a_plain_variable_is_substituted():
    text, ast = probes()
    ir = build_ir(ast)
    assert ir is not None
    wf = convert(ir, text)["workflow"]
    runs = [s["run"] for s in steps_of(wf) if "run" in s]
    assert "echo hello" in runs and "target" not in runs
    echo = next(s["run"] for s in steps_of(wf) if s.get("_j2gha", {}).get("kind") == "echo")
    assert echo == 'echo "echo hello"'


def test_helper_argument_that_is_a_caller_variable_stays_a_variable():
    from j2gha.ir import Step
    helper = {"params": ["target"], "body": [Step("sh", args=["target"], dynamic=True, variable_args=[0])]}
    ir = Pipeline(dialect="declarative", options={"skipDefaultCheckout": True}, method_defs={"deploy": helper},
                  stages=[Stage("S", steps=[Step("deploy", args=["cmd"], dynamic=True, variable_args=[0])])])
    run = next(s["run"] for s in steps_of(convert(ir, "")["workflow"]) if s.get("_j2gha", {}).get("kind") == "sh")
    assert "target" not in run


def test_computed_pipeline_environment_reaches_the_post_job():
    sh = Step("sh", args=["true"])
    ir = Pipeline(dialect="declarative", environment={"LABEL": EnvValue("shell", "echo hi")},
                  stages=[Stage("A", agent=Agent("label", label="x"), steps=[sh]),
                          Stage("B", agent=Agent("label", label="y"), steps=[sh])],
                  post={"always": [Step("echo", args=["${LABEL}"])]})
    post = convert(ir, "")["workflow"]["jobs"]["post"]
    assert any(s.get("_j2gha", {}).get("kind") == "environment" for s in post["steps"])



@pytest.mark.parametrize("text, expected", [pytest.param("abc", b"abc"),
                                            pytest.param("abc\n", b"abc\n"), pytest.param("", b""),
                                            pytest.param("a'b $HOME \\n\n\n", b"a'b $HOME \\n\n\n")])
def test_write_file_preserves_content_exactly(tmp_path, text, expected):
    ir = Pipeline(dialect="declarative", options={"skipDefaultCheckout": True}, stages=[
        Stage("W", steps=[Step("writeFile", named={"file": "out.txt", "text": text})])])
    run = next(s["run"] for s in steps_of(convert(ir, "")["workflow"]) if s.get("_j2gha", {}).get("kind") == "writeFile")
    subprocess.run(["bash", "-eo", "pipefail", "-c", run], cwd=tmp_path, check=True)
    assert (tmp_path / "out.txt").read_bytes() == expected


@pytest.mark.parametrize("value", ["1.2", "abc\n", "abc\n\n", "", "a b\n\n\n"])
@pytest.mark.parametrize("template, expect", [("v=${VERSION}", "v=%s"), ("${VERSION}", "%s"), ("v=${VERSION} $5", "v=%s $5"),
                                              ("${VERSION}\n", "%s\n")])
def test_write_file_gstring_keeps_interpolation_and_every_trailing_newline(tmp_path, value, template, expect):
    ir = Pipeline(dialect="declarative", options={"skipDefaultCheckout": True}, stages=[
        Stage("W", steps=[Step("writeFile", named={"file": "out.txt", "text": template}, dynamic=True)])])
    run = next(s["run"] for s in steps_of(convert(ir, "")["workflow"]) if s.get("_j2gha", {}).get("kind") == "writeFile")
    subprocess.run(["bash", "-eo", "pipefail", "-c", run], cwd=tmp_path, check=True,
                   env={"VERSION": value, "PATH": "/usr/bin:/bin"})
    assert (tmp_path / "out.txt").read_bytes() == (expect % value).encode()


@pytest.mark.parametrize("event, supplied, expected", [("push", "", None), ("workflow_dispatch", "", ""),
                                                       ("workflow_dispatch", "qa", "qa")])
@pytest.mark.parametrize("default", ["prod", ""])
def test_explicitly_empty_dispatch_input_does_not_revert_to_the_default(event, supplied, expected, default):
    ir = Pipeline(dialect="declarative", parameters=[Parameter("string", "TARGET", default=default)],
                  stages=[Stage("Build", steps=[Step("echo", args=["ok"])])])
    expr = convert(ir, "")["workflow"]["env"]["TARGET"].removeprefix("${{ ").removesuffix(" }}")
    # GitHub's && / || return an operand and treat '' as false, exactly like Python's and / or
    py = re.sub(r"format\('\{0\}', (inputs\.\w+)\)", r"\1", expr).replace("&&", " and ").replace("||", " or ")
    value = eval(py, {}, {"github": type("G", (), {"event_name": event}), "inputs": type("I", (), {"TARGET": supplied})})  # noqa: S307
    assert value == (default if expected is None else expected), (expr, value)


def test_outdated_localizer_version_invalidates_the_reference():
    from j2gha.jenkins.localize import LOCALIZER_VERSION
    from j2gha.provenance import jenkinsfile_sha256
    ref = {"result": "SUCCESS", "traces": [{"stage": "a", "step": "sh"}],
           "provenance": {"jenkinsfile_sha256": "x", "scenario": {"branch": "main"},
                          "localizer_version": LOCALIZER_VERSION - 1}}
    assert reference_problem(ref, {"jenkinsfile_sha256": "x", "scenario": {"branch": "main"}})
    assert jenkinsfile_sha256  # imported for symmetry with the model-hash test


def test_editing_the_model_after_the_run_makes_the_record_stale(tmp_path):
    import json
    from j2gha.provenance import jenkinsfile_sha256, sha256_json
    (tmp_path / "gha").mkdir()
    (tmp_path / "Jenkinsfile").write_text("source")
    model = {"jobs": {"build": {"steps": [{"run": "true"}]}}}
    digest = sha256_json(model)
    (tmp_path / "gha" / "conversion.json").write_text(
        json.dumps({"source_sha256": jenkinsfile_sha256(tmp_path), "model_sha256": digest}))
    model["jobs"]["build"]["steps"][0]["run"] = "false"
    (tmp_path / "gha" / "workflow.model.json").write_text(json.dumps(model))
    rec = {"provenance": {"jenkinsfile_sha256": jenkinsfile_sha256(tmp_path), "model_sha256": digest}}
    assert stale_reason(tmp_path, rec, "act")


def test_script_if_condition_is_decided_once():
    pipe = Pipeline(dialect="declarative", options={"skipDefaultCheckout": True}, stages=[Stage("Build", steps=[
        Step("script", body=[Step("<if>", source="env.TARGET == 'prod'",
                                  body=[Step("sh", args=['echo TARGET=dev >> "$GITHUB_ENV"']), Step("echo", args=["then"])],
                                  named={"_else": [Step("echo", args=["else"])]})])])])
    steps = steps_of(convert(pipe, "")["workflow"])
    yes, no = [s for s in steps if s["_j2gha"]["kind"] == "if-decision"]
    assert yes["if"] == "env.TARGET == 'prod'" and no["if"] == f"steps.{yes['id']}.outcome == 'skipped'"
    ifs = [s.get("if", "") for s in steps if s["_j2gha"]["kind"] != "if-decision"]
    assert not any("env.TARGET" in i for i in ifs), ifs  # later steps read the one decision, not the changed variable
    assert ifs == [f"steps.{yes['id']}.outputs.taken == 'true'"] * 2 + [f"steps.{no['id']}.outputs.taken == 'false'"]
    # a lone step cannot be affected by its own re-evaluation: no extra step
    one = Pipeline(dialect="declarative", options={"skipDefaultCheckout": True}, stages=[Stage("B", steps=[
        Step("script", body=[Step("<if>", source="env.TARGET == 'prod'", body=[Step("echo", args=["x"])])])])])
    assert [s.get("if") for s in steps_of(convert(one, "")["workflow"])] == ["env.TARGET == 'prod'"]


def test_full_runs_without_any_stage_data_are_inconclusive():
    c = compare_outcome({"result": "SUCCESS", "stages": []}, {"result": "success", "jobs": []}, {})
    assert c["verdict"] == "inconclusive" and "neither run reports" in c["inconclusive"]["reason"]
    ran = compare_outcome({"result": "SUCCESS", "stages": [{"name": "Build"}]}, {"result": "success", "jobs": [{}]}, {})
    assert ran["verdict"] == "equivalent"
    # an infrastructure state is reported as such even without stage data
    assert "did not finish" in compare_outcome({"result": "NOT_RUN"}, {"result": "success"}, {})["inconclusive"]["reason"]


def test_gaps_counts_an_unknown_step_once(tmp_path):
    import json
    from j2gha.improve import gaps
    text, ast = probes()
    analysis = analyse(text, ast)
    (tmp_path / "999" / "analysis").mkdir(parents=True)
    (tmp_path / "999" / "analysis" / "analysis.json").write_text(json.dumps(analysis))
    row = next(r for r in gaps(["999"], tmp_path, include_holdout=True) if r["step"] == "rocketSend")
    assert row["count"] == 1


def test_probe_fixture_is_the_codex_reproduction():
    text, ast = probes()
    assert ast["ok"] and "rocketSend" in text
    assert list(itertools.islice(iter(ast["methods"]), 1))[0]["name"] == "deploy"


# ----------------------------------------------------------------------------------- scenario parameters (--param)
def test_scenario_parameters_are_part_of_the_scenario_and_override_the_workflow_env():
    from j2gha.runners.execute import scenario_for
    assert scenario_for({}, "main") == {"branch": "main", "git_branch": "origin/main"}  # old records stay valid
    scenario = scenario_for({}, "main", {"B": "2", "A": "1"})
    assert scenario["params"] == {"A": "1", "B": "2"}
    ir = Pipeline(dialect="declarative", parameters=[Parameter("string", "TARGET", default="prod")],
                  stages=[Stage("S", steps=[Step("echo", args=["x"])])])
    wf = convert(ir, "")["workflow"]
    variant, _ = make_variant(wf, "trace", "act", scenario_for({}, "main", {"TARGET": "qa", "NOPE": "x"}))
    assert variant["env"]["TARGET"] == "qa" and "NOPE" not in variant["env"]
    assert "qa" not in wf["env"]["TARGET"], "the model itself is untouched"


def test_a_reference_run_with_other_parameters_is_refused():
    from j2gha.jenkins.localize import LOCALIZER_VERSION
    ref = {"result": "SUCCESS", "traces": [{"stage": "a", "step": "sh"}],
           "provenance": {"jenkinsfile_sha256": "x", "localizer_version": LOCALIZER_VERSION,
                          "scenario": {"branch": "main", "git_branch": "origin/main", "params": {"A": "1"}}}}
    base = {"jenkinsfile_sha256": "x", "scenario": {"branch": "main", "git_branch": "origin/main"}}
    assert reference_problem(ref, base) is not None
    assert reference_problem(ref, {**base, "scenario": ref["provenance"]["scenario"]}) is None


def test_param_option_syntax():
    import argparse
    from j2gha.cli import _param
    assert _param("A=b=c") == ("A", "b=c") and _param("A=") == ("A", "")
    for bad in ("A", "=x", "1A=x", "a-b=x"):
        with pytest.raises(argparse.ArgumentTypeError):
            _param(bad)


# ------------------------------------------------------------------------------------ workspace split (R2, F8)
def _split_pipeline(extra_steps=()):
    return Pipeline(dialect="declarative", agent=Agent("any"), options={"skipDefaultCheckout": True}, stages=[
        Stage("Build", steps=[Step("sh", args=["touch output"]), *extra_steps]),
        Stage("Fan", parallel=[Stage("Test", steps=[Step("sh", args=["test -f output"])])]),
        Stage("Publish", steps=[Step("sh", args=["test -f output"])])])


@pytest.mark.parametrize("extra", [(), (Step("stash", named={"name": "w", "includes": "output"}),),
                                   (Step("archiveArtifacts", named={"artifacts": "unrelated.txt"}),)])
def test_a_parallel_split_is_never_reported_as_a_faithful_mapping(extra):
    """The converter cannot know which files the branches read, so no hand-off step proves the split safe."""
    items = convert(_split_pipeline(extra), "")["report"]["items"]
    (split,) = [i for i in items if "parallel jobs" in i["gha"]]
    assert split["status"] == "approximated" and "no longer share the workspace" in split["note"]
    assert ("check that they cover every file" in split["note"]) == bool(extra)


# ----------------------------------------------------------------------------- Jenkins parameters (F2)
def test_parameters_are_defined_in_the_job_xml_so_one_build_runs():
    import xml.etree.ElementTree as ET
    from j2gha.jenkins.controller import parameter_definitions_xml
    from j2gha.jenkins.run import xml_parameters
    params = [Parameter("string", "V", default="1.4.0"), Parameter("booleanParam", "B", default=True),
              Parameter("choice", "C", choices=["a", "b<c"]), Parameter("text", "T", default="x & y")]
    defs = xml_parameters(params)
    root = ET.fromstring(parameter_definitions_xml(defs))  # well-formed, escaped
    kinds = [e.tag for e in root.iter() if e.tag.startswith("hudson.model.") and e.tag.endswith("Definition")]
    assert kinds == ["hudson.model.StringParameterDefinition", "hudson.model.BooleanParameterDefinition",
                     "hudson.model.ChoiceParameterDefinition", "hudson.model.TextParameterDefinition"]
    assert [e.text for e in root.iter("string")] == ["a", "b<c"]


@pytest.mark.parametrize("params", [
    [Parameter("string", "NO_DEFAULT")],  # Jenkins evaluates the default itself: only a run can register it
    [Parameter("string", "V", default="x"), Parameter("other", "F")],
    [],
])
def test_parameters_that_cannot_be_defined_up_front_fall_back_to_the_recorded_registration_build(params):
    from j2gha.jenkins.run import xml_parameters
    assert xml_parameters(params) is None


# ------------------------------------------------------------------------- environment scope of script if (F3, S1, S6)
def _scoped_if(body, stage_env=None, wrap=None, source="env.TARGET == 'prod'"):
    inner = [Step("<if>", source=source, body=body)]
    if wrap:
        inner = [Step("withEnv", args=[[wrap]], body=inner)]
    pipe = Pipeline(dialect="declarative", options={"skipDefaultCheckout": True}, stages=[Stage(
        "S", environment=stage_env or {}, steps=[Step("script", body=inner)])])
    return steps_of(convert(pipe, "")["workflow"])


ONE = [Step("echo", args=["a"])]
TWO = [Step("echo", args=["a"]), Step("echo", args=["b"])]


@pytest.mark.parametrize("body", [ONE, TWO], ids=["single-step", "decision"])
@pytest.mark.parametrize("scope", ["stage", "withEnv"])
def test_script_if_runs_in_the_environment_of_the_steps_it_guards(body, scope):
    """A step's `if:` reads the step's own `env:` (verified on GitHub), so the single-step form needs nothing; the
    decision steps carry the same environment as the steps they decide for, instead of an expression that cannot."""
    kw = {"stage_env": {"TARGET": EnvValue("literal", "prod")}} if scope == "stage" else {"wrap": "TARGET=prod"}
    steps = _scoped_if(body, **kw)
    guarded = [s for s in steps if s["_j2gha"]["kind"] in ("if-decision", "echo")]
    assert all(s["env"].get("TARGET") == "prod" for s in guarded), guarded
    assert "env.TARGET == 'prod'" in guarded[0]["if"]
    assert not any("J2GHA_CONDITION" in str(s.get("env")) for s in steps)


def test_script_if_leaves_quoted_literals_alone():
    """S6: nothing is rewritten, so a string that looks like a reference stays a string."""
    steps = _scoped_if(TWO, stage_env={"TARGET": EnvValue("literal", "prod")}, source="env.TARGET == 'env.TARGET'")
    yes = next(s for s in steps if s["_j2gha"]["kind"] == "if-decision")
    assert yes["if"] == "env.TARGET == 'env.TARGET'"


@pytest.mark.parametrize("value", [EnvValue("shell", "echo prod"), EnvValue("expression", "${params.WHERE}", line=1)],
                         ids=["shell", "gstring"])
def test_script_if_gates_a_value_only_the_shell_computes(value):
    """Such a value is exported inside the step's script: an `if:` cannot read it, so it is a manual gate."""
    steps = _scoped_if(ONE, stage_env={"TARGET": value})
    assert not any("env.TARGET" in (s.get("if") or "") for s in steps)
    assert any(s["_j2gha"]["kind"] == "script-manual" for s in steps)


# ------------------------------------------------------------------------------------- --param validation (F7)
def test_a_scenario_cannot_override_pipeline_or_harness_variables():
    ir = Pipeline(dialect="declarative", environment={"APP_NAME": EnvValue("literal", "svc")},
                  parameters=[Parameter("string", "TARGET", default="prod")],
                  stages=[Stage("S", steps=[Step("echo", args=["x"])])])
    wf = convert(ir, "BRANCH_NAME")["workflow"]
    assert {"APP_NAME", "BRANCH_NAME", "TARGET"} <= set(wf["env"])
    scenario = {"branch": "main", "params": {"TARGET": "qa", "APP_NAME": "injected", "BRANCH_NAME": "other"}}
    variant, _ = make_variant(wf, "trace", "act", scenario)
    assert variant["env"]["TARGET"] == "qa"
    assert variant["env"]["APP_NAME"] == "svc" and variant["env"]["BRANCH_NAME"] == "main"


def test_run_refuses_undeclared_parameters_before_running_anything(tmp_path):
    import json
    from j2gha.runners import execute
    d = tmp_path / "901"
    (d / "analysis").mkdir(parents=True)
    text, ast = load("declarative")
    (d / "Jenkinsfile").write_text(text)
    (d / "analysis" / "groovy-ast.json").write_text(json.dumps(ast))
    declared = execute.declared_parameters(d)
    assert declared  # the declarative fixture declares parameters
    with pytest.raises(ValueError, match="APP_NAME.*not a declared pipeline parameter"):
        execute.run_example(d, ["jenkins"], params={"APP_NAME": "x", next(iter(declared)): "y"})
    assert not (d / "runs").exists()


# ------------------------------------------------------------------- second review (S2-S5): gate completeness
def _gated_parallel(**options):
    return Pipeline(dialect="declarative", agent=Agent("any"), options=options,
                    environment={"FLAG": EnvValue("shell", "printf yes")},
                    stages=[Stage("Deploy", when=When([Condition("expression", text="env.FLAG == 'yes'")], before_input=True),
                                  input={"message": "Go?"}, post={"always": [Step("echo", args=["stage post"])]},
                                  parallel=[Stage("A", steps=[Step("echo", args=["a"])]),
                                            Stage("B", steps=[Step("echo", args=["b"])])])])


def test_a_gated_stages_post_actions_follow_the_gates_decision():
    """S2: the stage-post job consumes the gate's output instead of evaluating `when` (and recomputing env) again."""
    jobs = convert(_gated_parallel(), "")["workflow"]["jobs"]
    post = jobs["deploy-post"]
    assert "deploy-gate" in post["needs"] and post["if"] == "always()"
    conds = [s["if"] for s in post["steps"] if s["_j2gha"]["kind"] == "echo"]
    assert conds == ["(always()) && (needs.deploy-gate.outputs.run == 'true')"]
    assert not any("env.FLAG" in s.get("if", "") for s in post["steps"])


def test_the_gate_keeps_the_checkout_layout_of_the_pipeline():
    """S3: checkoutToSubdirectory applies to the gate's checkout as it does to the stage's."""
    jobs = convert(_gated_parallel(checkoutToSubdirectory="src"), "")["workflow"]["jobs"]
    for jid in ("deploy-gate", "deploy-a", "deploy-b"):
        checkout = next(s for s in jobs[jid]["steps"] if s["_j2gha"]["kind"] == "checkout")
        assert checkout["with"]["path"] == "src", jid


@pytest.mark.parametrize("kind", ["plain", "parallel"])
def test_a_gated_first_stage_still_emits_the_initial_trace_events_once(kind):
    """S4: Jenkins' implicit checkout and pipeline-environment events belong to the workflow's first job, which is
    the gate (or an approval job) when the first stage is gated."""
    ir = _gated_parallel()
    if kind == "plain":
        ir.stages = [Stage("Deploy", when=ir.stages[0].when, input={"message": "Go?"},
                           steps=[Step("echo", args=["d"])])]
    wf = convert(ir, "")["workflow"]
    first = next(iter(wf["jobs"].values()))
    assert first["name"] == "Deploy (when)"
    events = [e for j in wf["jobs"].values() for st in j["steps"] for e in st["_j2gha"].get("trace_events", [])]
    assert [e for e in events if e[0] == "Declarative: Checkout SCM"] == [["Declarative: Checkout SCM", "checkout"]]
    assert sum(1 for e in events if e[1] == "sh") == 1
    kinds = [st["_j2gha"]["kind"] for st in first["steps"]]
    assert kinds[:2] == ["checkout", "environment"]


def test_an_ungated_first_approval_job_carries_the_initial_events_too():
    ir = _gated_parallel()
    ir.stages[0].when = None
    wf = convert(ir, "")["workflow"]
    first = next(iter(wf["jobs"].values()))
    assert first["name"] == "Deploy (input)"
    assert [st["_j2gha"]["kind"] for st in first["steps"]][:2] == ["checkout", "environment"]


def test_a_boolean_default_that_is_not_a_literal_is_not_defined_as_false():
    """S5: `defaultValue: (1 == 1)` parses as default=None; defining it up front would register `false`."""
    from j2gha.jenkins.run import xml_parameters
    assert xml_parameters([Parameter("booleanParam", "RUN", default=None)]) is None
    assert xml_parameters([Parameter("booleanParam", "RUN", default=True)]) == [
        {"name": "RUN", "kind": "booleanParam", "default": True}]
