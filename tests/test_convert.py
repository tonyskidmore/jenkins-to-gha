import re

import pytest
import yaml

from j2gha.analysis.declarative import build_ir
from j2gha.convert.expressions import glob_condition, translate_groovy
from j2gha.convert.generator import convert, to_yaml
from j2gha.ir import Step
from j2gha.render import references_section, xref_key
from j2gha.runners.variants import estimate_minutes, make_variant


@pytest.fixture(autouse=True)
def no_workspace_handoff(monkeypatch):
    """These tests check the job structure without the workspace hand-off (Phase 4, P4.3: tests/test_handoff.py);
    the cross product in tests/test_contexts.py runs with it."""
    monkeypatch.setenv("J2GHA_WORKSPACE_HANDOFF", "0")


def _convert(declarative):
    text, ast = declarative
    return convert(build_ir(ast), text, title="fixture")


def test_expression_translation():
    assert translate_groovy("return params.DEPLOY") == "env.DEPLOY == 'true'"
    assert translate_groovy("params.ENV == 'prod'") == "env.ENV == 'prod'"
    assert translate_groovy("env.BRANCH_NAME.startsWith('release/')") == "startsWith(env.BRANCH_NAME, 'release/')"
    assert translate_groovy("env.CHANGE_ID") == "env.CHANGE_ID != ''"
    assert translate_groovy("myLocal == 1") is None  # Groovy local variables are not knowable statically
    # Ant `*` stays inside one path segment: release/* does not match release/1/2, which `startsWith` cannot say
    assert glob_condition("env.BRANCH_NAME", "release/*") == ("startsWith(env.BRANCH_NAME, 'release/')", "approximated")


def test_workflow_shape(declarative):
    wf = _convert(declarative)["workflow"]
    jobs = wf["jobs"]
    assert wf["permissions"] == {"contents": "read"}
    assert wf["concurrency"]["cancel-in-progress"] is False
    assert wf["on"]["schedule"] == [{"cron": "7 2 * * *"}]  # H replaced deterministically
    assert set(wf["on"]["workflow_dispatch"]["inputs"]) == {"DEPLOY", "TARGET"}
    # Build is its own job; Test's parallel branches become two jobs that need it; Matrix and Deploy follow
    assert list(jobs) == ["build", "test-unit", "test-integration", "matrix", "deploy", "post"]
    assert jobs["test-integration"]["container"]["image"] == "node:20"
    assert jobs["test-unit"]["needs"] == "build" and jobs["matrix"]["needs"] == ["test-unit", "test-integration"]
    m = jobs["matrix"]["strategy"]["matrix"]
    assert m["OS"] == ["linux", "windows"] and {"OS": "windows", "JDK": "17"} in m["exclude"]
    assert jobs["post"]["if"] == "always()"


def test_steps_and_conditions(declarative):
    jobs = _convert(declarative)["workflow"]["jobs"]
    build_runs = [s.get("run", "") for s in jobs["build"]["steps"]]
    assert "make build" in build_runs and "make lint" in build_runs  # helper() inlined with its argument
    deploy = jobs["deploy"]["steps"]
    deploy_sh = next(s for s in deploy if s.get("run", "").startswith("./deploy.sh"))
    # `when` is evaluated once by the stage entry step; the stage's steps test its output
    entry = next(s for s in deploy if s["_j2gha"]["kind"] == "stage-entry")
    assert "env.BRANCH_NAME == 'main'" in entry["if"] and "env.DEPLOY == 'true'" in entry["if"]
    assert f"steps.{entry['id']}.outputs.run == 'true'" in deploy_sh["if"]
    assert deploy_sh["env"]["U"] == "${{ secrets.DEPLOYER_USR }}"
    echoes = [s for s in deploy if s.get("_j2gha", {}).get("kind") == "echo"]
    # an if/else with several steps is decided once (a step may change TARGET); its steps test the decision
    yes, no = [s for s in deploy if s.get("_j2gha", {}).get("kind") == "if-decision"]
    assert "env.TARGET == 'prod'" in yes["if"] and f"steps.{yes['id']}.outcome == 'skipped'" in no["if"]
    assert any(f"steps.{yes['id']}.outputs.taken == 'true'" in s["if"] for s in echoes)
    assert any(f"steps.{no['id']}.outputs.taken == 'false'" in s["if"] for s in echoes)
    stage_post = next(s for s in jobs["build"]["steps"] if s.get("run") == 'echo "build failed"')
    assert "outcome == 'failure'" in stage_post["if"]


def test_report_and_yaml(declarative):
    result = _convert(declarative)
    report = result["report"]
    assert {"REGISTRY", "DEPLOYER_USR", "DEPLOYER_PSW"} <= set(report["secrets"])
    assert report["counts"]["mapped"] > 0 and 0 < report["automation_pct"] <= 100
    text = to_yaml(result["workflow"])
    loaded = yaml.safe_load(text)
    assert "_j2gha" not in text
    assert loaded["jobs"]["build"]["runs-on"] == "ubuntu-latest"


def test_trace_variant_and_estimate(declarative):
    wf = _convert(declarative)["workflow"]
    variant, notes = make_variant(wf, "trace", "act", {"branch": "main"})
    assert variant["env"]["BRANCH_NAME"] == "main"
    for job in variant["jobs"].values():
        assert "container" not in job
        for step in job["steps"]:
            assert "uses" not in step
            assert "J2GHA-TRACE" in step["run"] or step["run"] in (
                "true", 'echo "run=true" >> "$GITHUB_OUTPUT"', 'echo "taken=true" >> "$GITHUB_OUTPUT"',
                'echo "taken=false" >> "$GITHUB_OUTPUT"')
    est = estimate_minutes(variant, "trace")
    assert est["typical"] == notes["jobs"] == 8  # build, unit, integration, deploy, post + 3 matrix cells
    hosted, _ = make_variant(wf, "full", "hosted", {"branch": "main"}, branch="j2gha/run/x", max_minutes=7)
    assert hosted["on"]["push"]["branches"] == ["j2gha/run/x"]
    assert all(j["timeout-minutes"] <= 7 for j in hosted["jobs"].values())


def test_regexp_branch_comparator():
    from j2gha.ir import Condition
    from j2gha.convert.expressions import condition_expr

    def cond(pattern):
        return condition_expr(Condition(kind="branch", value=pattern, comparator="REGEXP", line=12))
    # Java matches() is a whole-value match: literal prefixes/suffixes and alternations translate exactly
    assert cond("release-.*") == ("startsWith(env.BRANCH_NAME, 'release-')", "mapped")
    assert cond("^release-.*$") == ("startsWith(env.BRANCH_NAME, 'release-')", "mapped")
    assert cond(".*-hotfix") == ("endsWith(env.BRANCH_NAME, '-hotfix')", "mapped")
    assert cond("main|develop") == ("(env.BRANCH_NAME == 'main' || env.BRANCH_NAME == 'develop')", "mapped")
    assert cond("main") == ("env.BRANCH_NAME == 'main'", "mapped")
    # regexes without `*`/`?` used to be taken for exact names
    for pattern in ("release-[0-9]+", r"v\d+\.\d+", "(?i)main", "rel.ase"):
        assert cond(pattern) == ("vars.J2GHA_WHEN_L12 == 'true'", "manual"), pattern
    tag = condition_expr(Condition(kind="tag", value="v[0-9]+", comparator="REGEXP", line=3))
    assert tag == ("vars.J2GHA_WHEN_L3 == 'true'", "manual")
    assert condition_expr(Condition(kind="branch", value="release-*", comparator="GLOB")) == \
        ("(startsWith(env.BRANCH_NAME, 'release-') && !contains(env.BRANCH_NAME, '/'))", "mapped")


def _gha_if(expr: str, env: dict, vars_: dict | None = None) -> bool:
    """Evaluate the subset of GitHub expressions the condition translator emits (env/vars comparisons,
    startsWith/endsWith/contains, ! && || and parentheses)."""
    import re as _re
    vars_ = vars_ or {}
    py = expr
    py = _re.sub(r"(startsWith|endsWith|contains)\(", lambda m: {"startsWith": "_sw(", "endsWith": "_ew(",
                                                                 "contains": "_ct("}[m.group(1)], py)
    py = _re.sub(r"substring\(", "_ss(", py)
    py = _re.sub(r"\benv\.(\w+)", lambda m: repr(env.get(m.group(1), "")), py)
    py = _re.sub(r"\bvars\.(\w+)", lambda m: repr(vars_.get(m.group(1), "")), py)
    py = py.replace("&&", " and ").replace("||", " or ").replace("!=", "<>").replace("!", " not ").replace("<>", "!=")
    return bool(eval(py, {"_sw": lambda a, b: a.lower().startswith(b.lower()),  # noqa: S307 - test-only
                          "_ew": lambda a, b: a.lower().endswith(b.lower()),
                          "_ct": lambda a, b: b.lower() in a.lower(),
                          "_ss": lambda a, start, length=None: a[start:] if length is None else a[start:start + length]}))


def test_untranslatable_conditions_never_widen_the_stage():
    """A manual gate stands in for the untranslatable condition; unset, it takes the value that keeps the stage off,
    so the stage runs only where it would run whatever that condition's value (also under `not`)."""
    from j2gha.ir import Condition as C
    from j2gha.convert.expressions import condition_expr

    unknown = C("expression", text="isProduction()", line=5)
    main = C("branch", value="main")
    cases = {
        "not": C("not", children=[unknown]),
        "allOf-not": C("allOf", children=[main, C("not", children=[unknown])]),
        "not-anyOf": C("not", children=[C("anyOf", children=[main, unknown])]),
        "not-not": C("not", children=[C("not", children=[unknown])]),
        "anyOf": C("anyOf", children=[main, unknown]),
        "changeset": C("changeset", value="src/**", line=5),
        "not-changeset": C("not", children=[C("changeset", value="src/**", line=5)]),
    }
    for name, c in cases.items():
        expr, status = condition_expr(c)
        assert status == "manual", name
        for branch in ("main", "dev"):
            env = {"BRANCH_NAME": branch}
            runs = _gha_if(expr, env)
            # the unknown condition true / false (stated through the repository variable)
            if_true = _gha_if(expr, env, {"J2GHA_WHEN_L5": "true"})
            if_false = _gha_if(expr, env, {"J2GHA_WHEN_L5": "false"})
            assert runs <= (if_true and if_false), (name, branch, expr)
            assert {if_true, if_false} <= {True, False}
    # stating the condition's value restores the Jenkins semantics
    expr, _ = condition_expr(cases["not"])
    assert _gha_if(expr, {}, {"J2GHA_WHEN_L5": "false"}) and not _gha_if(expr, {}, {"J2GHA_WHEN_L5": "true"})


def test_change_request_filters_are_translated():
    from j2gha.ir import Condition as C
    from j2gha.convert.expressions import condition_expr

    expr, status = condition_expr(C("changeRequest", value={"target": "main"}))
    assert status == "mapped"
    assert _gha_if(expr, {"CHANGE_ID": "7", "CHANGE_TARGET": "main"})
    assert not _gha_if(expr, {"CHANGE_ID": "7", "CHANGE_TARGET": "develop"})
    assert not _gha_if(expr, {"CHANGE_TARGET": "main"})
    # examples/015 SonarQube: not { allOf { changeRequest branch: 'dependabot*'; not { changeRequest branch: /re/ } } }
    sonar = C("not", children=[C("allOf", children=[
        C("changeRequest", value={"branch": "dependabot*", "comparator": "GLOB"}, line=80),
        C("not", children=[C("changeRequest", value={"branch": "^dependabot.*(?i)(ibm)[\\.-].+sdk-core.*$",
                                                     "comparator": "REGEXP"}, line=81)])])])
    expr, status = condition_expr(sonar)
    assert status == "manual"
    dependabot_pr = {"CHANGE_ID": "9", "CHANGE_BRANCH": "dependabot-lodash"}
    assert not _gha_if(expr, dependabot_pr)  # the exclusion is kept (was `!(A && !A)`, always true)
    # Jenkins' GLOB is Ant matchPath: `*` does not cross `/`, so `dependabot*` does not match dependabot/npm/lodash
    assert _gha_if(expr, {"CHANGE_ID": "9", "CHANGE_BRANCH": "dependabot/npm/lodash"})
    assert _gha_if(expr, {"CHANGE_ID": "9", "CHANGE_BRANCH": "feature/x"})
    assert _gha_if(expr, {"BRANCH_NAME": "main"})


def test_scripted_literal_parallel_branches_are_kept():
    from conftest import load
    text, ast = load("parallel")
    wf = convert(build_ir(ast), text, title="parallel")["workflow"]
    runs = [s.get("run") for job in wf["jobs"].values() for s in job["steps"]]
    assert "make unit" in runs and "make lint" in runs


def _jobs_for(stages, agent="any"):
    from j2gha.ir import Agent, Pipeline
    ir = Pipeline(dialect="declarative", agent=Agent(kind=agent), stages=stages, options={"skipDefaultCheckout": True})
    return convert(ir, "", title="t")["workflow"]["jobs"]


def _steps(jobs):
    return [s for job in jobs.values() for s in job["steps"]]


def test_shell_text_is_verbatim_unless_gstring():
    from j2gha.ir import Stage, Step
    plain = Step("sh", args=['echo "${#PASSWORD} ${TICKET:-none} ${env.X}"'])
    gstring = Step("sh", args=['echo "${env.X} ${TICKET:-none}"'], dynamic=True)  # "...\${TICKET:-none}" in Groovy
    echo = Step("echo", args=["cost: $5"])
    runs = [s.get("run") for s in _steps(_jobs_for([Stage("S", steps=[plain, gstring, echo])]))]
    assert 'echo "${#PASSWORD} ${TICKET:-none} ${env.X}"' in runs  # '...' strings reach the shell untouched
    assert 'echo "${X} ${TICKET:-none}"' in runs  # Groovy interpolation translated, shell expansion kept
    assert 'echo "cost: \\$5"' in runs  # a plain echo message is printed literally


def test_write_file_gstring_expands_only_interpolation():
    from j2gha.ir import Stage, Step
    gs = Step("writeFile", named={"file": "info.txt", "text": "app=${APP}\ncost=$5 `x`\n"}, dynamic=True)
    plain = Step("writeFile", named={"file": "raw.txt", "text": "keep ${APP}"})
    runs = [s["run"] for s in _steps(_jobs_for([Stage("S", steps=[gs, plain])]))]
    assert "cat > info.txt <<J2GHA_EOF\napp=${APP}\ncost=\\$5 \\`x\\`\nJ2GHA_EOF" in runs
    assert "printf '%s' 'keep ${APP}' > raw.txt" in runs  # no final newline in the text: none in the file


def test_stash_paths_follow_dir_and_artifact_root():
    from j2gha.ir import Stage, Step
    build = Stage("Build", steps=[Step("stash", named={"name": "dist", "includes": "dist/**"}),
                                  Step("dir", args=["out"], body=[Step("stash", named={"name": "rep", "includes": "a/x.txt, a/b/*.xml"})])])
    use = Stage("Use", steps=[Step("dir", args=["work"], body=[Step("unstash", args=["dist"])]),
                              Step("unstash", args=["rep"]), Step("archiveArtifacts", named={"artifacts": "dist/*.tgz", "excludes": "dist/tmp*"})])
    w = {s["name"]: s["with"] for s in _steps(_jobs_for([build, use])) if "with" in s}
    def listed(name):  # the upload's own patterns, without Ant's default excludes (**/.git/** and friends)
        return "\n".join(line for line in w[name]["path"].splitlines() if "/**/" not in line and not line.startswith("!**/"))
    assert listed("Build: stash rep") == "out/a/x.txt\nout/a/b/*.xml"
    assert w["Use: unstash dist"]["path"] == "work/dist"  # upload-artifact stored dist/** relative to dist/
    assert w["Use: unstash rep"]["path"] == "a"
    assert listed("Use: archive artifacts") == "dist/*.tgz\n!dist/tmp*"
    assert "!**/.git/**" in w["Use: archive artifacts"]["path"].splitlines()  # archiveArtifacts default excludes


def test_matrix_artifact_names_are_unique_per_cell():
    from j2gha.ir import Matrix, Stage, Step
    inner = Stage("Cell", steps=[Step("stash", named={"name": "s", "includes": "**"})],
                  post={"always": [Step("junit", args=["r/*.xml"])]})
    jobs = _jobs_for([Stage("M", matrix=Matrix(axes={"OS": ["a", "b"], "PY": ["3"]}, stages=[inner]))])
    w = {s["name"]: s["with"] for s in _steps(jobs) if "with" in s}
    assert w["Cell: upload test reports"]["name"].endswith("-${{ matrix.OS }}-${{ matrix.PY }}")
    assert w["Cell: stash s"]["name"] == "stash-s" and w["Cell: stash s"]["overwrite"] is True


def test_not_expression_with_method_call_is_translated():
    from j2gha.analysis.declarative import parse_condition
    from j2gha.convert.expressions import condition_expr
    call = {"k": "call", "name": "endsWith", "receiver": "params.VERSION", "named": {},
            "args": [{"t": "str", "v": "-SNAPSHOT"}], "line": 3}
    cond = parse_condition({"name": "not", "line": 3, "body": [
        {"k": "call", "name": "expression", "line": 3, "body": [call]}]})
    assert condition_expr(cond) == ("!(endsWith(env.VERSION, '-SNAPSHOT'))", "approximated")


def test_runtime_env_exports_do_not_mask_command_status():
    from j2gha.ir import Agent, EnvValue, Pipeline, Stage, Step
    ir = Pipeline(dialect="declarative", agent=Agent(kind="any"), stages=[Stage("S", steps=[Step("sh", args=["true"])])],
                  environment={"V": EnvValue(kind="shell", value="date"), "L": EnvValue(kind="expression", value="${V}-x")})
    setup = convert(ir, "", title="t")["workflow"]["jobs"]["s"]["steps"][1]["run"]
    assert 'V="$(date)"; export V;' in setup and 'export L="${V}-x";' in setup  # SC2155 only applies to $(...)


def test_scripted_trace_matches_jenkins_stubs(library_classes):
    import re
    text, ast = library_classes
    ir = build_ir(ast)
    assert [s.name for s in ir.stages if s.name] == ["Build"]  # stage(stageName) after stageName = 'Build'
    wf = convert(ir, text, title="library-classes")["workflow"]
    variant, _ = make_variant(wf, "trace", "act", {"branch": "main"})
    events = [m.group(0) for job in variant["jobs"].values() for s in job["steps"]
              for m in re.finditer(r'\{"stage":"[^"]*","step":"[^"]*"\}', s.get("run") or "")]
    # scripted node {} has no implicit checkout; tools.log() and new Settings() hit silent stubs on Jenkins
    # tools.build() is a library method named like the traced build step; settings.inStage() {} runs its block
    # the loose `sh 'deploy'` (settings.inStage('Deploy') {}, after node {}) keeps its place after Build
    assert events == ['{"stage":"Build","step":"sh"}', '{"stage":"Build","step":"platformPublish"}',
                      '{"stage":"Build","step":"sh"}', '{"stage":"","step":"sh"}']


def test_literal_if_chain_exports_script_variable(script_dispatch, tmp_path):
    import subprocess
    text, ast = script_dispatch
    ir = build_ir(ast)
    assert ir.stages[1].when.conditions[0].text.strip() == "return target == 'dev' || target == 'pro'"
    wf = convert(ir, text, title="dispatch")["workflow"]
    setup, deploy = wf["jobs"]["setup"], wf["jobs"]["deploy"]
    chain = next(s for s in setup["steps"] if s["name"] == "Setup: set target")
    assert setup["outputs"] == {"target": f"${{{{ steps.{chain['id']}.outputs.target }}}}"}
    assert deploy["needs"] == "setup" and deploy["env"] == {"target": "${{ needs.setup.outputs.target }}"}
    assert any(s.get("if") == "env.target == 'dev' || env.target == 'pro'" for s in deploy["steps"])

    def run(script, branch):
        env_file, out_file = tmp_path / "env", tmp_path / "out"
        env_file.write_text(""), out_file.write_text("")
        r = subprocess.run(["bash", "-e", "-c", script], capture_output=True, text=True,
                           env={"GIT_BRANCH": branch, "GITHUB_ENV": str(env_file), "GITHUB_OUTPUT": str(out_file)})
        return r.returncode, env_file.read_text(), r.stdout

    assert run(chain["run"], "origin/feature-x")[:2] == (0, "target=dev\n")  # ==~ is a full match
    assert run(chain["run"], "origin/master")[:2] == (0, "target=pro\n")
    assert run(chain["run"], "origin/other")[0] == 1
    # the trace variant keeps the chain (later conditions read it) and marks only the error branch
    variant, _ = make_variant(wf, "trace", "act", {"branch": "main"})
    traced = next(s for s in variant["jobs"]["setup"]["steps"] if s["name"] == "Setup: set target")
    code, env_out, stdout = run(traced["run"], "origin/other")
    assert code == 1 and 'J2GHA-TRACE {"stage":"Setup","step":"error"}' in stdout
    assert run(traced["run"], "origin/master")[1] == "target=pro\n"


def test_equals_with_single_interpolation_gstring():
    from j2gha.convert.expressions import condition_expr
    from j2gha.ir import Condition
    c = Condition(kind="equals", value={"expected": "'NONE'", "actual": "${params.TARGET_VERSION}"}, line=9)
    assert condition_expr(c) == ("(env.TARGET_VERSION) == ('NONE')", "approximated")


def test_inlined_helper_runs_the_callers_block():
    from j2gha.ir import Pipeline, Stage, Step
    helper = {"params": ["registry", "closure"],
              "body": [Step(name="withEnv", args=[["NPM_CONFIG_REGISTRY=${registry}"]], body=[Step(name="closure")])]}
    call = Step(name="withNpmEnv", args=["https://npm.example"], category="local", body=[Step(name="sh", args=["npm test"])])
    ir = Pipeline(dialect="declarative", stages=[Stage(name="QA", steps=[call])], method_defs={"withNpmEnv": helper},
                  options={"skipDefaultCheckout": True})
    steps = [s for job in convert(ir, "", title="t")["workflow"]["jobs"].values() for s in job["steps"]]
    assert [s.get("run") for s in steps] == ["npm test"]
    assert steps[0]["env"]["NPM_CONFIG_REGISTRY"] == "https://npm.example"


# ------------------------------------------------------------------------- execution semantics (fixture: semantics)
def _semantics(semantics):
    text, ast = semantics
    return convert(build_ir(ast), text, title="semantics")


def _run_bash(script: str, tmp_path):
    import subprocess
    f = tmp_path / "step.sh"
    f.write_text(script)
    # GitHub runs `shell: bash` steps as `bash --noprofile --norc -eo pipefail {0}`
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(f)], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "RUNNER_TEMP": str(tmp_path)}, cwd=tmp_path)


def test_retry_attempts_fail_on_the_first_failing_command(semantics, tmp_path):
    from j2gha.convert.generator import Ctx, _retry_loop
    from j2gha.ir import Pipeline

    steps = _semantics(semantics)["workflow"]["jobs"]["build"]["steps"]
    step = next(s for s in steps if "SHOULD_NOT_RUN" in s.get("run", ""))
    assert step["shell"] == "bash"
    p = _run_bash(step["run"], tmp_path)
    assert "SHOULD_NOT_RUN" not in p.stdout and p.returncode == 1
    assert "retrying (1/2)" in p.stderr and "retrying" not in p.stdout  # a captured `sh` value only gets the output
    ctx = Ctx(ir=Pipeline(dialect="declarative"), source_text="")
    # exhaustion keeps the last exit status; a later attempt can succeed
    p = _run_bash(_retry_loop("echo try\nexit 7", None, 3, ctx, "S", 1)[0], tmp_path)
    assert p.returncode == 7 and p.stdout.splitlines().count("try") == 3
    flaky = 'n=$(cat count 2>/dev/null || echo 0); echo $((n + 1)) > count\n[ "$n" -ge 1 ]\necho done'
    p = _run_bash(_retry_loop(flaky, None, 3, ctx, "S", 1)[0], tmp_path)
    assert p.returncode == 0 and p.stdout.count("done") == 1 and "retrying (1/3)" in p.stderr
    # a shebang interpreter keeps its semantics inside the loop; Windows shells are reported, not wrapped
    assert '"$j2gha_script"' in _retry_loop("print(1)", "python3 {0}", 2, ctx, "S", 1)[0]
    assert _retry_loop("dir", "cmd", 2, ctx, "S", 1) == ("dir", "cmd")


def test_parallel_and_matrix_stages_keep_their_own_directives(semantics):
    jobs = _semantics(semantics)["workflow"]["jobs"]
    for jid in ("fan-a", "fan-b"):
        steps = jobs[jid]["steps"]
        entry = steps[0]
        assert entry["_j2gha"]["kind"] == "stage-entry" and "skip-" in entry["if"]
        work = [s for s in steps if s["_j2gha"]["kind"] == "sh"]
        assert work and all(s["env"]["REGION"] == "eu" and s["timeout-minutes"] == 2 for s in work)
        assert all(f"steps.{entry['id']}.outputs.run == 'true'" in s["if"] for s in steps[1:])
    # the parallel stage's post runs once, after both branches, and later stages wait for it
    post = jobs["fan-post"]
    assert post["needs"] == ["fan-a", "fan-b"] and post["if"] == "always()"
    assert "always()" in post["steps"][0]["if"] and "skip-" in post["steps"][0]["if"]
    assert set(jobs["cells"]["needs"]) == {"fan-a", "fan-b", "fan-post"}
    # matrix: stage- and cell-level environment/options reach every cell; stage post is a fan-in job
    test = next(s for s in jobs["cells"]["steps"] if s.get("run") == "make test")
    assert test["env"] == {"SUITE": "all", "CELL_VAR": "cell"} and test["timeout-minutes"] == 3
    assert jobs["cells-post"]["needs"] == ["cells"]
    assert "contains(needs.*.result, 'failure')" in jobs["cells-post"]["steps"][0]["if"]


def test_with_env_bindings_are_kept(semantics):
    result = _semantics(semantics)
    step = next(s for s in result["workflow"]["jobs"]["build"]["steps"] if "printf" in s.get("run", ""))
    run = step["run"]
    assert 'export COPY="${ORIGINAL}"' in run  # GString: evaluated by the shell
    assert 'export PATH="/opt/tools/bin:${PATH}"' in run  # PATH+TOOLS prepends
    assert 'export STAMP="${BUILD_ID}"' in run  # 'STAMP=' + env.BUILD_ID
    assert step["env"]["STATIC"] == "${KEEP}"  # single-quoted: Jenkins does not expand it either
    item = next(i for i in result["report"]["items"] if i["jenkins"] == "withEnv")
    assert item["status"] == "approximated"


def test_stage_post_anchors_on_stage_entry(semantics):
    steps = _semantics(semantics)["workflow"]["jobs"]["build"]["steps"]
    entry = next(s for s in steps if s["_j2gha"]["kind"] == "stage-entry")
    ran = f"steps.{entry['id']}.outcome == 'success'"
    posts = {s["run"]: s["if"] for s in steps if s.get("run", "").startswith('echo "build')}
    # a skipped first/last step no longer decides whether always/success/cleanup run
    assert all(ran in cond for cond in posts.values())
    assert "always()" in posts['echo "build always"'] and "always()" in posts['echo "build cleanup"']
    success = posts['echo "build ok"']
    assert "!cancelled()" in success
    # an always-post step that fails counts as a stage failure for the success condition, as in Jenkins
    always_id = next(s["id"] for s in steps if s.get("run") == 'echo "build always"')
    assert f"steps.{always_id}.outcome == 'failure'" in success


def test_post_job_steps_have_status_functions(semantics):
    post = _semantics(semantics)["workflow"]["jobs"]["post"]
    assert post["if"] == "always()"
    # a job-level always() does not reach the steps: a failing notify must not skip the lock release
    assert [s["if"] for s in post["steps"]] == ["always()", "always()"]


def test_reserved_secret_names(semantics):
    result = _semantics(semantics)
    assert result["workflow"]["env"]["TOKEN"] == "${{ secrets.JENKINS_GITHUB_TOKEN }}"
    assert "secrets.GITHUB_" not in to_yaml(result["workflow"])


def test_stage_condition_is_evaluated_once():
    """A step that changes the variable a stage `when` reads must not switch the stage's later steps off."""
    from j2gha.ir import Condition, Stage, Step, When

    deploy = Stage(name="Deploy", when=When(conditions=[Condition("environment", name="TARGET", value="prod")]),
                   steps=[Step("sh", args=["./deploy.sh"]), Step("sh", args=["./smoke.sh"])])
    steps = _jobs_for([deploy])["deploy"]["steps"]
    entry = next(s for s in steps if s["_j2gha"]["kind"] == "stage-entry")
    assert entry["if"] == "env.TARGET == 'prod'"
    assert all(s["if"] == f"steps.{entry['id']}.outputs.run == 'true'" for s in steps if s.get("run", "").startswith("./"))


def test_direct_catalog_steps_have_a_generator_mapping(monkeypatch):
    """Coverage gives `direct` steps full credit: each must reach a deterministic generator mapping."""
    from j2gha.analysis.catalog import load_catalog
    from j2gha.convert import generator
    from j2gha.ir import Pipeline

    unmapped = []
    monkeypatch.setattr(generator, "_unmapped", lambda s, *a: unmapped.append(s.name) or [])
    args = {"zip": {"zipFile": "a.zip"}, "unzip": {"zipFile": "a.zip"}, "tar": {"file": "a.tgz"},
            "untar": {"file": "a.tgz"}, "sh": {"script": "make"}, "bat": {"script": "x"},
            "powershell": {"script": "x"}, "pwsh": {"script": "x"}}
    ctx = generator.Ctx(ir=Pipeline(dialect="declarative"), source_text="")
    # job properties are mapped where they occur (options {} / properties([...]) -> concurrency), not as steps
    properties = {"disableConcurrentBuilds"}
    direct = [n for n, e in load_catalog()["steps"].items() if e["category"] == "direct" and n not in properties]
    for name in direct:
        generator._step(Step(name, named=args.get(name, {})), ctx, generator.Inherit(stage="S"))
    assert direct and not unmapped, f"direct in rules/steps.yaml but not mapped by the generator: {unmapped}"


def test_archive_steps(tmp_path):
    from j2gha.convert import generator
    from j2gha.ir import Pipeline

    ctx = generator.Ctx(ir=Pipeline(dialect="declarative"), source_text="")
    inh = generator.Inherit(stage="S")
    (zip_step,) = generator._step(Step("zip", named={"zipFile": "out/a.zip", "dir": "dist"}), ctx, inh)
    assert zip_step["run"] == 'j2gha_zip="$PWD"/out/a.zip; (cd dist && zip -qr "$j2gha_zip" .)'
    (tar_step,) = generator._step(Step("tar", named={"file": "a.tgz", "dir": "dist", "compress": True}), ctx, inh)
    assert tar_step["run"] == "tar -czf a.tgz -C dist ."
    assert all(not s["_j2gha"]["trace"] for s in (zip_step, tar_step))  # not traced on the Jenkins side either
    # archiveArtifacts keeps dotfiles (013 archived .project/.settings files); upload-artifact must be told to
    (archive,) = generator._step(Step("archiveArtifacts", named={"artifacts": "**"}), ctx, inh)
    assert archive["with"]["include-hidden-files"] is True
    assert archive["with"]["if-no-files-found"] == "error"
    # ... but Jenkins applies Ant's default excludes (013 archived '**' and Jenkins kept no .git/**), unless told not to
    assert "!**/.git/**" in archive["with"]["path"].splitlines()
    (raw,) = generator._step(Step("archiveArtifacts", named={"artifacts": "**", "defaultExcludes": False}), ctx, inh)
    assert "!**/.git/**" not in raw["with"]["path"].splitlines()
    (stash,) = generator._step(Step("stash", named={"name": "s", "includes": "**", "useDefaultExcludes": False}), ctx, inh)
    assert "!**/.git/**" not in stash["with"]["path"].splitlines()


def test_inlined_helper_keeps_variable_arguments_as_references():
    from j2gha.ir import Pipeline, Stage

    body = [Step("sh", args=["deploy --registry ${registry}"], dynamic=True)]
    for args, variable_args, expected in ((["myRegistry"], [0], "deploy --registry ${myRegistry}"),
                                          (["registry.example.com"], [], "deploy --registry registry.example.com")):
        ir = Pipeline(dialect="declarative", stages=[Stage("Deploy", steps=[
            Step("helper", args=args, variable_args=variable_args, category="local", dynamic=bool(variable_args))])],
            method_defs={"helper": {"params": ["registry"], "body": body}}, options={"skipDefaultCheckout": True})
        steps = convert(ir, "", title="t")["workflow"]["jobs"]["deploy"]["steps"]
        assert any(s.get("run") == expected for s in steps), [s.get("run") for s in steps]


def test_report_items_map_to_crosswalk_entries():
    assert xref_key("stage 'Build' when") == "when"
    assert xref_key("stage 'Don't' post failure") == "post"
    assert xref_key("options: timeout") == "timeout"
    assert xref_key("options: preserveStashes") == "options"  # no entry of its own: the section's pages
    assert xref_key("(no pipeline timeout)") == "timeout"
    assert xref_key("assign env.X = 1") == "scripted"
    assert xref_key("buildInParallel() (local helper method)") == "scripted"
    assert xref_key("withCredentials usernamePassword 'creds'") == "withCredentials"
    assert xref_key("stage 'Tests' nested parallel") == "parallel"
    assert xref_key("rocketSend") is None


def test_report_references_order_and_links(declarative, monkeypatch):
    from j2gha.docs import store

    monkeypatch.setattr(store, "docs_dir", lambda: pytest.fail("the report read the local docs directory"))
    items = [{"jenkins": "sh", "status": "mapped"}, {"jenkins": "stash 'x'", "status": "approximated"},
             {"jenkins": "assign env.X = 1", "status": "manual"}, {"jenkins": "sh", "status": "approximated"},
             {"jenkins": "rocketSend", "status": "manual"}]
    section = references_section(items)
    assert [line.split("`")[1] for line in section if line.startswith("- **")] == ["scripted", "sh", "stash"]
    assert "- **`sh`** (🟡 1 approximated, ✅ 1 mapped): " in "\n".join(section)
    report = _convert(declarative)["report"]
    links = re.findall(r"\]\(([^)]+)\)", "\n".join(references_section(report["items"])))
    assert links and all(u.startswith(("https://www.jenkins.io/", "https://docs.github.com/en/actions/")) for u in links)


# ------------------------------------------------------------------------------- full-mode corpus findings (C2, C5, C10, H7)
def _wf_for(stages, **options):
    from j2gha.ir import Agent, Pipeline
    ir = Pipeline(dialect="declarative", agent=Agent(kind="any"), stages=stages,
                  options={"skipDefaultCheckout": True, **options})
    return convert(ir, "", title="t")


def test_scm_env_is_emitted_whenever_the_workflow_checks_out(declarative):
    """C5: Jenkins' checkout exports GIT_COMMIT/GIT_BRANCH/GIT_URL to every sh, so scripts the pipeline calls may
    read them even when the Jenkinsfile never mentions them (the fixture does not)."""
    from j2gha.ir import Stage, Step
    scm = {"GIT_COMMIT", "GIT_BRANCH", "GIT_URL"}
    implicit = _convert(declarative)
    env = implicit["workflow"]["env"]
    assert scm <= set(env) and env["GIT_COMMIT"] == "${{ github.sha }}"
    assert env["GIT_URL"] == "${{ github.server_url }}/${{ github.repository }}.git"
    item = next(i for i in implicit["report"]["items"] if i["jenkins"].startswith("checkout: SCM environment"))
    # listed, but not scored: the automation share counts Jenkins elements (review metric caveat, M-4)
    assert item["status"] == "info" and item["gha"] == "env"
    # no checkout at all (skipDefaultCheckout, no checkout/git step): Jenkins defines none of them either
    none = _wf_for([Stage("S", steps=[Step("sh", args=["make"])])])
    assert not scm & set(none["workflow"]["env"])
    assert not any(i["jenkins"].startswith("checkout: SCM") for i in none["report"]["items"])
    # an explicit `checkout scm` / `git` step counts
    explicit = _wf_for([Stage("S", steps=[Step("checkout", args=["scm"]), Step("sh", args=["./entry.sh"])])])
    assert scm <= set(explicit["workflow"]["env"])
    git = _wf_for([Stage("S", steps=[Step("git", named={"url": "https://github.com/o/r.git"})])])
    assert scm <= set(git["workflow"]["env"])


def test_stash_allow_empty_matches_jenkins():
    """C10: a default stash matching nothing fails in Jenkins; `allowEmpty: true` stashes nothing and the later
    unstash succeeds with nothing."""
    from j2gha.ir import Stage, Step
    build = Stage("Build", steps=[Step("stash", named={"name": "dist", "includes": "dist/**"}),
                                  Step("stash", named={"name": "opt", "includes": "opt/**", "allowEmpty": True})])
    use = Stage("Use", steps=[Step("unstash", args=["dist"]), Step("unstash", args=["opt"])])
    result = _wf_for([build, use])
    steps = {s["name"]: s for s in _steps(result["workflow"]["jobs"])}
    assert steps["Build: stash dist"]["with"]["if-no-files-found"] == "error"
    assert "continue-on-error" not in steps["Use: unstash dist"]
    assert steps["Use: unstash dist"]["with"]["name"] == "stash-dist" and "pattern" not in steps["Use: unstash dist"]["with"]
    assert steps["Build: stash opt"]["with"]["if-no-files-found"] == "ignore"
    # R8-6: an absent optional stash is a successful empty download (by pattern), never a tolerated failure whose
    # 'failure' outcome a stage post condition would read
    assert "continue-on-error" not in steps["Use: unstash opt"]
    opt = steps["Use: unstash opt"]["with"]
    assert (opt["pattern"], opt["merge-multiple"], "name" in opt) == ("stash-opt", True, False)
    notes = {i["jenkins"]: i for i in result["report"]["items"]}
    assert notes["stash 'opt'"]["status"] == "approximated" and "allowEmpty" in notes["stash 'opt'"]["note"]
    assert "pattern" in notes["unstash 'opt'"]["note"] and notes["unstash 'dist'"]["note"] == ""


def test_step_names_carry_no_surrounding_or_repeated_whitespace():
    """H7: GitHub trims step names; the harness maps a failed step back to its stage by name."""
    from j2gha.ir import Stage, Step
    long = "tar --exclude='./.git' --exclude='./Jenkinsfile' --exclude='*.tar.gz' -czv ./src -f ${packname}"
    assert long[:70].endswith(" ")  # the 006 case: the title cut lands on a space
    steps = _steps(_wf_for([Stage("Build", steps=[Step("sh", args=[long]), Step("sh", args=["  a \t b   c  "])])])
                   ["workflow"]["jobs"])
    names = [s["name"] for s in steps if s["_j2gha"]["kind"] == "sh"]
    assert names[0] == "Build: " + long[:70].rstrip()
    assert names[1] == "Build: a b c"  # the title is the script's first line, its whitespace collapsed
    assert all(n == " ".join(n.split()) for s in steps for n in [s["name"]])


def test_unset_env_in_a_gstring_is_the_string_null():
    """C2: Groovy renders an unset `env.TAG_NAME`/`env.CHANGE_*` inside a GString as `null`; the converted step
    defines them as '' and must read them with `${X:-null}`. Plain ('...') shell text and other names are untouched."""
    from j2gha.ir import Stage, Step
    gstring = Step("sh", args=['if [ "${env.TAG_NAME}" = "" ]; then echo tag; fi; echo ${CHANGE_ID} ${env.X} ${params.TAG_NAME}'],
                   dynamic=True)
    plain = Step("sh", args=['echo "${env.TAG_NAME} ${TAG_NAME}"'])
    escaped = Step("sh", args=['echo "${TAG_NAME:-x} ${CHANGE_ID}"'], dynamic=True)  # "...\${TAG_NAME:-x}" in Groovy
    echo = Step("echo", args=["target ${env.CHANGE_TARGET}"], dynamic=True)
    wf = Step("writeFile", named={"file": "f", "text": "tag=${env.TAG_NAME}\n"}, dynamic=True)
    result = _wf_for([Stage("S", steps=[gstring, plain, escaped, echo, wf])])
    runs = [s["run"] for s in _steps(result["workflow"]["jobs"]) if "run" in s]
    assert runs[0] == 'if [ "${TAG_NAME:-null}" = "" ]; then echo tag; fi; echo ${CHANGE_ID:-null} ${X} ${TAG_NAME}'
    assert runs[1] == 'echo "${env.TAG_NAME} ${TAG_NAME}"'  # single-quoted: reaches the shell verbatim
    assert runs[2] == 'echo "${TAG_NAME:-x} ${CHANGE_ID:-null}"'  # the author's own shell default is kept
    assert runs[3] == 'echo "target ${CHANGE_TARGET:-null}"'
    assert "cat > f <<J2GHA_EOF\ntag=${TAG_NAME:-null}\nJ2GHA_EOF" in runs[4]  # the heredoc still expands it
    notes: dict[str, list[str]] = {}
    for i in result["report"]["items"]:
        notes.setdefault(i["jenkins"], []).append(i["note"])
    both = next(n for n in notes["sh"] if "CHANGE_ID" in n)
    assert "an unset env.CHANGE_ID/TAG_NAME is the string 'null' in Jenkins" in both
    assert "${CHANGE_ID:-null}/${TAG_NAME:-null}" in both and "drop the default" in both
    assert notes["sh"].count("") == 1  # the plain string gets no note; the escaped GString notes CHANGE_ID
    assert "env.CHANGE_TARGET" in notes["echo"][0] and "env.TAG_NAME" in notes["writeFile"][0]


def test_map_form_credentials_bindings_become_secrets():
    # withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'iam', accessKeyVariable: ...]])
    from j2gha.analysis.declarative import binding_type
    from j2gha.convert import generator
    from j2gha.ir import Pipeline

    assert binding_type("AmazonWebServicesCredentialsBinding") == "aws"
    assert binding_type("UsernamePasswordMultiBinding") == "usernamePassword"
    ctx = generator.Ctx(ir=Pipeline(dialect="scripted"), source_text="")
    inh = generator.Inherit(stage="S")
    step = Step("withCredentials", named={"bindings": [{"type": "aws", "credentialsId": "jenkins-iam",
                                                        "accessKeyVariable": "AWS_ACCESS_KEY_ID",
                                                        "secretKeyVariable": "AWS_SECRET_ACCESS_KEY"}]},
                body=[Step("sh", args=["aws s3 ls"])])
    (sh,) = generator._step(step, ctx, inh)
    assert sh["env"]["AWS_ACCESS_KEY_ID"] == "${{ secrets.JENKINS_IAM_USR }}"
    assert sh["env"]["AWS_SECRET_ACCESS_KEY"] == "${{ secrets.JENKINS_IAM_PSW }}"


def test_credential_id_from_a_literal_pipeline_environment_value():
    # credentialsId: "${ocir_creds}" with `ocir_creds = 'wkt-ocir-creds'` in environment {} (007)
    from j2gha.convert import generator
    from j2gha.ir import EnvValue, Pipeline

    ir = Pipeline(dialect="declarative", environment={"ocir_creds": EnvValue(kind="literal", value="wkt-ocir-creds")})
    ctx = generator.Ctx(ir=ir, source_text="")
    step = Step("withCredentials", named={"bindings": [{"type": "usernamePassword", "credentialsId": "${ocir_creds}",
                                                        "usernameVariable": "U", "passwordVariable": "P"}]},
                body=[Step("sh", args=["docker login"])])
    (sh,) = generator._step(step, ctx, generator.Inherit(stage="S"))
    assert sh["env"]["U"] == "${{ secrets.WKT_OCIR_CREDS_USR }}"



def test_script_constants_are_top_level_literals_assigned_once():
    from j2gha.analysis.declarative import script_constants

    def assign(name, value):
        return {"k": "assign", "op": "=", "target": name, "value": value}

    ast = {"statements": [assign("IMAGE", {"t": "str", "v": "debian"}),
                          assign("TAG", {"t": "str", "v": "12"}),
                          assign("BUILT", {"t": "call", "name": "sh"}),
                          assign("CHANGED", {"t": "str", "v": "a"}),
                          {"k": "call", "name": "node", "body": [assign("CHANGED", {"t": "str", "v": "b"})]}],
           "methods": [{"name": "f", "body": [{"k": "decl", "name": "TAG", "value": {"t": "str", "v": "13"}}]}]}
    assert script_constants(ast) == {"IMAGE": "debian"}


def test_container_image_resolves_values_fixed_before_the_run():
    from j2gha.ir import Agent, EnvValue, Pipeline, Stage
    ir = Pipeline(dialect="declarative", constants={"BASE": "apache/ci:erlang", "VER": "27"},
                  environment={"ARGS": EnvValue("literal", "-e HOME=."), "LATER": EnvValue("shell", "date")},
                  stages=[Stage("Build", agent=Agent("docker", image="${BASE}-${VER}", args="${ARGS}"),
                                steps=[Step("sh", args=["make"])]),
                          Stage("Test", agent=Agent("docker", image="${BASE}-${LATER}"),
                                steps=[Step("sh", args=["make test"])])])
    out = convert(ir, "")
    jobs = out["workflow"]["jobs"]
    assert jobs["build"]["container"] == {"image": "apache/ci:erlang-27", "options": "-e HOME=."}
    assert jobs["test"]["container"]["image"] == "apache/ci:erlang-${LATER}"  # not fixed before the run: left as is
    status = {i["jenkins"]: i["status"] for i in out["report"]["items"]}
    assert status["agent docker '${BASE}-${VER}'"] == "mapped"
    assert status["agent docker '${BASE}-${LATER}'"] == "manual"


def _assign(target, value, body=None, kind="<assign>"):
    return Step(kind, named={"_target": target, "_value": value}, body=body or [], source=f"{target} = ...")


def test_assigned_values_reach_later_steps_through_github_env(tmp_path):
    # 106: `oversion = sh(returnStdout).trim()`, `version = oversion.take(10) + '-' + env.BUILD_NUMBER`, a GString of
    # earlier variables; 119: `def ws = pwd()`. Run the generated scripts in order, as one job's steps would.
    import os
    import subprocess
    from j2gha.ir import Pipeline, Stage
    trim = {"t": "call", "call": {"name": "trim", "args": [], "receiver": "sh(...)"}}
    take = {"t": "call", "call": {"name": "take", "args": [{"t": "num", "v": 5}], "receiver": "oversion"}}
    steps = [
        _assign("oversion", trim, [Step("sh", args=["echo '  1.2.3-rc1  '"], named={"returnStdout": True})]),
        _assign("version", {"t": "concat", "parts": [{"t": "concat", "parts": [take, {"t": "str", "v": "-"}]},
                                                      {"t": "prop", "text": "env.BUILD_NUMBER", "calls": []}]}),
        _assign("pack", {"t": "gstr", "v": '"app-v${version}.tar.gz"'}),
        _assign("ws", {"t": "call", "call": {"name": "pwd", "args": []}}, [Step("pwd")], kind="<decl>"),
        _assign("odd", {"t": "str", "v": 'a "quoted" $HOME `x`'}),
        _assign("helper", {"t": "new", "type": "Helper"}),  # not a string expression: reported as before
    ]
    out = convert(Pipeline(dialect="declarative", stages=[Stage("Build", steps=steps)]), "")
    runs = [s["run"] for s in out["workflow"]["jobs"]["build"]["steps"] if s.get("run", "").split("=")[0] in
            ("oversion", "version", "pack", "ws", "odd")]
    assert len(runs) == 5
    env_file, out_file = tmp_path / "env", tmp_path / "out"
    env = {**os.environ, "GITHUB_ENV": str(env_file), "GITHUB_OUTPUT": str(out_file), "BUILD_NUMBER": "42"}
    for run in runs:  # each step is its own shell: it only sees what earlier steps wrote to $GITHUB_ENV
        for name, val in re.findall(r"^(\w+)<<J2GHA_EOF\n(.*?)\nJ2GHA_EOF$", env_file.read_text() if env_file.exists()
                                    else "", re.M | re.S):
            env[name] = val
        subprocess.run(["bash", "-eo", "pipefail", "-c", run], env=env, cwd=tmp_path, check=True)
    values = dict(re.findall(r"^(\w+)<<J2GHA_EOF\n(.*?)\nJ2GHA_EOF$", env_file.read_text(), re.M | re.S))
    assert values == {"oversion": "1.2.3-rc1", "version": "1.2.3-42", "pack": "app-v1.2.3-42.tar.gz",
                      "ws": str(tmp_path), "odd": 'a "quoted" $HOME `x`'}
    assert out_file.read_text() == env_file.read_text()  # later jobs get the same values through job outputs
    trace = [s for s in out["workflow"]["jobs"]["build"]["steps"] if s["_j2gha"].get("trace")]
    assert [s["_j2gha"]["kind"] for s in trace] == ["sh"]  # trace parity: only the captured `sh` is a traced step
    status = {i["jenkins"].split(" =")[0]: i["status"] for i in out["report"]["items"]}
    assert status["assign helper"] == "manual" and status["assign version"] == "mapped"


def test_assignment_named_like_an_environment_variable_is_not_exported():
    from j2gha.ir import EnvValue, Parameter, Pipeline, Stage
    ir = Pipeline(dialect="declarative", environment={"STAGE_ENV": EnvValue("literal", "x")},
                  parameters=[Parameter("string", "TARGET")],
                  stages=[Stage("Build", steps=[_assign(n, {"t": "str", "v": "y"})
                                                for n in ("BRANCH_NAME", "STAGE_ENV", "TARGET", "PATH")])])
    runs = [s.get("run", "") for s in convert(ir, "")["workflow"]["jobs"]["build"]["steps"]]
    assert not any("GITHUB_ENV" in r for r in runs)


def test_variants_give_stubbed_properties_the_jenkins_stub_value():
    # 119: `target_location = "${TARGET_LOCATION}"` reads 'j2gha-stub' on Jenkins (an undeclared property the
    # localiser stubs); the converted run must not read an empty value instead
    from j2gha.jenkins.localize import STUBBED_PROPERTY_CHANGE
    from j2gha.runners.variants import stubbed_properties
    ref = {"localisation": {"changes": ["L40: node(master) -> node('built-in')",
                                        *(STUBBED_PROPERTY_CHANGE.format(n) for n in ("TARGET_LOCATION", "docker",
                                                                                      "OWN", "PARAM"))]}}
    names = stubbed_properties(ref)
    assert names == ["TARGET_LOCATION", "OWN", "PARAM"]  # objects (`docker`) have no environment value
    model = {"on": {"workflow_dispatch": {"inputs": {"PARAM": {}}}}, "env": {"OWN": "mine"},
             "jobs": {"b": {"runs-on": "ubuntu-latest", "steps": [{"run": "true", "_j2gha": {"trace": True}}]}}}
    for mode in ("trace", "full"):
        variant, _ = make_variant(model, mode, "act", {"branch": "main"}, stubbed=names)
        assert variant["env"]["TARGET_LOCATION"] == "j2gha-stub"
        assert variant["env"]["OWN"] == "mine" and "PARAM" not in variant["env"]


def test_self_assignment_from_a_parameter_adds_no_step():
    from j2gha.ir import Pipeline, Stage
    ir = Pipeline(dialect="declarative", stages=[Stage("Build", steps=[
        _assign("VERSION", {"t": "prop", "text": "params.VERSION", "calls": []}, kind="<decl>")])])
    out = convert(ir, "")
    assert not any("GITHUB_ENV" in s.get("run", "") for s in out["workflow"]["jobs"]["build"]["steps"])
    assert {i["status"] for i in out["report"]["items"] if i["jenkins"].startswith("decl VERSION")} == {"mapped"}


def test_variants_pin_job_name_to_the_jenkins_job():
    # 106: `iacname = env.JOB_NAME` names a tar file; github.workflow ("j2gha harness run") has spaces, ex-106-full not
    from j2gha.convert.generator import JENKINS_ENV
    from j2gha.jenkins.run import harness_job
    model = {"env": {"JOB_NAME": JENKINS_ENV["JOB_NAME"], "JOB_BASE_NAME": "own"},
             "jobs": {"b": {"runs-on": "ubuntu-latest", "steps": [{"run": "true", "_j2gha": {"trace": True}}]}}}
    variant, _ = make_variant(model, "full", "act", {"branch": "main"}, job_name=harness_job("106", "full"))
    assert variant["env"]["JOB_NAME"] == "ex-106-full"
    assert variant["env"]["JOB_BASE_NAME"] == "own"  # a value the pipeline set itself is kept


def test_full_variants_run_without_docker_when_the_reference_did():
    # 103 (agent dockerfile), 108 (docker.image().inside), 001 (agent docker): without `run --docker` the Jenkins
    # reference ran these steps on the controller; act's and the self-hosted runners' jobs have no Docker daemon
    from j2gha.ir import Agent, Pipeline, Stage
    from j2gha.runners.variants import reference_had_docker
    inside = Step("inside", receiver="docker.image('d3fk/s3cmd')", body=[Step("sh", args=["s3cmd ls"])])
    retried = Step("retry", args=[2], body=[Step("inside", receiver="docker.image('alpine')",
                                                 body=[Step("sh", args=["echo hi"])])])
    ir = Pipeline(dialect="declarative", stages=[
        Stage("Image", agent=Agent("dockerfile", filename="Dockerfile"), steps=[Step("sh", args=["make"])]),
        Stage("Inside", steps=[inside, retried]),
        Stage("Container", agent=Agent("docker", image="debian:12"), steps=[Step("sh", args=["make test"])])])
    model = convert(ir, "")["workflow"]
    image, plain, container = (model["jobs"][j] for j in ("image", "inside", "container"))
    assert all("docker run" in s["run"] for s in plain["steps"] if s.get("run"))
    assert [s["_j2gha"]["run_without_docker"] for s in plain["steps"] if "run_without_docker" in s["_j2gha"]][0] \
        == "s3cmd ls"
    assert "j2gha-retry" in plain["steps"][-1]["_j2gha"]["run_without_docker"]  # the retry loop is kept
    without = {"localisation": {"stubs": ["withCredentials", "withDockerContainer"]}}
    assert not reference_had_docker(without)
    assert reference_had_docker({"localisation": {"stubs": ["withCredentials"]}}) and reference_had_docker(None)
    variant, notes = make_variant(model, "full", "act", {"branch": "main"}, docker=False)
    jobs = variant["jobs"]
    assert "container" not in jobs["container"]
    assert not any(s["_j2gha"]["kind"] == "dockerfile-agent" for s in jobs["image"]["steps"])
    runs = [s.get("run", "") for j in jobs.values() for s in j["steps"]]
    assert "s3cmd ls" in runs and not any("docker run --rm" in r for r in runs)
    assert set(notes["without_docker"]) == {"image", "inside", "container"}
    variant, _ = make_variant(model, "full", "act", {"branch": "main"})  # a reference with Docker: as converted
    assert variant["jobs"]["container"]["container"]["image"] == "debian:12"
    assert any("docker run --rm" in s.get("run", "") for s in variant["jobs"]["inside"]["steps"])
