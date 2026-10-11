"""Regression tests for the findings of the 2026-10-10 code review after 24bf0b6 (R8-1 ... R8-10) and its
secondary items (M-1 ... M-5).

The unmarked tests need no Docker. `docker` tests re-parse localised scripts with the Jenkins Groovy dumper; `e2e` tests
run the review's reproductions on the disposable Jenkins controller (and act).
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import load

from j2gha.analysis.analyze import analyse
from j2gha.analysis.declarative import build_ir
from j2gha.convert.generator import JENKINS_ENV, convert
from j2gha.ir import Agent, Pipeline, Stage, Step, resolve_credential_id
from j2gha.jenkins.localize import _arg_calls, groovy_string, localize
from j2gha.jenkins.run import xml_parameters
from j2gha.outputs import compare_outputs, file_entry, gha_outputs
from j2gha.runners.variants import make_variant

FIXTURES = Path(__file__).resolve().parent / "fixtures"

ROOT = Path(__file__).resolve().parent.parent
SOURCE = {"url": "https://github.com/example/project.git", "sha": "0123456789abcdef0123456789abcdef01234567"}


@pytest.fixture(autouse=True)
def no_workspace_handoff(monkeypatch):
    monkeypatch.setenv("J2GHA_WORKSPACE_HANDOFF", "0")


def _steps(result):
    return [s for job in result["workflow"]["jobs"].values() for s in job["steps"]]


# ------------------------------------------------------------------------------------------------- R8-2 properties
def test_full_mode_properties_keeps_parameter_definitions():
    text, ast = load("localisation")
    full = localize(text, ast, analyse(text, ast), "full", source=SOURCE).script
    # the parameter entries reach the real step, stub-valued definitions are left out, other properties dropped
    assert "steps.properties([steps.parameters(defs)])" in full and "j2ghaParameterDefs" in full
    assert "!(it instanceof J2ghaAny)" in full
    # core parameter symbols are never stubbed as unknown DSL symbols (a J2ghaAny is no parameter definition)
    assert "def choice(" not in full and "def booleanParam(" not in full
    assert "def parameters(Object... a) { return [j2ghaParameters:" in full
    assert "def logRotator(Object... a) { return new J2ghaAny() }" in full  # a non-parameter symbol is still a stub
    assert "def buildDiscarder(Object... a) { return null }" in full


def test_trace_mode_properties_is_still_silent():
    text, ast = load("localisation")
    trace = localize(text, ast, analyse(text, ast), "trace").script
    assert "def properties(Object... a) { return null }" in trace and "j2ghaParameterDefs" not in trace


def test_scripted_map_form_parameters_are_registered_up_front():
    text, ast = load("localisation")
    params = {p.name: p for p in build_ir(ast).parameters}
    assert (params["TARGET"].kind, params["TARGET"].choices) == ("choice", ["dev", "prod"])
    assert (params["C"].kind, params["C"].choices) == ("choice", ["x", "y"])
    assert params["FLAG"].default is True and params["S"].default == "sv"
    # libraryParam cannot be defined in job XML: the runtime-registration build defines them all (fallback path)
    assert params["L"].kind == "libraryParam" and xml_parameters(list(params.values())) is None
    # without it, every definition is literal: defined up front, the one build is the scenario
    defined = xml_parameters([p for p in params.values() if p.name != "L"])
    assert {d["name"]: d.get("choices") for d in defined}["TARGET"] == ["dev", "prod"]


# ------------------------------------------------------------------------------------------------- R8-3 literals
GROOVY_DECODE = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "'": "'", "\\": "\\"}


def _groovy_decode(lit: str) -> str:
    body, out, i = lit[1:-1], [], 0
    while i < len(body):
        if body[i] == "\\":
            if body[i + 1] == "u":
                out.append(chr(int(body[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(GROOVY_DECODE[body[i + 1]])
            i += 2
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


@pytest.mark.parametrize("value", ["multi\nline", "cr\r\nlf", "tab\there", "quote ' and \\ backslash", "bell\x07",
                                   "dollar ${x} $y", "unicode é ✓"])
def test_groovy_string_is_one_line_and_round_trips(value):
    lit = groovy_string(value)
    assert lit[0] == lit[-1] == "'" and not any(ord(ch) < 0x20 for ch in lit)
    assert _groovy_decode(lit) == value


def test_promoted_multiline_tuple_keeps_lines_and_value():
    text, ast = load("localisation")
    script = localize(text, ast, analyse(text, ast), "full", source=SOURCE,
                      remove=[("stub-property", "config")]).script
    body = script[:script.index("// ---- j2gha localisation block")]
    assert "@groovy.transform.Field def config = 'first\\nsecond'; @groovy.transform.Field def retries = 0" in body
    # every line after the edit is where it was: Jenkins error lines still match the Jenkinsfile
    lines, original = body.splitlines(), text.splitlines()
    assert lines[3:6] == original[3:6] and lines.index("  stage('Build') {") == original.index("  stage('Build') {")


@pytest.mark.docker
def test_promoted_multiline_tuple_compiles():
    from j2gha.analysis.ast import dump_sources
    text, ast = load("localisation")
    script = localize(text, ast, analyse(text, ast), "full", source=SOURCE, remove=[("stub-property", "config")]).script
    parsed = dump_sources({"localised": script})["localised"]
    assert parsed["ok"], parsed.get("errors")


# ------------------------------------------------------------------------------------------------- R8-4 parameters
def _echo_runs(result):
    return [s["run"] for s in _steps(result) if (s.get("_j2gha") or {}).get("kind") == "echo"]


def test_declared_empty_parameter_is_not_rendered_null():
    text, ast = load("scoped-credentials")
    run = _echo_runs(convert(build_ir(ast), text))[0]
    assert run == 'echo "tag=<${TAG_NAME}> env=<${TAG_NAME}> params=<${TAG_NAME}>"'
    out = subprocess.run(["bash", "-c", run], env={**os.environ, "TAG_NAME": ""}, capture_output=True, text=True)
    assert out.stdout.strip() == "tag=<> env=<> params=<>"  # what live Jenkins prints for the declared '' parameter


def test_undeclared_scm_variable_keeps_the_null_rendering():
    ir = Pipeline(dialect="declarative", agent=Agent(kind="any"), options={"skipDefaultCheckout": True},
                  stages=[Stage("S", steps=[Step("echo", args=["tag=<${TAG_NAME}> id=<${env.CHANGE_ID}>"], dynamic=True)])])
    run = _echo_runs(convert(ir, ""))[0]
    assert "${TAG_NAME:-null}" in run and "${CHANGE_ID:-null}" in run


# ------------------------------------------------------------------------------------------------- R8-5 credentials
def test_credential_resolution_uses_the_nearest_scope():
    text, ast = load("scoped-credentials")
    envs = [s.get("env") or {} for s in _steps(convert(build_ir(ast), text))
            if "TOKEN" in (s.get("env") or {}) or "A" in (s.get("env") or {})]
    assert [e.get("TOKEN") or e.get("B") for e in envs] == [
        "${{ secrets.INNER_ID }}",       # stage environment beats the pipeline's
        "${{ secrets.OUTER_ID }}",       # no nearer definition: the pipeline literal
        "${{ secrets.WITH_ENV_ID }}",    # withEnv beats both
        "${{ secrets.LIT_ID }}",         # "${LIT}" and 'lit-id' are one credential
        "${{ secrets.ENV_CRED }}",       # a nearer non-literal definition: unresolved, never the outer literal
    ]


def test_unresolved_credential_is_a_manual_item():
    text, ast = load("scoped-credentials")
    items = convert(build_ir(ast), text)["report"]["items"]
    unresolved = [i for i in items if i["jenkins"].startswith("withCredentials") and "$" in i["jenkins"]]
    assert unresolved and all(i["status"] == "manual" for i in unresolved)


def test_credential_inventory_is_scope_aware_and_merged():
    text, ast = load("scoped-credentials")
    creds = {c["id"]: c for c in analyse(text, ast)["credentials"]}
    assert set(creds) == {"inner-id", "outer-id", "with-env-id", "lit-id", "${env.CRED}"}
    assert creds["lit-id"]["lines"] == [22, 22] and creds["lit-id"]["expr"] == "${LIT}"
    assert creds["${env.CRED}"]["lines"] == [30]  # the Dynamic stage: nothing to provision for it


# re-review R9-1/R9-2: scopes by actual nesting (same-line siblings and nested wrappers), and a nearer literal over an
# outer shell export; inventory and workflow must agree on every use
CREDENTIAL_SCOPES = [  # (stage, credential the use selects, line)
    ("Sibling", "outer-id", 11),             # a closed sibling withEnv on the same line does not apply
    ("Nested", "nested-id", 16),             # the innermost of same-line nested withEnv
    ("LiteralOverDynamic", "literal-id", 23),  # a nearer literal beats an outer dynamic export
    ("DynamicOverLiteral", "${env.CRED}", 33),  # a nearer dynamic value beats an outer literal: unresolved
    ("StageOverPipelineExport", "stage-dyn-id", 41),  # a stage literal beats a pipeline shell export
    ("Usea", "matrix-a-id", 44),             # two matrices on one line keep their own environment (R10-1)
    ("Useb", "matrix-b-id", 44),
]


def _token_steps(conversion):
    return {s["name"].split(":")[0]: s for s in _steps(conversion) if "TOKEN" in (s.get("env") or {})}


def test_credential_scopes_follow_nesting_in_inventory_and_workflow():
    text, ast = load("credential-scopes")
    creds = {c["id"]: c["lines"] for c in analyse(text, ast)["credentials"]}
    assert creds == {cid: [line] for _, cid, line in CREDENTIAL_SCOPES}  # line: the binding's (matrices share 44)
    steps = _token_steps(convert(build_ir(ast), text))
    for stage, cid, _ in CREDENTIAL_SCOPES:
        secret = "ENV_CRED" if cid.startswith("$") else cid.upper().replace("-", "_")
        assert steps[stage]["env"]["TOKEN"] == f"${{{{ secrets.{secret} }}}}", stage


def test_nearer_literal_drops_the_outer_export_and_leaving_restores_it():
    text, ast = load("credential-scopes")
    steps = [s for s in _steps(convert(build_ir(ast), text)) if s["name"].startswith("LiteralOverDynamic")]
    inner, after = (next(s for s in steps if marker in s.get("run", "")) for marker in ("= literal-id", "cred="))
    assert "export CRED" not in inner["run"] and inner["env"]["CRED"] == "literal-id"
    shell = {**os.environ, "BUILD_NUMBER": "42"}
    for step, expected in ((inner, ""), (after, "cred=42-id")):  # the outer export applies again after the scope
        out = subprocess.run(["bash", "-c", step["run"]], env={**shell, **{k: v for k, v in (step.get("env") or {}).items()
                                                                           if k != "TOKEN"}},
                             capture_output=True, text=True)
        assert out.returncode == 0 and out.stdout.strip() == expected, (step["run"], out)


def test_resolver_contract():
    assert resolve_credential_id("${env.X}", [{"X": "inner"}, {"X": "outer"}]) == "inner"
    assert resolve_credential_id("${X}", [{}, {"X": "outer"}]) == "outer"
    assert resolve_credential_id("${X}", [{"X": None}, {"X": "outer"}]) == "${X}"
    assert resolve_credential_id("literal-id", [{"literal-id": "x"}]) == "literal-id"
    assert resolve_credential_id("pre-${X}", [{"X": "x"}]) == "pre-${X}"


# ------------------------------------------------------------------------------------------------- R8-6 unstash
def test_optional_unstash_cannot_select_the_failure_post():
    stage = Stage("Test", steps=[Step("stash", named={"name": "nothing", "includes": "absent/**", "allowEmpty": True}),
                                 Step("unstash", args=["nothing"]), Step("echo", args=["body succeeded"])],
                  post={"success": [Step("echo", args=["success post"])],
                        "failure": [Step("error", args=["failure post must not run"])]})
    ir = Pipeline(dialect="declarative", agent=Agent(kind="any"), options={"skipDefaultCheckout": True}, stages=[stage])
    steps = _steps(convert(ir, ""))
    unstash = next(s for s in steps if s["_j2gha"]["kind"] == "unstash")
    failure = next(s for s in steps if s["_j2gha"]["kind"] == "error")
    # no tolerated failure: an absent stash is a successful download of nothing (by pattern)
    assert "continue-on-error" not in unstash and unstash["with"]["pattern"] == "stash-nothing"
    assert f"steps.{unstash['id']}.outcome == 'failure'" in failure["if"]  # a real download error still counts


# ------------------------------------------------------------------------------------------------- R8-7 archives
def test_identical_project_workflow_files_compare_same():
    record = {"tests": [], "archived": [{"path": ".github/workflows/j2gha.yml", "sha256": "same"}]}
    assert compare_outputs(record, record)["archived"]["status"] == "same"
    gha = {**record, "injected": [{"path": ".github/workflows/j2gha.yml", "sha256": "same"}]}
    assert compare_outputs(record, gha)["archived"]["status"] == "same"  # Jenkins archived it: always compared


def test_only_the_injected_file_is_filtered():
    injected = {".github/workflows/j2gha-run.yml": "name: run\n"}
    harness = file_entry(".github/workflows/j2gha-run.yml", b"name: run\n")
    own = file_entry(".github/workflows/j2gha-run.yml", b"name: the project's own\n")
    jenkins = {"tests": None, "archived": [file_entry("out.txt", b"x")]}
    base = gha_outputs({}, None, injected=injected)
    assert base["injected"] == [harness]
    ok = compare_outputs(jenkins, {**base, "archived": [file_entry("out.txt", b"x"), harness]})
    assert ok["archived"]["status"] == "same"
    extra = compare_outputs(jenkins, {**base, "archived": [file_entry("out.txt", b"x"), own]})
    assert extra["archived"]["extra"] == [".github/workflows/j2gha-run.yml"] and extra["verdict"] == "differs"


def test_legacy_records_filter_by_path_only_when_jenkins_lacks_it():
    jenkins = {"tests": None, "archived": [file_entry("out.txt", b"x")]}
    legacy = {"tests": None, "archived": [file_entry("out.txt", b"x"), file_entry(".github/workflows/j2gha.yml", b"y")]}
    assert compare_outputs(jenkins, legacy)["archived"]["status"] == "same"


# ------------------------------------------------------------------------------------------------- R8-8 variants
def _variant_env(env, scenario=None, inputs=None):
    model = {"name": "t", "on": {"workflow_dispatch": {"inputs": inputs or {}}}, "env": env,
             "jobs": {"j": {"runs-on": "ubuntu-latest", "steps": [{"run": "true"}]}}}
    return make_variant(model, "full", "act", scenario or {"branch": "main"},
                        source={**SOURCE, "repository": "example/project"})[0]["env"]


def test_variant_keeps_an_explicit_git_commit():
    assert _variant_env({"GIT_COMMIT": "pipeline-value"})["GIT_COMMIT"] == "pipeline-value"
    assert _variant_env({"GIT_COMMIT": JENKINS_ENV["GIT_COMMIT"]})["GIT_COMMIT"] == SOURCE["sha"]


def test_variant_keeps_other_declared_jenkins_names_and_applies_parameters():
    env = _variant_env({"BRANCH_NAME": "declared", "GIT_BRANCH": JENKINS_ENV["GIT_BRANCH"], "GIT_COMMIT": "expr"},
                       scenario={"branch": "dev", "params": {"GIT_COMMIT": "from-scenario"}},
                       inputs={"GIT_COMMIT": {}})
    assert env["BRANCH_NAME"] == "declared" and env["GIT_BRANCH"] == "dev" and env["GIT_COMMIT"] == "from-scenario"
    assert _variant_env({})["BRANCH_NAME"] == "main" and _variant_env({})["TAG_NAME"] == ""


# ------------------------------------------------------------------------------------------------- R8-9 crawler
def test_crawler_refuses_the_twin_range(monkeypatch, tmp_path):
    from j2gha.crawl import crawler
    monkeypatch.setattr(crawler, "list_example_ids", lambda: ["097", "101", "121"])
    assert crawler.check_capacity(2, tmp_path) == 98
    with pytest.raises(SystemExit, match="2 id"):
        crawler.check_capacity(3, tmp_path)
    monkeypatch.setattr(crawler, "list_example_ids", lambda: ["098", "099", "100", "101"])
    with pytest.raises(SystemExit, match="0 id"):
        crawler.check_capacity(1, tmp_path)
    with pytest.raises(SystemExit):  # write_examples checks the whole batch before writing anything
        crawler.write_examples([{"text": "x"}], tmp_path, datetime.now(timezone.utc))
    assert not any(tmp_path.iterdir())


# ------------------------------------------------------------------------------------------------- R8-10 twin results
def test_twin_results_are_recorded_per_mode_and_run(tmp_path):
    script = ROOT / ".claude/skills/jenkins-example-twin/scripts/twin_results.py"
    d = tmp_path / "examples" / "150"
    for mode, finished in (("full", "2026-10-10T08:00:00+00:00"), ("trace", "2026-10-10T08:05:00+00:00")):
        for tier, result in (("jenkins", "SUCCESS"), ("act", "success")):
            (d / "runs" / f"{tier}-{mode}").mkdir(parents=True)
            (d / "runs" / f"{tier}-{mode}" / "result.json").write_text(json.dumps(
                {"result": result, "finished_at": finished, "comparison": {"verdict": "equivalent"}}))
    (d / "LOCAL.md").write_text("# twin\n")

    def run(*args):
        return subprocess.run([sys.executable, str(script), "150", *args], cwd=tmp_path, capture_output=True,
                              text=True, check=True).stdout

    run("--mode", "full")
    run("--mode", "trace")
    text = (d / "LOCAL.md").read_text()
    assert "- act full (2026-10-10T08:00:00+00:00)" in text and "- act trace (2026-10-10T08:05:00+00:00)" in text
    assert "nothing new" in run("--mode", "trace")  # the same run is not recorded twice
    rec = d / "runs" / "act-trace" / "result.json"
    rec.write_text(json.dumps({**json.loads(rec.read_text()), "finished_at": "2026-10-10T09:00:00+00:00"}))
    assert "- act trace (2026-10-10T09:00:00+00:00)" in run("--mode", "trace")  # a re-run the same day is


# ------------------------------------------------------------------------------------------------- M-1, M-4, M-5
def test_argument_walker_reaches_receiver_calls_not_gstrings():
    text, ast = load("localisation")
    from j2gha.analysis.ast import all_calls
    node = {"named": {"choices": {"t": "call", "call": {
        "k": "call", "name": "reverse", "args": [], "named": {}, "receiver": "getChoices()",
        "receiverCalls": [{"k": "call", "name": "getChoices", "args": [], "named": {}}]}}}}
    assert [c["name"] for c in _arg_calls(node)] == ["reverse", "getChoices"]
    gstr = {"named": {"choices": {"t": "gstr", "v": '"${getChoices()}"', "calls": [{"k": "call", "name": "getChoices"}]}}}
    assert list(_arg_calls(gstr)) == []  # interpolated into a String: coercible, the parameter is kept
    assert all_calls(ast)  # the fixture parses


def test_info_rows_are_listed_but_not_scored():
    ir = Pipeline(dialect="declarative", agent=Agent(kind="any"), stages=[Stage("S", steps=[Step("sh", args=["make"])])])
    report = convert(ir, "")["report"]
    assert report["counts"].get("info") == 1  # the implicit checkout's SCM environment
    scored = {k: v for k, v in report["counts"].items() if k != "info"}
    weights = {"mapped": 1.0, "dropped": 0.8, "approximated": 0.6, "manual": 0.0}
    assert report["automation_pct"] == round(100 * sum(weights[k] * v for k, v in scored.items()) / sum(scored.values()), 1)


def test_spare_runner_counts_busy_runners():
    from j2gha.gha.remote import RunnerPool
    pool = RunnerPool.__new__(RunnerPool)
    pool.max_parallel, started = 4, []
    alive = iter([2, 3, 4])  # two runners busy with running jobs, one job queued
    pool.alive = lambda: next(alive)
    pool.start_one = lambda: started.append(1)
    pool.ensure(1, running=2)
    # 2 busy + 1 for the queued job + 1 spare (before the fix: min(4, 1 + 1) = 2 <= 2 alive, nothing started)
    assert started == [1, 1]


# ------------------------------------------------------------------------------------------------- live controls
@pytest.mark.e2e
def test_live_jenkins_reproductions(tmp_path):
    """The review's runtime reproductions on the disposable controller: R8-2 (map-form choice, mixed properties with a
    stub-valued definition, Declarative parameters {} next to properties() in script {}), R8-4 (declared empty
    parameter) and the re-review's R9-1/R9-2 (the credential-scopes fixture: the controller provisions exactly the
    inventory, so a use resolved to the wrong scope fails with a missing credential; its one deliberately unresolved
    use, which nothing can provision, is left out)."""
    from j2gha.analysis.ast import dump_sources
    from j2gha.convert.generator import to_yaml
    from j2gha.provenance import sha256_json, sha256_text
    from j2gha.runners import execute
    nonce = os.urandom(4).hex()
    cases = {
        "map-choice": ("properties([parameters([[$class: 'ChoiceParameterDefinition', name: 'TARGET', "
                       "choices: ['dev', 'prod']]])])\nnode { stage('Test') { echo \"target=${params.TARGET}\"\n"
                       "if (params.TARGET != 'dev') { error 'expected default dev' } } }\n"),
        "mixed": ("properties([buildDiscarder(logRotator(numToKeepStr: '5')), disableConcurrentBuilds(),\n"
                  "parameters([booleanParam(name: 'FLAG', defaultValue: true), choice(name: 'C', choices: ['x', 'y']),"
                  " libraryParam(name: 'L'), string(name: 'S', defaultValue: 'sv')])])\n"
                  "node { stage('Test') { if (params.FLAG != true || params.C != 'x' || params.S != 'sv') "
                  "{ error 'wrong parameters' } } }\n"),
        "empty-tag": ("pipeline { agent any\n options { skipDefaultCheckout() }\n"
                      " parameters { string(name: 'TAG_NAME', defaultValue: '') }\n"
                      " stages { stage('Test') { steps { echo \"tag=<${TAG_NAME}>\" } } } }\n"),
        "declarative-properties": ("pipeline { agent any\n options { skipDefaultCheckout() }\n"
                                   " parameters { booleanParam(name: 'FLAG', defaultValue: true) }\n"
                                   " stages { stage('Test') { steps { script {\n"
                                   "  properties([parameters([booleanParam(name: 'FLAG', defaultValue: true),"
                                   " choice(name: 'C', choices: ['x', 'y'])])])\n"
                                   "  if (params.FLAG != true) { error 'wrong FLAG' } } } } } }\n"),
        # fresh ids per run: the controller keeps credentials provisioned by earlier runs, which would mask a wrong one
        "credential-scopes": re.sub(r"(?s)    stage\('DynamicOverLiteral'\).*?(?=    stage\('StageOverPipelineExport'\))", "",
                                    (FIXTURES / "Jenkinsfile.credential-scopes").read_text()).replace("-id'", f"-id-{nonce}'"),
    }
    for key, src in cases.items():
        d = tmp_path / key
        (d / "analysis").mkdir(parents=True)
        (d / "gha").mkdir()
        (d / "Jenkinsfile").write_text(src)
        (d / "README.md").write_text("# live control\n")
        ast = dump_sources({key: src})[key]
        ast["source_sha256"] = sha256_text(src)
        a = analyse(src, ast)
        a["source_sha256"] = ast["source_sha256"]
        (d / "analysis/groovy-ast.json").write_text(json.dumps(ast))
        (d / "analysis/analysis.json").write_text(json.dumps(a))
        model = convert(build_ir(ast), src)["workflow"]
        (d / "gha/workflow.model.json").write_text(json.dumps(model))
        (d / "gha/workflow.yml").write_text(to_yaml(model))
        (d / "gha/conversion.json").write_text(json.dumps({"source_sha256": ast["source_sha256"],
                                                           "model_sha256": sha256_json(model)}))
        rec = execute.run_example(d, ["jenkins"], mode="full")["records"]["jenkins"]
        assert rec["result"] == "SUCCESS", (key, rec.get("error_tail"))
        if key == "empty-tag":
            assert "tag=<>" in (d / "runs/jenkins-full/console.log").read_text()
        if key == "credential-scopes":
            assert {c["id"] for c in a["credentials"]} == {f"{x}-id-{nonce}" for x in ("outer", "nested", "literal", "stage-dyn",
                                                                                     "matrix-a", "matrix-b")}
            assert re.search(r"cred=\d+-id", (d / "runs/jenkins-full/console.log").read_text())  # outer export again


def test_act_artifact_store_has_the_run_directory(tmp_path):
    """act's v4 artifact server panics listing a run with no uploads yet (the review's ECONNRESET): the harness
    creates the run's directory so a download by pattern of an empty optional stash finds an empty list (R8-6)."""
    from j2gha.runners.act import _reset_artifacts
    _reset_artifacts(tmp_path / "artifacts")
    assert (tmp_path / "artifacts" / "1").is_dir()
